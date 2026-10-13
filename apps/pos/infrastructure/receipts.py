"""
Receipts for completed POS sales -- the printed (thermal) slip and the public e-receipt behind its QR code.

* `assign(sale_id)` gives a sale its receipt identity exactly once, at completion:
  a sequential number from a Postgres sequence ("NZ-000124", never reused, safe
  under concurrent tills) and an unguessable token for the public link.
* `receipt(sale)` is the one receipt shape both the store terminal, the public
  page (`/r/<token>`) and the dashboard render -- so the paper slip, the phone
  and the admin always agree.

The public e-receipt shows only what is printed on the paper slip: the buyer's
first name and a masked phone, never contact details in full.
"""
from __future__ import annotations

import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import connection

from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel
from apps.pos.infrastructure.sales_reports import split_of

SEQUENCE = "pos_receipt_number_seq"
CURRENCY = "UZS"


def assign(sale_id: uuid.UUID) -> tuple[str, str]:
    """Idempotent: a sale that already has its number keeps it (a retried completion never burns a second number)."""
    row = SaleModel.all_objects.filter(id=sale_id).values("receipt_number", "receipt_token").first()
    if row and row["receipt_number"]:
        return row["receipt_number"], row["receipt_token"]
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{SEQUENCE}')")
        n = cursor.fetchone()[0]
    number, token = f"NZ-{n:06d}", secrets.token_urlsafe(12)
    SaleModel.all_objects.filter(id=sale_id, receipt_number__isnull=True).update(receipt_number=number, receipt_token=token)
    row = SaleModel.all_objects.filter(id=sale_id).values("receipt_number", "receipt_token").first()
    return row["receipt_number"], row["receipt_token"]


def public_url(token: str | None) -> str | None:
    """Absolute e-receipt link for places that have no browser origin of their own (dashboard, Telegram)."""
    base = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    return f"{base}/r/{token}" if token and base else None


def mask_phone(phone: str | None) -> str | None:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 7:
        return None
    return f"+{digits[:3]} ** *** {digits[-4:-2]} {digits[-2:]}"


def first_name(full_name: str | None) -> str | None:
    return (full_name or "").strip().split(" ")[0] or None


def _variant_label(variant) -> str | None:
    parts = []
    if variant.weight_value:
        value = int(variant.weight_value) if float(variant.weight_value).is_integer() else variant.weight_value
        parts.append(f"{value} {variant.weight_unit}")
    if variant.package_id and getattr(variant, "package", None):
        parts.append(str(variant.package))
    return " · ".join(parts) or None


def _names(product_ids, locale: str) -> dict:
    from apps.products.infrastructure.models import ProductTranslation

    names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in=set(product_ids)).values("product_id", "locale_code", "name"):
        names.setdefault(tr["product_id"], {})[tr["locale_code"]] = tr["name"]
    return {pid: (by.get(locale) or by.get("uz") or by.get("en") or next(iter(by.values()), None)) for pid, by in names.items()}


def seller_of(sale: SaleModel) -> dict:
    """Who issued the receipt: the partner store for store-terminal sales, NutriZone itself for the dashboard till."""
    from apps.stores.infrastructure.models import Store

    store = Store.objects.filter(id=sale.branch_id).only("name", "address", "city", "phone_numbers").first()
    if store is None:
        from apps.platform.infrastructure.branding import brand_name

        return {"name": brand_name(), "address": None, "phone": None, "store_id": None}
    phones = store.phone_numbers if isinstance(store.phone_numbers, list) else []
    phone = phones[0] if phones else None
    if isinstance(phone, dict):
        phone = phone.get("number") or phone.get("phone")
    return {"name": store.name, "address": ", ".join(x for x in (store.address, store.city) if x) or None, "phone": phone, "store_id": str(store.id)}


def amounts(sale: SaleModel, lines: list | None = None) -> dict:
    """subtotal (catalogue prices) − discount − coins (+ delivery on dashboard sales) = what was paid in money."""
    lines = lines if lines is not None else list(sale.line_items.all())
    subtotal = sum((li.unit_price_amount * li.quantity for li in lines), Decimal("0"))
    discount = sale.discount_amount or Decimal("0")
    coins = sale.coins_redeemed or Decimal("0")
    delivery = sale.delivery_fee_amount or Decimal("0")
    return {"subtotal": subtotal, "discount": discount, "coins": coins, "delivery": delivery, "paid": max(Decimal("0"), subtotal - discount - coins + delivery)}


def receipt(sale: SaleModel, locale: str = "uz", public: bool = True) -> dict:
    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure.models import WalletTransaction
    from apps.products.infrastructure.models import ProductVariant

    lines = list(SaleLineItemModel.objects.filter(sale_id=sale.id))
    names = _names([li.product_id for li in lines], locale)
    variants = {v.id: v for v in ProductVariant.objects.filter(id__in=[li.product_variant_id for li in lines if li.product_variant_id]).select_related("package")}
    items = []
    for li in lines:
        v = variants.get(li.product_variant_id)
        items.append({
            "name": names.get(li.product_id) or (v.sku if v else "—"), "variant_label": _variant_label(v) if v else None, "sku": v.sku if v else None,
            "quantity": li.quantity, "unit_price": str(li.unit_price_amount), "line_total": str(li.unit_price_amount * li.quantity),
            "refunded_quantity": li.refunded_quantity,
        })
    money = amounts(sale, lines)
    customer = User.objects.filter(id=sale.customer_id).only("id", "full_name", "phone_number").first() if sale.customer_id else None
    from apps.stores.infrastructure.models import CashSession, Store
    from apps.stores.infrastructure.pos_cashiers import kassa_name
    from apps.stores.infrastructure.pos_service import _actor_name, shift_number

    cashier = _actor_name(sale.cashier_id) if sale.cashier_id else None
    store = Store.objects.filter(id=sale.branch_id).only("id", "name", "kind").first() if sale.channel == "store" else None
    session = CashSession.objects.filter(id=sale.cash_session_id).first() if sale.cash_session_id else None
    earned = WalletTransaction.objects.filter(order_id=sale.id, kind="earn").values_list("amount", "tier_name").first()
    return {
        "number": sale.receipt_number or "#" + str(sale.id)[:8].upper(),
        "token": sale.receipt_token,
        "status": sale.status,
        "channel": sale.channel,
        "issued_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "refunded_at": sale.refunded_at.isoformat() if sale.refunded_at else None,
        "seller": {k: v for k, v in seller_of(sale).items() if k != "store_id"},
        "cashier": cashier or None,
        "kassa": kassa_name(store) if store else None,
        "shift": shift_number(session) if session else None,
        "items": items,
        "item_count": sum(li.quantity for li in lines),
        "subtotal": str(money["subtotal"]), "discount": str(money["discount"]), "coins": str(money["coins"]),
        "delivery": str(money["delivery"]), "total": str(money["paid"]), "currency": CURRENCY,
        "payment_method": sale.payment_method,
        "payments": [{"method": m, "amount": str(a)} for m, a in split_of(sale.payments, sale.payment_method, money["paid"]).items()],
        "refunds": [
            {"number": r.number, "at": r.created_at.isoformat(), "value": str(r.value), "coins": str(r.coins), "items": sum(int(ln.get("quantity", 0)) for ln in r.lines)}
            for r in sale.refunds.order_by("created_at")
        ],
        "returned": str((sale.refunded_amount or 0) + (sale.refunded_coins or 0)),
        "amount_tendered": str(sale.amount_tendered) if sale.amount_tendered is not None else None,
        "change": str(sale.change_amount) if sale.change_amount is not None else None,
        "customer": {
            "name": first_name(customer.full_name) if public else customer.full_name,
            "phone": mask_phone(customer.phone_number) if public else customer.phone_number,
        } if customer else None,
        "coins_earned": earned[0] if earned else 0,
        "tier": earned[1] if earned else None,
    }


def by_token(token: str) -> SaleModel | None:
    if not token or len(token) > 32:
        return None
    return SaleModel.objects.filter(receipt_token=token, completed_at__isnull=False).first()
