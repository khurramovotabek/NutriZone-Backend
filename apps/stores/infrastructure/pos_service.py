"""
Store POS -- a partner store owner's own cash register, scoped to ONE store.

Built on the certified POS `Sale` aggregate (apps.pos) with no domain change:

    branch_id  = Store.id            (the sale belongs to this store)
    cashier_id = the owner's identity.User id
    channel    = "store"

What this layer adds on top of the plain Sale lifecycle:

* **Server-side prices only** -- a line's unit price is the variant's active
  catalog price (`bulk_variant_prices`, the same source the storefront shows);
  the client only ever sends *which* variant and *how many*.
* **The store's own stock** (`StoreProductStock`): a line can never exceed what
  the store holds; completion locks the stock rows, re-checks and decrements in
  the same transaction as the Sale completing (all or nothing); a refund puts
  the units back.
* **Payment**: method + amount tendered + change, recorded at completion. Live:
  cash, Uzcard and Humo (the store's own bank terminal; the POS records the
  method and amount). Click/Payme/Uzum are declared so a provider integration is
  a switch, not a migration. Optional basket discount (capped) and loyalty coins
  reduce what is due; every completed sale gets a receipt number + e-receipt token.
* **Isolation**: every sale lookup is filtered by branch_id == this store's id
  -- one owner can never read or touch another store's sales.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.products.infrastructure import barcodes
from apps.products.infrastructure.barcodes import barcode_q
from apps.pos.domain.enums import CARD_PAYMENT_METHODS, LIVE_PAYMENT_METHODS, PaymentMethod, SaleChannel, SaleStatus
from apps.pos.infrastructure import composition as pos
from apps.pos.infrastructure import receipts
from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel
from apps.stores.infrastructure.models import CashSession, CashSessionStatus, Store, StoreProductStock
from apps.stores.infrastructure.pos_cashiers import kassa_name
from apps.stores.infrastructure.stock_service import variant_image_urls
from common.exceptions import ConflictError, ResourceNotFound, ValidationFailed


def _actor_name(user_id) -> str:
    """The cashier's name: a customer account (store owner / linked cashier), or a Dashboard staff member at the online kassa (uuid5 of their auth id)."""
    from apps.identity.infrastructure.models import User

    name = User.objects.filter(id=user_id).values_list("full_name", flat=True).first()
    if name:
        return name
    from apps.pos.infrastructure.sales_reports import _staff_uuid_map

    return _staff_uuid_map().get(user_id, "")


def _conflict(code: str, message: str, **details) -> ConflictError:
    """409 with a stable machine code the terminal localises (details carry e.g. the available quantity)."""
    err = ConflictError(message, details=details)
    err.code = code
    return err

CURRENCY = "UZS"
# The most a cashier may knock off a basket by hand (percent of the basket), a business guard-rail.
MAX_DISCOUNT_PERCENT = Decimal(str(getattr(settings, "POS_MAX_DISCOUNT_PERCENT", 20)))


def _media_url(storage_path: str | None, thumbnail_paths: dict | None, size: str = "small") -> str | None:
    if not storage_path:
        return None
    return f"/media/{(thumbnail_paths or {}).get(size) or storage_path}"


def _first_phone(store: Store) -> str | None:
    phones = store.phone_numbers if isinstance(store.phone_numbers, list) else []
    first = phones[0] if phones else None
    if isinstance(first, dict):
        return first.get("number") or first.get("phone")
    return first


def _variant_label(variant) -> str | None:
    from apps.products.infrastructure.variant_labels import variant_label

    return variant_label(variant)  # "2.27 kg · Chocolate · Banka"


# ---------------------------------------------------------------- catalog


def catalog(store: Store, locale: str, q: str = "", page: int = 1, page_size: int = 48, in_stock_only: bool = False) -> dict:
    """The store's own sellable range: every product it stocks, with live price and the store's own quantity."""
    from apps.products.infrastructure.selectors import bulk_variant_prices

    qs = StoreProductStock.objects.filter(store=store).select_related("product_variant", "product_variant__product", "product_variant__package", "product_variant__flavour").prefetch_related("product_variant__flavour__translations", "product_variant__package__translations")
    if in_stock_only:
        qs = qs.filter(quantity__gt=F("reserved_quantity"))
    q = (q or "").strip()
    if q:
        qs = qs.filter(
            Q(product_variant__sku__iexact=q) | barcode_q(q, "product_variant__") | Q(product_variant__sku__icontains=q)
            | Q(product_variant__product__translations__name__icontains=q)
        ).distinct()
    total = qs.count()
    rows = list(qs.order_by("-quantity", "product_variant__sku")[(page - 1) * page_size: page * page_size])
    scanned = barcodes.resolve(q) if q else None
    scanned_variant_id = scanned.variant.id if scanned else None

    variant_ids = [r.product_variant_id for r in rows]
    prices = bulk_variant_prices(variant_ids)
    from apps.products.infrastructure.models import ProductTranslation

    product_ids = {r.product_variant.product_id for r in rows}
    names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in=product_ids).values("product_id", "locale_code", "name"):
        bucket = names.setdefault(tr["product_id"], {})
        bucket[tr["locale_code"]] = tr["name"]
    images = variant_image_urls(r.product_variant for r in rows)

    exact = None
    items = []
    for r in rows:
        v = r.product_variant
        by_locale = names.get(v.product_id, {})
        price = prices.get(v.id)
        item = {
            "variant_id": str(v.id), "product_id": str(v.product_id), "sku": v.sku, "barcode": v.barcode,
            "name": by_locale.get(locale) or by_locale.get("uz") or by_locale.get("en") or next(iter(by_locale.values()), v.sku),
            "variant_label": _variant_label(v), "image_url": images.get(v.id),
            "price": price["amount"] if price else None, "currency": price["currency"] if price else CURRENCY,
            "stock": r.available, "sellable": bool(price) and r.available > 0 and v.status == "active",
        }
        items.append(item)
        if q and (v.barcode == q or v.sku.lower() == q.lower() or v.id == scanned_variant_id):
            exact = item
            if scanned and scanned.variant.id == v.id and (scanned.batch or scanned.expires_at):
                item["batch"] = {"number": scanned.batch or "", "expiry": scanned.expires_at.isoformat() if scanned.expires_at else None, "code": q,
                                 "expired": bool(scanned.expires_at and scanned.expires_at < timezone.localdate())}
    items.sort(key=lambda i: not i["sellable"])  # stable: sellable first, stock order kept within each group
    return {"results": items, "total_count": total, "page": page, "exact_match": exact}


# ---------------------------------------------------------------- sale access


def _load(store: Store, sale_id: uuid.UUID):
    if not SaleModel.objects.filter(id=sale_id, branch_id=store.id).exists():
        raise ResourceNotFound("Sale not found.")
    return pos.build_load_sale().execute(sale_id)


# ---------------------------------------------------------------- cash-register sessions


def current_session(store: Store) -> CashSession | None:
    return CashSession.objects.filter(store=store, status=CashSessionStatus.OPEN).select_related("opened_by").first()


def _require_session(store: Store) -> CashSession:
    session = current_session(store)
    if session is None:
        raise _conflict("REGISTER_CLOSED", "Open the cash register to start selling.")
    return session


def open_session(store: Store, user_id: uuid.UUID | None, opening_cash: Decimal = Decimal("0"), note: str = "", *, by_name: str = "", online: bool = False) -> CashSession:
    """Opens the kassa's shift. `user_id` = the customer-account cashier; the Dashboard's online kassa passes None + `by_name`."""
    if store.kind == "warehouse" and not online:
        raise _conflict("WAREHOUSE_CANNOT_SELL", "A warehouse doesn't sell -- it receives goods and transfers them to branches.")
    if opening_cash < 0:
        raise ValidationFailed("The opening float can't be negative.")
    with transaction.atomic():
        Store.objects.select_for_update().filter(pk=store.pk).first()
        if current_session(store) is not None:
            raise _conflict("REGISTER_ALREADY_OPEN", "The cash register is already open.")
        return CashSession.objects.create(store=store, opened_by_id=user_id, opened_by_name=(by_name or _actor_name(user_id) if user_id else by_name)[:150],
                                          opening_cash=Decimal(opening_cash).quantize(Decimal("0.01")), opening_note=note[:255])


SESSION_TOTAL_KEYS = (
    "sales_count", "items_sold", "gross_sales", "discounts_total", "coins_redeemed", "cash_sales", "uzcard_sales", "humo_sales",
    "refunds_count", "refunds_total", "cash_refunded",
)


def money_split(payments, fallback_method: str | None = None, fallback_amount: Decimal | None = None) -> dict[str, Decimal]:
    """{"cash": 50000, "uzcard": 70000} from a sale's `payments` (legacy "card" counts as Uzcard)."""
    out: dict[str, Decimal] = {}
    for p in payments or []:
        method = "uzcard" if p.get("method") == PaymentMethod.CARD.value else p.get("method")
        out[method] = out.get(method, Decimal("0")) + Decimal(str(p.get("amount") or 0))
    if not out and fallback_method and fallback_amount:
        out[fallback_method] = fallback_amount
    return out


def _sale_rows(qs) -> list[dict]:
    """
    One row per sale: catalogue subtotal, what was paid in money (subtotal − discount − coins) and how,
    what has been returned so far, and the net value kept (what was paid, coins included, minus returns).
    """
    line_total = F("line_items__unit_price_amount") * F("line_items__quantity")
    rows = list(qs.annotate(gross=Sum(line_total), units=Sum("line_items__quantity"), units_back=Sum("line_items__refunded_quantity")).values(
        "id", "payment_method", "payments", "gross", "units", "units_back", "discount_amount", "coins_redeemed", "customer_id", "completed_at", "status",
        "refunded_amount", "refunded_coins", "refunded_split",
    ))
    for r in rows:
        r["gross"] = r["gross"] or Decimal("0")
        r["units"] = r["units"] or 0
        r["paid"] = max(Decimal("0"), r["gross"] - r["discount_amount"] - r["coins_redeemed"])
        r["split"] = money_split(r["payments"], r["payment_method"], r["paid"])
        r["refund_split"] = {m: Decimal(str(v)) for m, v in (r["refunded_split"] or {}).items()}
        r["refunded_value"] = r["refunded_amount"] + r["refunded_coins"]
        r["net"] = r["gross"] - r["discount_amount"] - r["refunded_value"]
    return rows


def _by_method(rows: list[dict], method: str, net: bool = False) -> Decimal:
    """Money taken by `method` (net=True: minus what was returned by that method)."""
    return sum((r["split"].get(method, Decimal("0")) - (r["refund_split"].get(method, Decimal("0")) if net else 0) for r in rows), Decimal("0"))


def _session_totals(session: CashSession) -> dict:
    """Live (or final) figures for one shift: what was sold in it (split by how it was paid) and every return made in it."""
    from apps.pos.infrastructure.models import SaleRefundModel

    sold = _sale_rows(SaleModel.objects.filter(cash_session_id=session.id, status__in=[SaleStatus.COMPLETED.value, SaleStatus.REFUNDED.value]))
    returns = list(SaleRefundModel.objects.filter(cash_session_id=session.id).values("value", "split"))
    cash_sales = _by_method(sold, PaymentMethod.CASH.value)
    cash_refunded = sum((Decimal(str((r["split"] or {}).get("cash", 0))) for r in returns), Decimal("0"))
    return {
        "sales_count": len(sold), "items_sold": sum(r["units"] for r in sold),
        "gross_sales": sum((r["gross"] for r in sold), Decimal("0")),
        "discounts_total": sum((r["discount_amount"] for r in sold), Decimal("0")),
        "coins_redeemed": sum((r["coins_redeemed"] for r in sold), Decimal("0")),
        "cash_sales": cash_sales,
        "uzcard_sales": _by_method(sold, PaymentMethod.UZCARD.value),
        "humo_sales": _by_method(sold, PaymentMethod.HUMO.value),
        "refunds_count": len(returns),
        "refunds_total": sum((r["value"] for r in returns), Decimal("0")),
        "cash_refunded": cash_refunded,
        # Only cash lives in the drawer -- card money is in the bank, coins are loyalty.
        "expected_cash": session.opening_cash + cash_sales - cash_refunded,
    }


def frozen_totals(session: CashSession) -> dict:
    return {**{k: getattr(session, k) for k in SESSION_TOTAL_KEYS}, "expected_cash": session.expected_cash}


def session_totals(session: CashSession) -> dict:
    """Live for an open shift, the frozen Z-report for a closed one."""
    return _session_totals(session) if session.status == CashSessionStatus.OPEN else frozen_totals(session)


def close_session(store: Store, user_id: uuid.UUID | None, counted_cash: Decimal, note: str = "", *, by_name: str = "", actor_id: uuid.UUID | None = None) -> CashSession:
    """Z-report: freezes the shift's totals, the expected drawer and the counted difference. Refuses while a basket still has items."""
    if counted_cash < 0:
        raise ValidationFailed("Counted cash can't be negative.")
    with transaction.atomic():
        session = CashSession.objects.select_for_update().filter(store=store, status=CashSessionStatus.OPEN).first()
        if session is None:
            raise _conflict("REGISTER_CLOSED", "The cash register is not open.")
        open_baskets = SaleModel.objects.filter(branch_id=store.id, status=SaleStatus.OPEN.value)
        if SaleLineItemModel.objects.filter(sale__in=open_baskets).exists():
            raise _conflict("OPEN_BASKET", "Finish or cancel the current basket before closing the register.")
        for sale_id in open_baskets.values_list("id", flat=True):  # empty baskets are just discarded
            pos.build_void_sale(actor_id or user_id).execute(sale_id)
        totals = _session_totals(session)
        for key in SESSION_TOTAL_KEYS:
            setattr(session, key, totals[key])
        session.expected_cash = totals["expected_cash"]
        session.counted_cash = counted_cash
        session.cash_difference = counted_cash - totals["expected_cash"]
        session.status = CashSessionStatus.CLOSED
        session.closed_by_id = user_id
        session.closed_by_name = (by_name or (_actor_name(user_id) if user_id else ""))[:150]
        session.closed_at = timezone.now()
        session.closing_note = note[:255]
        session.save()
        from apps.stores.infrastructure import shift_report

        sid = session.id
        transaction.on_commit(lambda: shift_report.send(sid))  # Z-report to the owner (inbox + Telegram) and the Orders channel
        return session


def session_payload(session: CashSession | None) -> dict | None:
    if session is None:
        return None
    from apps.identity.infrastructure.models import User

    totals = session_totals(session)
    names = dict(User.objects.filter(id__in=[x for x in (session.opened_by_id, session.closed_by_id) if x]).values_list("id", "full_name"))
    end = session.closed_at or timezone.now()
    return {
        "id": str(session.id), "status": session.status,
        "opened_at": session.opened_at.isoformat(), "opened_by": session.opened_by_name or names.get(session.opened_by_id) or "—",
        "closed_at": session.closed_at.isoformat() if session.closed_at else None, "closed_by": (names.get(session.closed_by_id) or session.closed_by_name) if session.closed_at else None,
        "number": shift_number(session),
        "duration_minutes": int((end - session.opened_at).total_seconds() // 60),
        "opening_cash": str(session.opening_cash), "opening_note": session.opening_note,
        "counted_cash": str(session.counted_cash) if session.counted_cash is not None else None,
        "cash_difference": str(session.cash_difference) if session.cash_difference is not None else None,
        "closing_note": session.closing_note,
        **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()},
    }


def _shift_no(session_id) -> int | None:
    session = CashSession.objects.filter(id=session_id).only("id", "store_id", "opened_at").first() if session_id else None
    return shift_number(session) if session else None


def shift_number(session: CashSession) -> int:
    """The shift's running number at its kassa (1, 2, 3 ...) -- printed on receipts and Z-reports."""
    return CashSession.objects.filter(store_id=session.store_id, opened_at__lte=session.opened_at).count()


def sessions(store: Store, page: int = 1, page_size: int = 20) -> dict:
    qs = CashSession.objects.filter(store=store).order_by("-opened_at")
    total = qs.count()
    return {"results": [session_payload(x) for x in qs[(page - 1) * page_size: page * page_size]], "total_count": total, "page": page}


def open_sale(store: Store, cashier_id: uuid.UUID):
    """Resumes this cashier's open sale at this store if there is one (a refreshed tab never loses a basket), otherwise opens a new one."""
    # Two tabs / a double-mounted component can ask at the same instant: the store
    # row lock serialises them so exactly one open basket ever exists.
    _require_session(store)
    with transaction.atomic():
        Store.objects.select_for_update().filter(pk=store.pk).first()
        existing = SaleModel.objects.filter(branch_id=store.id, cashier_id=cashier_id, status=SaleStatus.OPEN.value, parked_at__isnull=True).order_by("-created_at").first()
        if existing:
            return pos.build_load_sale().execute(existing.id)
        sale = pos.build_open_sale(cashier_id).execute(branch_id=store.id, cashier_id=cashier_id)
        SaleModel.objects.filter(id=sale.id).update(channel=SaleChannel.STORE.value)
        return sale


MAX_PARKED = 10


def park_sale(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, label: str = ""):
    """Puts the basket on hold ("kutishga qo'yish") so the next customer can be served; returns the new empty basket.
    A parked basket stays OPEN (its lines keep their stock checks) and any cashier of the kassa can resume it."""
    _require_session(store)
    with transaction.atomic():
        row = SaleModel.objects.select_for_update().filter(id=sale_id, branch_id=store.id, status=SaleStatus.OPEN.value, parked_at__isnull=True).first()
        if row is None:
            raise ResourceNotFound("Sale not found.")
        if not SaleLineItemModel.objects.filter(sale_id=row.id).exists():
            raise ValidationFailed("An empty basket can't be put on hold.")
        if SaleModel.objects.filter(branch_id=store.id, status=SaleStatus.OPEN.value, parked_at__isnull=False).count() >= MAX_PARKED:
            raise _conflict("TOO_MANY_PARKED", "Too many baskets on hold -- finish or cancel one first.")
        row.parked_at = timezone.now()
        row.parked_label = (label or "").strip()[:60]
        row.save(update_fields=["parked_at", "parked_label"])
    return open_sale(store, cashier_id)


def parked_sales(store: Store) -> list[dict]:
    """Baskets on hold at this kassa, oldest first: who parked it, when, the label, and its size."""
    line_total = F("line_items__unit_price_amount") * F("line_items__quantity")
    rows = (SaleModel.objects.filter(branch_id=store.id, status=SaleStatus.OPEN.value, parked_at__isnull=False)
            .annotate(total=Sum(line_total), units=Sum("line_items__quantity")).order_by("parked_at")
            .values("id", "cashier_id", "customer_id", "parked_at", "parked_label", "total", "units"))
    names = {}
    for r in rows:
        for uid in (r["cashier_id"], r["customer_id"]):
            if uid and uid not in names:
                names[uid] = _actor_name(uid)
    return [{
        "id": str(r["id"]), "label": r["parked_label"], "parked_at": r["parked_at"].isoformat(), "items": int(r["units"] or 0),
        "total": str((r["total"] or Decimal(0)).quantize(Decimal("0.01"))), "cashier": names.get(r["cashier_id"], ""),
        "customer": names.get(r["customer_id"]) if r["customer_id"] else None,
    } for r in rows]


def resume_sale(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID):
    """Brings a parked basket back to the till. The basket in progress is parked in its place (or dropped if empty),
    so nothing is lost; the resumed basket becomes this cashier's."""
    _require_session(store)
    with transaction.atomic():
        Store.objects.select_for_update().filter(pk=store.pk).first()
        target = SaleModel.objects.select_for_update().filter(id=sale_id, branch_id=store.id, status=SaleStatus.OPEN.value, parked_at__isnull=False).first()
        if target is None:
            raise ResourceNotFound("This basket is no longer on hold.")
        for cur in SaleModel.objects.filter(branch_id=store.id, cashier_id=cashier_id, status=SaleStatus.OPEN.value, parked_at__isnull=True):
            if SaleLineItemModel.objects.filter(sale_id=cur.id).exists():
                SaleModel.objects.filter(id=cur.id).update(parked_at=timezone.now(), parked_label="")
            else:
                pos.build_void_sale(cashier_id).execute(cur.id)
        SaleModel.objects.filter(id=target.id).update(parked_at=None, parked_label="", cashier_id=cashier_id)
    return pos.build_load_sale().execute(target.id)


def _stock_for(store: Store, variant_id) -> StoreProductStock:
    entry = StoreProductStock.objects.filter(store=store, product_variant_id=variant_id).select_related("product_variant").first()
    if entry is None:
        raise ResourceNotFound("This product is not in your store.")
    return entry


def _line_variant_map(sale_id) -> dict:
    return {row["id"]: row["product_variant_id"] for row in SaleLineItemModel.objects.filter(sale_id=sale_id).values("id", "product_variant_id")}


def _batch_key(batch: str, expiry) -> str:
    return f"{batch or ''}|{expiry.isoformat() if expiry else ''}"


def _scanned_batch(code: str | None, variant_id) -> tuple[str, object] | None:
    """The batch a scanned batch barcode stands for (None for the product's main barcode / SKU / no code)."""
    if not code:
        return None
    match = barcodes.resolve(code)
    if match is None or match.variant.id != variant_id or not (match.batch or match.expires_at):
        return None
    if match.expires_at and match.expires_at < timezone.localdate():
        raise _conflict("EXPIRED_BATCH", f"This batch expired on {match.expires_at:%d.%m.%Y} -- it can't be sold.", expiry=match.expires_at.isoformat(), batch=match.batch or "")
    return match.batch or "", match.expires_at


def _add_batch(line_id, key: str, units: int) -> None:
    row = SaleLineItemModel.objects.filter(id=line_id).values_list("batches", flat=True).first() or {}
    row = dict(row)
    row[key] = row.get(key, 0) + units
    SaleLineItemModel.objects.filter(id=line_id).update(batches=row)


def _trim_batches(line_id, quantity: int) -> None:
    """A line reduced to `quantity` units keeps at most that many batch-scanned units (the last scanned go first)."""
    row = dict(SaleLineItemModel.objects.filter(id=line_id).values_list("batches", flat=True).first() or {})
    over = sum(row.values()) - quantity
    for key in reversed(list(row)):
        if over <= 0:
            break
        take = min(over, row[key])
        row[key] -= take
        over -= take
        if not row[key]:
            del row[key]
    SaleLineItemModel.objects.filter(id=line_id).update(batches=row)


def add_item(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, variant_id: uuid.UUID, quantity: int, code: str | None = None):
    """
    Adds a variant (or tops up its existing line) at the server-side price, never beyond the store's stock.
    `code` = what was scanned: a batch barcode records the batch on the line (an expired batch is refused).
    """
    from apps.products.infrastructure.selectors import bulk_variant_prices

    if quantity < 1:
        raise ValidationFailed("Quantity must be at least 1.")
    batch = _scanned_batch(code, variant_id)
    sale = _load(store, sale_id)
    entry = _stock_for(store, variant_id)
    if entry.product_variant.status != "active":
        raise _conflict("PRODUCT_INACTIVE", "This product is not available for sale.")
    variant_map = _line_variant_map(sale.id)
    existing_line = next((lid for lid, vid in variant_map.items() if vid == variant_id and lid in sale.line_items), None)
    in_basket = sale.line_items[existing_line].quantity.value if existing_line else 0
    if in_basket + quantity > entry.available:
        raise _conflict("STOCK_LIMIT", f"Only {entry.available} in stock.", available=entry.available)
    if existing_line:
        sale = pos.build_update_line_item_quantity(cashier_id).execute(sale_id=sale.id, line_item_id=existing_line, new_quantity=in_basket + quantity)
        if batch:
            _add_batch(existing_line, _batch_key(*batch), quantity)
        return sale

    price = bulk_variant_prices([variant_id]).get(variant_id)
    if not price:
        raise _conflict("NO_PRICE", "This product has no price yet.")
    before = set(sale.line_items)
    sale = pos.build_add_line_item(cashier_id).execute(
        sale_id=sale.id, product_id=entry.product_variant.product_id, quantity=quantity,
        unit_price_amount=Decimal(price["amount"]), unit_price_currency=price["currency"],
    )
    new_ids = set(sale.line_items) - before
    SaleLineItemModel.objects.filter(id__in=new_ids).update(product_variant_id=variant_id, batches={_batch_key(*batch): quantity} if batch else {})
    return sale


def set_quantity(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, line_id: uuid.UUID, quantity: int):
    sale = _load(store, sale_id)
    if quantity < 1:
        return pos.build_remove_line_item(cashier_id).execute(sale_id=sale.id, line_item_id=line_id)
    variant_id = _line_variant_map(sale.id).get(line_id)
    if variant_id is not None:
        available = _stock_for(store, variant_id).available
        if quantity > available:
            raise _conflict("STOCK_LIMIT", f"Only {available} in stock.", available=available)
    sale = pos.build_update_line_item_quantity(cashier_id).execute(sale_id=sale.id, line_item_id=line_id, new_quantity=quantity)
    _trim_batches(line_id, quantity)
    return sale


def remove_item(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, line_id: uuid.UUID):
    sale = _load(store, sale_id)
    return pos.build_remove_line_item(cashier_id).execute(sale_id=sale.id, line_item_id=line_id)


def clear(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID):
    sale = _load(store, sale_id)
    remover = pos.build_remove_line_item(cashier_id)
    for line_id in list(sale.line_items):
        sale = remover.execute(sale_id=sale.id, line_item_id=line_id)
    return sale


def _loyalty_card(user_id) -> dict:
    from apps.loyalty.infrastructure import services as loyalty

    summary = loyalty.summary(user_id)
    tier = summary.current_tier
    return {
        "balance": summary.balance,
        "tier": {"name": tier.name, "slug": tier.slug, "percent": f"{tier.percent.normalize():f}", "icon": tier.icon, "color": tier.color} if tier else None,
    }


def _customer_card(user) -> dict:
    return {"id": str(user.id), "full_name": user.full_name, "phone_number": user.phone_number, **_loyalty_card(user.id)}


def customer_search(store: Store, q: str) -> list[dict]:
    """
    Privacy rule: a store can look up by name/partial phone only among its OWN past
    buyers; any other platform customer is found only by their exact full phone
    number (what the customer tells the cashier) -- never a browsable directory.
    """
    from apps.identity.domain.value_objects import PhoneNumber
    from apps.identity.infrastructure.models import User

    q = (q or "").strip()
    if len(q) < 2:
        return []
    own_ids = SaleModel.objects.filter(branch_id=store.id, customer_id__isnull=False).values("customer_id")
    digits = "".join(ch for ch in q if ch.isdigit())
    own = User.objects.filter(id__in=own_ids).filter(Q(full_name__icontains=q) | (Q(phone_number__contains=digits) if len(digits) >= 3 else Q(pk__in=[])))
    results = list(own.order_by("full_name")[:6])
    try:
        exact = User.objects.filter(phone_number=PhoneNumber(q.replace(" ", "")).value).first()
    except Exception:  # noqa: BLE001 - not a full phone number: no global lookup
        exact = None
    if exact and exact not in results:
        results.insert(0, exact)
    return [_customer_card(u) for u in results[:6]]


def set_customer(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, phone_number: str = "", full_name: str = "", customer_id: str | None = None):
    """Attach the buyer: an id from customer_search, or find-or-create by phone (an existing customer's name is never overwritten)."""
    from apps.identity.domain.value_objects import PhoneNumber
    from apps.identity.infrastructure.models import User

    if customer_id:
        user = User.objects.filter(id=customer_id).first()
        if user is None:
            raise ResourceNotFound("Customer not found.")
    else:
        try:
            phone = PhoneNumber(str(phone_number).strip().replace(" ", "")).value
        except Exception as exc:  # noqa: BLE001 - value object raises its own validation error type
            raise ValidationFailed("Enter a valid phone number, e.g. +998901234567.") from exc
        user = User.objects.filter(phone_number=phone).first()
        if user is None:
            if not full_name.strip():
                err = ValidationFailed("A name is needed for a new customer.")
                err.code = "NEW_CUSTOMER_NAME_REQUIRED"
                raise err
            user = User.objects.create(phone_number=phone, full_name=full_name.strip()[:255], status="active")
    sale = _load(store, sale_id)
    return pos.build_set_sale_customer(cashier_id).execute(sale_id=sale.id, customer_id=user.id)


def remove_customer(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID):
    sale = _load(store, sale_id)
    if sale.status != SaleStatus.OPEN:
        raise _conflict("SALE_CLOSED", "This sale is already closed.")
    SaleModel.objects.filter(id=sale.id).update(customer_id=None)
    return _load(store, sale.id)


def void(store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID):
    sale = _load(store, sale_id)
    return pos.build_void_sale(cashier_id).execute(sale.id)


def _validated_coins(sale, coins: int, total: Decimal) -> int:
    from apps.loyalty.infrastructure import services as loyalty

    if not coins:
        return 0
    if sale.customer_id is None:
        raise _conflict("COINS_NEED_CUSTOMER", "Select the customer to pay with their coins.")
    try:
        return loyalty.validate_redemption(sale.customer_id, coins, total)
    except loyalty.LoyaltyError as exc:
        raise _conflict(exc.code, str(exc)) from exc


def _redeem(customer_id, coins: int, sale_id, number: str, total: Decimal) -> None:
    from apps.loyalty.infrastructure import services as loyalty

    try:
        loyalty.redeem_for_order(customer_id, coins, sale_id, number, total)
    except loyalty.LoyaltyError as exc:
        raise _conflict(exc.code, str(exc)) from exc


def _lock_stock_for(store: Store, sale) -> tuple[dict, dict]:
    """Locks this store's stock rows for every variant in the basket and verifies there is enough of each."""
    variant_map = _line_variant_map(sale.id)
    needed: dict = {}
    for line in sale.line_items.values():
        vid = variant_map.get(line.id)
        if vid is None:
            raise _conflict("LINE_WITHOUT_VARIANT", "A line is missing its product variant.")
        needed[vid] = needed.get(vid, 0) + line.quantity.value
    stock_rows = {x.product_variant_id: x for x in StoreProductStock.objects.select_for_update().filter(store=store, product_variant_id__in=needed)}
    short = [str(vid) for vid, qty in needed.items() if vid not in stock_rows or stock_rows[vid].available < qty]
    if short:
        raise _conflict("OUT_OF_STOCK", "Some items are no longer in stock.", variant_ids=short)
    return needed, stock_rows


def _validated_discount(discount, total: Decimal) -> Decimal:
    discount = Decimal(str(discount or 0)).quantize(Decimal("1"))
    if discount < 0:
        raise ValidationFailed("The discount can't be negative.")
    cap = (total * MAX_DISCOUNT_PERCENT / Decimal("100")).quantize(Decimal("1"))
    if discount > cap:
        raise _conflict("DISCOUNT_TOO_HIGH", f"A discount can be at most {MAX_DISCOUNT_PERCENT.normalize():f}% of the basket.", max_discount=str(cap), max_percent=str(MAX_DISCOUNT_PERCENT.normalize()))
    return discount


def _validated_payments(payments, due: Decimal) -> dict[str, Decimal]:
    """A split payment: each part a live method, whole so'm, > 0, one part per method, and together exactly the amount due."""
    parts: dict[str, Decimal] = {}
    for p in payments:
        try:
            method = PaymentMethod(str(p.get("method")))
            amount = Decimal(str(p.get("amount"))).quantize(Decimal("1"))
        except Exception as exc:  # noqa: BLE001 - malformed part
            raise ValidationFailed("Each payment needs a method and an amount.") from exc
        if method not in LIVE_PAYMENT_METHODS:
            raise _conflict("PAYMENT_METHOD_UNAVAILABLE", "This payment method is not connected yet.")
        if amount <= 0:
            continue
        if method.value in parts:
            raise ValidationFailed("Each payment method can appear once.")
        parts[method.value] = amount
    if sum(parts.values(), Decimal("0")) != due:
        raise _conflict("PAYMENT_SPLIT_MISMATCH", "The payment parts must add up to the amount due.", due=str(due))
    return parts


def complete(
    store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, payment_method: str, amount_tendered: Decimal | None,
    coins: int = 0, discount: Decimal | int = 0, discount_reason: str = "", payments: list | None = None,
):
    """
    Checkout, all or nothing, inside the open shift:
      1. an optional basket discount (≤ MAX_DISCOUNT_PERCENT, with a reason);
      2. the loyalty coins (optional, needs a customer) cover part of the rest --
         capped by the programme rule (max share, minimum, balance);
      3. the remainder is paid by one method (`payment_method`) or split over
         several (`payments`: e.g. part cash, part Uzcard). Cash: tendered >= the
         cash part, change computed; Uzcard/Humo: exactly their part, on the bank terminal;
      4. the store's stock rows are locked, re-checked and decremented;
      5. the sale is completed, stamped with the shift and given its receipt number.
    Cashback is credited after commit on what the customer actually paid.

    Idempotent against a double tap / network retry: completing a sale that is
    already completed returns it unchanged instead of failing (the till never
    shows an error for a sale that in fact went through, and never charges twice).
    """
    from apps.loyalty.infrastructure import services as loyalty

    if not payments:
        try:
            method = PaymentMethod(payment_method)
        except ValueError as exc:
            raise ValidationFailed("Unknown payment method.") from exc
        if method not in LIVE_PAYMENT_METHODS:
            raise _conflict("PAYMENT_METHOD_UNAVAILABLE", "This payment method is not connected yet.")

    with transaction.atomic():
        if not SaleModel.objects.filter(id=sale_id, branch_id=store.id).exists():
            raise ResourceNotFound("Sale not found.")
        SaleModel.objects.select_for_update().filter(id=sale_id).first()  # serialises a double submit on the row
        sale = _load(store, sale_id)
        if sale.status == SaleStatus.COMPLETED:
            receipts.assign(sale.id)
            return sale
        if sale.status != SaleStatus.OPEN:
            raise _conflict("SALE_CLOSED", "This sale is already closed.")
        session = _require_session(store)
        if not sale.line_items:
            raise _conflict("EMPTY_BASKET", "The basket is empty.")
        total = sale.total().amount
        discount = _validated_discount(discount, total)
        if discount and not (discount_reason or "").strip():
            raise ValidationFailed("Give a reason for the discount.")
        after_discount = total - discount

        coins = _validated_coins(sale, int(coins or 0), after_discount)
        due = after_discount - Decimal(coins)
        if payments:
            parts = _validated_payments(payments, due)
            method_code = next(iter(parts)) if len(parts) == 1 else PaymentMethod.MIXED.value
        else:
            parts = {method.value: due} if due > 0 else {}
            method_code = method.value
        cash_part = parts.get(PaymentMethod.CASH.value, Decimal("0"))
        if cash_part:
            tendered = amount_tendered if amount_tendered is not None else cash_part
            if tendered < cash_part:
                raise _conflict("CASH_TENDERED_TOO_LOW", "The cash received is less than the amount due.", due=str(cash_part))
            change = tendered - cash_part
        else:
            tendered, change = due, Decimal("0")  # the bank terminal charges exactly the amount due

        needed, stock_rows = _lock_stock_for(store, sale)

        sale = pos.build_complete_sale(cashier_id).execute(sale.id)
        number, _token = receipts.assign(sale.id)
        from apps.stores.infrastructure import stock_service

        cashier_name = _actor_name(cashier_id)
        scanned: dict = {}
        for row in SaleLineItemModel.objects.filter(sale_id=sale.id).exclude(batches={}).values("product_variant_id", "batches"):
            for key, units in (row["batches"] or {}).items():
                scanned.setdefault(row["product_variant_id"], {}).setdefault(key, 0)
                scanned[row["product_variant_id"]][key] += units
        for vid, qty in needed.items():
            left = qty
            for key, units in scanned.get(vid, {}).items():  # the batches the cashier scanned leave first, exactly
                take = min(units, left)
                if take <= 0:
                    continue
                batch, _sep, expiry = key.partition("|")
                stock_service.move(store, vid, -take, "sale", reference=number, actor=cashier_name, document_id=sale.id,
                                   batch_number=batch, expiry_date=date.fromisoformat(expiry) if expiry else None)
                left -= take
            if left:
                stock_service.move(store, vid, -left, "sale", reference=number, actor=cashier_name, document_id=sale.id)
        if coins:
            _redeem(sale.customer_id, coins, sale.id, number, after_discount)
        SaleModel.objects.filter(id=sale.id).update(
            channel=SaleChannel.STORE.value, payment_method=method_code, cash_session_id=session.id,
            payments=[{"method": m, "amount": f"{a:.2f}"} for m, a in parts.items()],
            coins_redeemed=Decimal(coins), discount_amount=discount, discount_reason=(discount_reason or "").strip()[:120] if discount else "",
            amount_tendered=tendered, change_amount=max(Decimal("0"), change),
        )
        if sale.customer_id and due > 0:
            customer_id, sale_uuid = sale.customer_id, sale.id
            transaction.on_commit(lambda: loyalty.notify_award(loyalty.award_pos_sale(sale_uuid, customer_id, due, number)))
        if sale.customer_id:
            # the e-receipt in the customer's inbox and Telegram (button opens /r/<token>)
            from apps.notifications.infrastructure.notify import notify

            notify(sale.customer_id, "pos_receipt", {"store": store.name, "number": number, "amount": f"{int(due):,}".replace(",", " ")},
                   link=f"/r/{_token}", dedupe_key=f"pos_receipt:{sale.id}")
    return sale


def _share(total: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    """total × part / whole, rounded down to a whole so'm (never over-returns)."""
    if whole <= 0 or part <= 0:
        return Decimal("0")
    return (total * part / whole).quantize(Decimal("1"), rounding=ROUND_DOWN)


def refund(
    store: Store, cashier_id: uuid.UUID, sale_id: uuid.UUID, items: list | None = None, reason: str = "",
    require_session: bool = True, dry_run: bool = False,
):
    """
    A return (vozvrat) of some or all of a sale -- `items` = [{"line_id", "quantity"}],
    or None for everything not yet returned. The value returned is those units'
    share of what the customer paid (the basket discount spread pro rata); it goes
    back as coins in the proportion coins paid for the sale, the rest as money over
    the sale's payment methods in their proportion (cash out of this shift's drawer,
    card back via the bank terminal). The returned share of the cashback is taken
    back, the units go back on this store's shelf. The last return settles every
    remaining so'm exactly, so a sale returned in parts adds up to the whole.
    When nothing is left the sale becomes REFUNDED.

    `dry_run=True` computes the same figures without changing anything (the till's preview).
    """
    from apps.loyalty.infrastructure import services as loyalty
    from apps.loyalty.infrastructure.models import WalletTransaction
    from apps.pos.infrastructure.models import SaleRefundModel

    with transaction.atomic():
        if not SaleModel.objects.filter(id=sale_id, branch_id=store.id).exists():
            raise ResourceNotFound("Sale not found.")
        row = SaleModel.objects.select_for_update().get(id=sale_id)
        if row.status != SaleStatus.COMPLETED.value:
            raise _conflict("NOT_REFUNDABLE", "Only a completed sale can be returned.")
        session = _require_session(store) if require_session and not dry_run else current_session(store)
        lines = {li.id: li for li in SaleLineItemModel.objects.select_for_update().filter(sale_id=row.id)}

        wanted: dict = {}
        if items:
            for it in items:
                try:
                    lid, qty = uuid.UUID(str(it.get("line_id"))), int(it.get("quantity"))
                except (TypeError, ValueError) as exc:
                    raise ValidationFailed("Each returned item needs a line and a quantity.") from exc
                if qty <= 0:
                    continue
                line = lines.get(lid)
                if line is None:
                    raise ResourceNotFound("That line is not on this sale.")
                if wanted.get(lid, 0) + qty > line.quantity - line.refunded_quantity:
                    raise _conflict("RETURN_QTY_TOO_HIGH", "More units than are left to return.", available=line.quantity - line.refunded_quantity)
                wanted[lid] = wanted.get(lid, 0) + qty
        else:
            wanted = {lid: li.quantity - li.refunded_quantity for lid, li in lines.items() if li.quantity > li.refunded_quantity}
        if not wanted:
            raise _conflict("NOTHING_TO_RETURN", "Choose at least one item to return.")

        gross = sum((li.unit_price_amount * li.quantity for li in lines.values()), Decimal("0"))
        kept_value = gross - row.discount_amount  # what the customer paid, coins included
        final = all(li.quantity - li.refunded_quantity - wanted.get(lid, 0) == 0 for lid, li in lines.items())
        already_value = row.refunded_amount + row.refunded_coins
        chosen_gross = sum((lines[lid].unit_price_amount * q for lid, q in wanted.items()), Decimal("0"))
        value = kept_value - already_value if final else _share(kept_value, chosen_gross, gross)
        coins = (row.coins_redeemed - row.refunded_coins) if final else _share(row.coins_redeemed, value, kept_value)
        amount = value - coins

        paid_parts = money_split(row.payments, row.payment_method, max(Decimal("0"), kept_value - row.coins_redeemed))
        done = {m: Decimal(str(v)) for m, v in (row.refunded_split or {}).items()}
        left = {m: a - done.get(m, Decimal("0")) for m, a in paid_parts.items()}
        if final:
            split = {m: a for m, a in left.items() if a > 0}
        else:
            total_paid = sum(paid_parts.values(), Decimal("0"))
            split = {m: min(left[m], _share(amount, a, total_paid)) for m, a in paid_parts.items()}
            rest = amount - sum(split.values(), Decimal("0"))
            for m in sorted(split, key=lambda k: paid_parts[k], reverse=True):  # rounding remainder onto the biggest part
                take = min(rest, left[m] - split[m])
                split[m] += take
                rest -= take
            split = {m: a for m, a in split.items() if a > 0}

        earned = WalletTransaction.objects.filter(order_id=row.id, kind="earn").values_list("amount", flat=True).first() or 0
        reversed_before = sum(SaleRefundModel.objects.filter(sale_id=row.id).values_list("cashback_reversed", flat=True))
        cashback = max(0, earned - reversed_before) if final else int(_share(Decimal(earned), value, kept_value))

        preview = {
            "value": value, "amount": amount, "coins": coins, "split": split, "cashback": cashback, "final": final,
            "lines": [{"line_id": str(lid), "quantity": q, "value": _share(kept_value, lines[lid].unit_price_amount * q, gross)} for lid, q in wanted.items()],
        }
        if dry_run:
            return None, preview

        count = SaleRefundModel.objects.filter(sale_id=row.id).count()
        record = SaleRefundModel.objects.create(
            sale_id=row.id, number=f"{row.receipt_number or str(row.id)[:8].upper()}-R{count + 1}", cashier_id=cashier_id,
            cash_session_id=session.id if session else None, reason=(reason or "").strip()[:255],
            lines=[{
                "line_id": str(lid), "variant_id": str(lines[lid].product_variant_id) if lines[lid].product_variant_id else None,
                "product_id": str(lines[lid].product_id), "quantity": q, "unit_price": f"{lines[lid].unit_price_amount:.2f}",
                "value": f"{_share(kept_value, lines[lid].unit_price_amount * q, gross):.2f}",
            } for lid, q in wanted.items()],
            value=value, amount=amount, coins=coins, split={m: f"{a:.2f}" for m, a in split.items()}, cashback_reversed=cashback,
        )
        for lid, q in wanted.items():
            SaleLineItemModel.objects.filter(id=lid).update(refunded_quantity=F("refunded_quantity") + q)
            vid = lines[lid].product_variant_id
            if vid:
                from apps.stores.infrastructure import stock_service

                stock_service.move(store, vid, q, "return", reference=record.number, actor=_actor_name(cashier_id), document_id=row.id, note=(reason or "")[:200])
        new_split = {m: f"{done.get(m, Decimal('0')) + split.get(m, Decimal('0')):.2f}" for m in set(done) | set(split)}
        SaleModel.objects.filter(id=row.id).update(refunded_amount=F("refunded_amount") + amount, refunded_coins=F("refunded_coins") + coins, refunded_split=new_split)
        if row.customer_id:
            loyalty.return_coins_for_refund(row.customer_id, record.id, int(coins), record.number)
            loyalty.reverse_cashback_for_refund(row.id, row.customer_id, record.id, int(cashback), record.number)
        if final:
            pos.build_refund_sale(cashier_id).execute(row.id)
            SaleModel.objects.filter(id=row.id).update(refund_cash_session_id=session.id if session else None)
    return _load(store, sale_id), preview


# ---------------------------------------------------------------- payloads & reports


def sale_payload(store: Store, sale, locale: str = "uz") -> dict:
    from apps.identity.infrastructure.models import User
    from apps.products.infrastructure.models import ProductVariant

    row = SaleModel.objects.filter(id=sale.id).values(
        "payment_method", "amount_tendered", "change_amount", "channel", "coins_redeemed", "discount_amount", "discount_reason", "receipt_number", "receipt_token",
        "payments", "refunded_amount", "refunded_coins", "cash_session_id",
    ).first() or {}
    refunded_qty = dict(SaleLineItemModel.objects.filter(sale_id=sale.id).values_list("id", "refunded_quantity"))
    line_batches = dict(SaleLineItemModel.objects.filter(sale_id=sale.id).values_list("id", "batches"))
    variant_map = _line_variant_map(sale.id)
    variants = {v.id: v for v in ProductVariant.objects.filter(id__in=[vid for vid in variant_map.values() if vid]).select_related("package", "flavour").prefetch_related("flavour__translations", "package__translations")}
    info = {i["variant_id"]: i for i in catalog_items_by_variant(store, locale, list(variants))}
    lines = []
    for line in sale.line_items.values():
        vid = variant_map.get(line.id)
        meta = info.get(str(vid), {}) if vid else {}
        lines.append({
            "id": str(line.id), "variant_id": str(vid) if vid else None, "product_id": str(line.product_id),
            "name": meta.get("name") or str(line.product_id)[:8], "variant_label": meta.get("variant_label"), "sku": meta.get("sku"),
            "image_url": meta.get("image_url"), "stock": meta.get("stock"),
            "quantity": line.quantity.value, "unit_price": str(line.unit_price.amount), "line_total": str(line.unit_price.amount * line.quantity.value),
            "refunded_quantity": refunded_qty.get(line.id, 0),
            "batches": [{"batch": k.partition("|")[0], "expiry": k.partition("|")[2] or None, "qty": n} for k, n in (line_batches.get(line.id) or {}).items() if n],
        })
    total = sale.total()
    customer = None
    if sale.customer_id:
        u = User.objects.filter(id=sale.customer_id).first()
        if u:
            customer = _customer_card(u)
            if sale.status == SaleStatus.OPEN:
                from apps.loyalty.infrastructure import services as loyalty

                cfg = loyalty.programme()
                usable, _balance = loyalty.max_redeemable(u.id, total.amount)
                customer["redeem"] = {"enabled": cfg.redeem_enabled, "max_coins": usable, "max_percent": cfg.max_redeem_percent, "min_coins": cfg.min_redeem_coins}
    coins_redeemed = row.get("coins_redeemed") or Decimal("0")
    discount = row.get("discount_amount") or Decimal("0")
    from apps.loyalty.infrastructure.models import WalletTransaction

    earned = WalletTransaction.objects.filter(order_id=sale.id, kind="earn").values_list("amount", flat=True).first()
    cashier = _actor_name(sale.cashier_id) if sale.cashier_id else None
    return {
        "id": str(sale.id), "number": row.get("receipt_number") or "#" + str(sale.id)[:8].upper(), "status": sale.status.value,
        "receipt_number": row.get("receipt_number"), "receipt_token": row.get("receipt_token"),
        "items": lines, "item_count": sum(li["quantity"] for li in lines),
        "total": str(total.amount), "currency": total.currency or CURRENCY,
        "discount": str(discount), "discount_reason": row.get("discount_reason") or "",
        "coins_redeemed": str(coins_redeemed), "amount_due": str(max(Decimal("0"), total.amount - discount - coins_redeemed)), "coins_earned": earned or 0,
        "cashier": cashier or None,
        "payments": [{"method": p["method"], "amount": p["amount"]} for p in (row.get("payments") or [])],
        "refunded_value": str((row.get("refunded_amount") or 0) + (row.get("refunded_coins") or 0)),
        "refunds": refunds_payload(sale.id),
        "customer": customer,
        "payment_method": row.get("payment_method"), "amount_tendered": str(row["amount_tendered"]) if row.get("amount_tendered") is not None else None,
        "change": str(row["change_amount"]) if row.get("change_amount") is not None else None,
        "created_at": sale.created_at.isoformat() if sale.created_at else None,
        "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "refunded_at": sale.refunded_at.isoformat() if sale.refunded_at else None,
        "store": {"name": store.name, "address": ", ".join(x for x in (store.address, store.city) if x), "phone": _first_phone(store)},
        "kassa": kassa_name(store),
        "shift": _shift_no(row.get("cash_session_id")),
    }


def refunds_payload(sale_id) -> list[dict]:
    from apps.pos.infrastructure.models import SaleRefundModel

    return [{
        "number": r.number, "created_at": r.created_at.isoformat(), "value": str(r.value), "amount": str(r.amount), "coins": str(r.coins),
        "split": r.split, "reason": r.reason, "items": sum(int(ln.get("quantity", 0)) for ln in r.lines),
    } for r in SaleRefundModel.objects.filter(sale_id=sale_id).order_by("created_at")]


def catalog_items_by_variant(store: Store, locale: str, variant_ids: list) -> list[dict]:
    if not variant_ids:
        return []
    from apps.products.infrastructure.models import ProductTranslation, ProductVariant

    variants = list(ProductVariant.objects.filter(id__in=variant_ids).select_related("package", "flavour").prefetch_related("flavour__translations", "package__translations"))
    stock = {r["product_variant_id"]: max(0, r["quantity"] - r["reserved_quantity"]) for r in StoreProductStock.objects.filter(store=store, product_variant_id__in=variant_ids).values("product_variant_id", "quantity", "reserved_quantity")}
    product_ids = {v.product_id for v in variants}
    names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in=product_ids).values("product_id", "locale_code", "name"):
        names.setdefault(tr["product_id"], {})[tr["locale_code"]] = tr["name"]
    images = variant_image_urls(variants)
    out = []
    for v in variants:
        by_locale = names.get(v.product_id, {})
        out.append({
            "variant_id": str(v.id), "sku": v.sku, "variant_label": _variant_label(v), "image_url": images.get(v.id), "stock": stock.get(v.id, 0),
            "name": by_locale.get(locale) or by_locale.get("uz") or by_locale.get("en") or next(iter(by_locale.values()), v.sku),
        })
    return out


PERIODS = {"today": 0, "7d": 6, "30d": 29}
LOW_STOCK_THRESHOLD = 5


def _period_start(period: str):
    now = timezone.localtime()
    return (now - timedelta(days=PERIODS.get(period, 0))).replace(hour=0, minute=0, second=0, microsecond=0)


def _closed_sales(store: Store, start):
    return SaleModel.objects.filter(branch_id=store.id, completed_at__gte=start).exclude(status__in=[SaleStatus.OPEN.value, SaleStatus.VOIDED.value])


def history(store: Store, locale: str, period: str = "today", status: str | None = None, q: str = "", page: int = 1, page_size: int = 25) -> dict:
    """Closed sales (newest first) with exactly what was bought, who bought it and how it was paid."""
    from apps.identity.infrastructure.models import User

    listing = _closed_sales(store, _period_start(period)).order_by("-completed_at")
    exact_receipt = (q or "").strip()
    if exact_receipt:
        # a scanned receipt QR / a typed receipt number finds that sale whatever its date
        one = SaleModel.objects.filter(branch_id=store.id).filter(Q(receipt_token=exact_receipt) | Q(receipt_number__iexact=exact_receipt)).exclude(status__in=[SaleStatus.OPEN.value, SaleStatus.VOIDED.value])
        if one.exists():
            listing, q = one, ""
    if status in (SaleStatus.COMPLETED.value, SaleStatus.REFUNDED.value):
        listing = listing.filter(status=status)
    elif status == "partial":
        listing = listing.filter(status=SaleStatus.COMPLETED.value).filter(Q(refunded_amount__gt=0) | Q(refunded_coins__gt=0))
    q = (q or "").strip().lstrip("#")
    if q:
        customer_ids = User.objects.filter(Q(full_name__icontains=q) | Q(phone_number__contains=q)).values("id")
        if len(q) >= 3:
            from django.db.models import CharField
            from django.db.models.functions import Cast

            # receipt number ("NZ-000124" / "124"), the e-receipt token (a scanned QR), the short id, or the buyer
            listing = listing.annotate(id_text=Cast("id", CharField())).filter(
                Q(id_text__startswith=q.lower()) | Q(customer_id__in=customer_ids) | Q(receipt_token=q) | Q(receipt_number__iendswith=q.upper().removeprefix("NZ-"))
            )
    total_rows = listing.count()
    rows = list(listing[(page - 1) * page_size: page * page_size])

    lines = list(SaleLineItemModel.objects.filter(sale__in=rows).values("id", "sale_id", "product_variant_id", "quantity", "refunded_quantity", "unit_price_amount"))
    info = {i["variant_id"]: i for i in catalog_items_by_variant(store, locale, list({ln["product_variant_id"] for ln in lines if ln["product_variant_id"]}))}
    customers = dict(User.objects.filter(id__in=[r.customer_id for r in rows if r.customer_id]).values_list("id", "full_name"))
    by_sale: dict = {}
    for ln in lines:
        meta = info.get(str(ln["product_variant_id"]), {})
        by_sale.setdefault(ln["sale_id"], []).append({
            "name": meta.get("name", "—"), "variant_label": meta.get("variant_label"), "image_url": meta.get("image_url"),
            "quantity": ln["quantity"], "unit_price": str(ln["unit_price_amount"]), "line_total": str(ln["unit_price_amount"] * ln["quantity"]),
            "line_id": str(ln["id"]), "refunded_quantity": ln["refunded_quantity"],
        })
    results = []
    for r in rows:
        items = by_sale.get(r.id, [])
        total = sum((Decimal(i["line_total"]) for i in items), Decimal("0"))
        results.append({
            "id": str(r.id), "number": r.receipt_number or "#" + str(r.id)[:8].upper(), "status": r.status, "receipt_token": r.receipt_token,
            "total": str(total), "discount": str(r.discount_amount), "coins_redeemed": str(r.coins_redeemed),
            "paid": str(max(Decimal("0"), total - r.discount_amount - r.coins_redeemed)),
            "payments": r.payments or [], "refunded_value": str(r.refunded_amount + r.refunded_coins),
            "partially_refunded": r.status == SaleStatus.COMPLETED.value and (r.refunded_amount + r.refunded_coins) > 0,
            "item_count": sum(i["quantity"] for i in items), "items": items,
            "payment_method": r.payment_method, "customer": customers.get(r.customer_id) if r.customer_id else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None, "refunded_at": r.refunded_at.isoformat() if r.refunded_at else None,
        })
    return {"period": period, "results": results, "total_count": total_rows, "page": page}


def analytics(store: Store, locale: str, period: str = "today") -> dict:
    """
    Day (by hour) / week / month (by day) sales analytics for the store. Revenue is net:
    catalogue subtotal − discounts − whatever has been returned (coins count as revenue paid in loyalty).
    """
    from apps.pos.infrastructure.models import SaleRefundModel

    start = _period_start(period)
    base = _closed_sales(store, start)
    completed = base.filter(status=SaleStatus.COMPLETED.value)
    rows = _sale_rows(base)
    kept = [r for r in rows if r["status"] == SaleStatus.COMPLETED.value]
    returns = list(SaleRefundModel.objects.filter(sale__branch_id=store.id, created_at__gte=start).values("value"))

    revenue = sum((r["net"] for r in rows), Decimal("0"))
    count = len(kept)
    if period == "today":
        buckets = [{"label": f"{h:02d}", "revenue": Decimal("0"), "count": 0} for h in range(24)]
        for r in rows:
            b = buckets[timezone.localtime(r["completed_at"]).hour]
            b["revenue"] += r["net"]
            b["count"] += 1 if r["status"] == SaleStatus.COMPLETED.value else 0
    else:
        days = PERIODS[period] + 1
        first = timezone.localtime(start).date()
        buckets = [{"label": (first + timedelta(days=i)).strftime("%d.%m"), "date": (first + timedelta(days=i)).isoformat(), "revenue": Decimal("0"), "count": 0} for i in range(days)]
        index = {b["date"]: b for b in buckets}
        for r in rows:
            b = index.get(timezone.localtime(r["completed_at"]).date().isoformat())
            if b:
                b["revenue"] += r["net"]
                b["count"] += 1 if r["status"] == SaleStatus.COMPLETED.value else 0
    peak = max(buckets, key=lambda b: b["revenue"]) if rows else None

    net_qty = Sum(F("quantity") - F("refunded_quantity"))
    top = list(
        SaleLineItemModel.objects.filter(sale__in=completed, product_variant_id__isnull=False)
        .values("product_variant_id").annotate(qty=net_qty, revenue=Sum(F("unit_price_amount") * (F("quantity") - F("refunded_quantity")))).filter(qty__gt=0).order_by("-revenue")[:6]
    )
    top_info = {i["variant_id"]: i for i in catalog_items_by_variant(store, locale, [t["product_variant_id"] for t in top])}
    coins_kept = sum((r["coins_redeemed"] - r["refunded_coins"] for r in rows), Decimal("0"))
    return {
        "period": period,
        "kpis": {
            "revenue": str(revenue), "sales_count": count, "average": str((revenue / count).quantize(Decimal("1")) if count else Decimal("0")),
            "items_sold": sum(r["units"] - (r["units_back"] or 0) for r in rows),
            "cash": str(_by_method(rows, PaymentMethod.CASH.value, net=True)),
            "uzcard": str(_by_method(rows, PaymentMethod.UZCARD.value, net=True)),
            "humo": str(_by_method(rows, PaymentMethod.HUMO.value, net=True)),
            "coins": str(coins_kept),
            "discounts": str(sum((r["discount_amount"] for r in kept), Decimal("0"))),
            "refunds_count": len(returns), "refunded": str(sum((r["value"] for r in returns), Decimal("0"))),
            "customers": len({r["customer_id"] for r in kept if r["customer_id"]}),
        },
        "series": [{"label": b["label"], "revenue": str(b["revenue"]), "count": b["count"]} for b in buckets],
        "peak": {"label": peak["label"], "revenue": str(peak["revenue"])} if peak and peak["revenue"] > 0 else None,
        "top_products": [{**top_info.get(str(t["product_variant_id"]), {}), "quantity": t["qty"], "revenue": str(t["revenue"])} for t in top],
    }


def stock_overview(store: Store, locale: str, q: str = "", status: str = "all") -> dict:
    """Read-only shelf view for the owner: every product the store carries, its selling price and how many are left. Stock itself is managed by NutriZone staff."""
    from apps.products.infrastructure.selectors import bulk_variant_prices

    entries = list(StoreProductStock.objects.filter(store=store).select_related("product_variant"))
    info = {i["variant_id"]: i for i in catalog_items_by_variant(store, locale, [e.product_variant_id for e in entries])}
    prices = bulk_variant_prices([e.product_variant_id for e in entries])
    items = []
    for e in entries:
        meta = info.get(str(e.product_variant_id), {})
        price = prices.get(e.product_variant_id)
        state = "out" if e.available <= 0 else "low" if e.available <= LOW_STOCK_THRESHOLD else "ok"
        items.append({
            "variant_id": str(e.product_variant_id), "name": meta.get("name", e.product_variant.sku), "sku": e.product_variant.sku,
            "variant_label": meta.get("variant_label"), "image_url": meta.get("image_url"),
            "price": price["amount"] if price else None, "stock": e.available, "reserved": e.reserved_quantity, "state": state,
            "stock_value": str(Decimal(price["amount"]) * e.quantity) if price else None, "updated_at": e.updated_at.isoformat(),
        })
    summary = {
        "products": len(items), "units": sum(i["stock"] for i in items),
        "value": str(sum((Decimal(i["stock_value"]) for i in items if i["stock_value"]), Decimal("0"))),
        "ok": sum(1 for i in items if i["state"] == "ok"), "low": sum(1 for i in items if i["state"] == "low"), "out": sum(1 for i in items if i["state"] == "out"),
        "low_threshold": LOW_STOCK_THRESHOLD,
    }
    attention = sorted((i for i in items if i["state"] != "ok"), key=lambda i: i["stock"])[:10]
    q = (q or "").strip().lower()
    if q:
        items = [i for i in items if q in i["name"].lower() or q in i["sku"].lower()]
    if status in ("ok", "low", "out"):
        items = [i for i in items if i["state"] == status]
    items.sort(key=lambda i: (i["stock"], i["name"]))
    return {"summary": summary, "attention": attention, "results": items}


TOP_DAYS = 30


def top_products(store: Store, locale: str, limit: int = 8) -> list[dict]:
    """The kassa's best sellers (units, last TOP_DAYS days) it still has in stock and can price -- the terminal's quick buttons."""
    from apps.products.infrastructure.selectors import bulk_variant_prices
    from apps.stores.infrastructure.models import StockMovement

    since = timezone.now() - timedelta(days=TOP_DAYS)
    ranked = list(StockMovement.objects.filter(store=store, movement_type="sale", created_at__gte=since)
                  .values("product_variant_id").annotate(n=Sum("quantity")).order_by("n")[:limit * 2])  # sales are negative: most units first
    ids = [r["product_variant_id"] for r in ranked]
    sold = {str(r["product_variant_id"]): -r["n"] for r in ranked}
    prices = bulk_variant_prices(ids)
    items = {}
    for i in catalog_items_by_variant(store, locale, ids):
        p = prices.get(uuid.UUID(i["variant_id"]))
        i.update({"price": str(p["amount"]) if p else None, "sellable": bool(p) and i["stock"] > 0, "sold": sold.get(i["variant_id"], 0), "currency": CURRENCY})
        items[i["variant_id"]] = i
    return [items[str(v)] for v in ids if str(v) in items and items[str(v)]["sellable"]][:limit]
