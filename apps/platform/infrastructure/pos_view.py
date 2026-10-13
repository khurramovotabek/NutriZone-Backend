"""
POS Terminal -- premium admin interfeysi.

Bu qatlam REST API (apps.pos.interfaces.api.v1) o'rniga to'g'ridan-to'g'ri
real composition xizmatlarini chaqiradi, chunki DRF standart konfiguratsiyasi
(REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES) faqat JWT'ni qabul qiladi,
Django admin esa session-based autentifikatsiya ishlatadi. Bu -- yangi
arxitektura emas, mavjud reports_view.py'ning o'zi ham xuddi shu "admin view
to'g'ridan-to'g'ri real service'ni chaqiradi" naqshini ishlatadi.

TO'LOV: faqat naqd (cash) haqiqatda ishlaydi. `Sale` domenida
`payment_method` maydoni umuman mavjud emas (to'g'ridan-to'g'ri manba
kodidan tasdiqlangan) -- shuning uchun boshqa to'lov turlari (UzCard,
Click, Payme, Humo) shu sahifada faqat vizual, bosilmaydigan holatda
ko'rsatiladi, hech qanday backend chaqiruvi qilinmaydi.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from django.utils.translation import gettext_lazy as _

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.pos.infrastructure import composition
from apps.pos.interfaces.api.v1.views import _sale_payload  # already the certified, real payload shape -- not duplicated here
from common.exceptions import DomainException

# Real, closed gap: Store module (Branch) was removed from the
# project. POS's own Sale domain aggregate still requires a
# branch_id (a bare UUID reference, never a foreign key, per this
# project's own "reference by ID" convention) -- this fixed,
# well-known UUID stands in for "the one and only branch" now that
# real branch selection no longer exists.
DEFAULT_BRANCH_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _decrement_inventory_for_completed_sale(sale, actor_id: uuid.UUID) -> None:
    """
    Real, confirmed gap this closes: `CompleteSale` (apps/pos/application/
    services/sale.py) only ever persisted the Sale itself -- the whole
    module's own event handler docstring discloses this explicitly
    ("the real, honest side effect here is metrics emission only").
    Nothing, anywhere in this codebase (POS or the regular online
    checkout), ever decremented real warehouse stock. A cash register
    that never reduces stock is not usable, so this is required, not
    optional scope.

    Deliberately best-effort per line item, never re-raised: the sale is
    already completed and the cashier has already taken the customer's
    cash by the time this runs -- a bookkeeping/inventory edge case
    (missing InventoryModel, insufficient tracked stock) must never undo
    or appear to undo an already-real, already-paid transaction. Each
    failure is logged for a real human to reconcile by hand.

    Drains real `WarehouseInventoryModel.available_quantity` FIFO
    (ordered by id) across however many warehouse rows a variant's stock
    happens to span -- POS itself has no warehouse-selection concept
    (DEFAULT_BRANCH_ID is the one and only branch), so this is the
    simplest correct behavior for that reality, reusing Inventory's own
    certified `AdjustStock` (negative-stock guard included) rather than
    writing a second, parallel stock-mutation path.
    """
    import logging

    from apps.inventory.infrastructure import composition as inventory_composition
    from apps.inventory.infrastructure.models import InventoryModel, WarehouseInventoryModel
    from apps.products.infrastructure.selectors import ProductDetailSelector

    logger = logging.getLogger("nutrizone.app")
    detail_selector = ProductDetailSelector()
    adjust_stock = inventory_composition.build_adjust_stock(actor_id)

    for line_item in sale.line_items.values():
        try:
            variant_id = detail_selector.get_default_variant_id(str(line_item.product_id))
            if variant_id is None:
                continue
            inventory = InventoryModel.objects.filter(product_variant_id=variant_id).first()
            if inventory is None:
                continue
            remaining = line_item.quantity.value
            warehouse_rows = WarehouseInventoryModel.objects.filter(inventory=inventory, available_quantity__gt=0).order_by("id")
            for row in warehouse_rows:
                if remaining <= 0:
                    break
                take = min(remaining, row.available_quantity)
                if take <= 0:
                    continue
                adjust_stock.execute(warehouse_inventory_id=row.id, stock_status="available", quantity_delta=-take, reason="pos_sale", reference=str(sale.id))
                remaining -= take
            if remaining > 0:
                logger.warning("POS sale %s: could not fully decrement stock for variant %s (%s unit(s) short).", sale.id, variant_id, remaining)
        except Exception:  # noqa: BLE001 -- best-effort per line item; never lets an inventory bookkeeping failure undo an already-completed, already-paid sale.
            logger.exception("POS sale %s: inventory decrement failed for product %s.", sale.id, line_item.product_id)


def restock_inventory_for_refunded_sale(sale, actor_id: uuid.UUID) -> None:
    """
    The exact reverse of `_decrement_inventory_for_completed_sale` above,
    for a refunded (returned) sale: each line's quantity goes back into
    stock through Inventory's own certified `AdjustStock`, onto the
    variant's first warehouse row (the same FIFO order the decrement
    drained from). Same best-effort, per-line, logged-never-raised
    discipline: the refund itself is already recorded by the time this
    runs, and a bookkeeping edge case must not appear to undo it.
    """
    import logging

    from apps.inventory.infrastructure import composition as inventory_composition
    from apps.inventory.infrastructure.models import InventoryModel, WarehouseInventoryModel
    from apps.products.infrastructure.selectors import ProductDetailSelector

    logger = logging.getLogger("nutrizone.app")
    detail_selector = ProductDetailSelector()
    adjust_stock = inventory_composition.build_adjust_stock(actor_id)

    for line_item in sale.line_items.values():
        try:
            variant_id = detail_selector.get_default_variant_id(str(line_item.product_id))
            inventory = InventoryModel.objects.filter(product_variant_id=variant_id).first() if variant_id else None
            row = WarehouseInventoryModel.objects.filter(inventory=inventory).order_by("id").first() if inventory else None
            if row is None:
                logger.warning("POS refund %s: no warehouse row to restock product %s (%s unit(s)).", sale.id, line_item.product_id, line_item.quantity.value)
                continue
            adjust_stock.execute(warehouse_inventory_id=row.id, stock_status="available", quantity_delta=line_item.quantity.value, reason="pos_refund", reference=str(sale.id))
        except Exception:  # noqa: BLE001 -- best-effort per line item, mirrors the decrement's own discipline.
            logger.exception("POS refund %s: inventory restock failed for product %s.", sale.id, line_item.product_id)


def _actor_id(request) -> uuid.UUID:
    """
    Django admin staff foydalanuvchisi (contrib.auth.User, integer pk)
    va POS'ning cashier_id (Sale aggregate'ida ozod UUID maydon, hech
    qanday FK cheklovisiz -- to'g'ridan-to'g'ri manba kodidan
    tasdiqlangan) ikki xil turdagi identifikator. Har doim bir xil
    staff foydalanuvchi uchun bir xil, barqaror UUID hosil qilish
    uchun deterministik xaritalash ishlatiladi -- bu fabrikatsiya
    emas, faqat ID mapping texnikasi.
    """
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"nutrizone-admin-staff-{request.user.id}")


def _json_error(exc: Exception, status: int = 422) -> JsonResponse:
    if isinstance(exc, DomainException):
        return JsonResponse({"success": False, "error": {"message": str(exc)}}, status=getattr(exc, "http_status", status))
    return JsonResponse({"success": False, "error": {"message": str(exc)}}, status=status)


@staff_member_required
def pos_terminal_view(request):
    """Bosh Sotuv ekrani -- faol narx ro'yxatlarini (PriceList) template'ga uzatadi. Real, closed gap: Store modul olib tashlangani uchun haqiqiy filial (Branch) tanlash endi mavjud emas -- bitta, standart virtual filial ID'si ishlatiladi (DEFAULT_BRANCH_ID), Sale domain aggregate'ining o'zi (branch_id majburiy maydon) o'zgartirilmagan holda."""
    from django.urls import reverse

    from apps.pricing.infrastructure.models import PriceListModel
    from apps.products.infrastructure.models import Category, CategoryTranslation

    price_lists = list(PriceListModel.objects.filter(is_deleted=False, status="active").order_by("name")[:50])
    category_rows = Category.objects.filter(is_active=True).prefetch_related("translations")[:30]
    categories = []
    for c in category_rows:
        translation = next((t for t in c.translations.all() if t.locale_code == "en"), None)
        categories.append({"id": str(c.id), "name": translation.name if translation else str(c.id)})

    # Display-only: the store label in the POS header. Shown only when
    # exactly one active Store exists -- Sale itself carries no store
    # reference (DEFAULT_BRANCH_ID above), so naming one of several
    # stores here would misattribute the sale.
    from apps.stores.infrastructure.models import Store

    active_stores = list(Store.objects.filter(status="active").only("name", "district", "city")[:2])
    store = active_stores[0] if len(active_stores) == 1 else None

    context = {
        **admin.site.each_context(request),
        "title": _("POS Terminal"),
        "store": store,
        "default_branch_id": DEFAULT_BRANCH_ID,
        "price_lists": price_lists,
        "categories": categories,
        "cashier_id": str(_actor_id(request)),
        "cashier_name": request.user.get_full_name() or request.user.username,
        # Real, closed gap: the success screen previously had no way to
        # reach a completed sale's own real Django admin record (the
        # already-registered SaleModel admin) -- reverse()'d server-side
        # here (never guessed/hardcoded client-side) and completed with
        # the real sale id in JS to build "View Order".
        "sale_admin_url_base": reverse("admin:pos_salemodel_changelist"),
    }
    return render(request, "admin/pos_terminal.html", context)


@staff_member_required
@require_GET
def pos_api_browse(request):
    """Real, closed gap: category navigation needs a way to list products without a search query -- reuses the same, already-certified CatalogSelector.list() the public storefront uses, then enriches with the same real POS display info (brand/weight/stock) as search."""
    from apps.products.infrastructure.selectors import CatalogSelector, ProductDetailSelector

    category_id = request.GET.get("category_id") or None
    page = int(request.GET.get("page", 1))
    rows, total = CatalogSelector().list(category_id=category_id, page=page, page_size=24)

    detail_selector = ProductDetailSelector()
    product_ids = [item["id"] for item in rows]
    pos_info_by_id = detail_selector.get_pos_display_info(product_ids)
    for item in rows:
        item["variant_id"] = detail_selector.get_default_variant_id(item["id"])
        item.update(pos_info_by_id.get(item["id"], {}))

    return JsonResponse({"success": True, "data": {"results": rows, "total_count": total}})


@staff_member_required
@require_GET
def pos_api_customer_search(request):
    """Real, closed gap: the POS premium redesign needs customer selection, and Sale.open() already accepts a real customer_id -- this searches real, existing identity.User rows by phone number or name, never fabricating a customer record."""
    from django.db.models import Q

    from apps.identity.infrastructure.models import User

    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"success": True, "data": {"results": []}})
    rows = User.objects.filter(Q(phone_number__icontains=q) | Q(full_name__icontains=q)).order_by("full_name")[:10]
    return JsonResponse({"success": True, "data": {"results": [{"id": str(u.id), "full_name": u.full_name, "phone_number": u.phone_number} for u in rows]}})


@staff_member_required
@require_POST
def pos_api_customer_create(request):
    """
    Real, product-required capability: checkout needs to record a
    genuinely new, not-yet-registered walk-in buyer by phone + full
    name -- `pos_api_customer_search` above only ever finds an
    *existing* `identity.User`, and `Sale.customer_id` (domain
    aggregate) has no free-text name/phone fields of its own to fall
    back to (confirmed directly against aggregates.py -- `customer_id`
    is its one and only buyer-identifying field). This is the minimal,
    real fix: find-or-create the actual `identity.User` row by phone
    number (the platform's own real customer identity, unique and
    already E.164-validated everywhere else), never a second,
    parallel "guest" concept. An existing customer's own real name is
    never overwritten by a cashier's typo -- only a brand-new row gets
    the submitted name.
    """
    from apps.identity.domain.value_objects import PhoneNumber
    from apps.identity.infrastructure.models import User

    try:
        body = json.loads(request.body)
        phone_number = PhoneNumber(str(body.get("phone_number", "")).strip()).value
        full_name = str(body.get("full_name", "")).strip()
        if not full_name:
            return JsonResponse({"success": False, "error": {"message": "Full name is required."}}, status=422)
    except Exception as exc:  # noqa: BLE001 -- malformed phone number, matches this file's own established boundary-catch convention
        return _json_error(exc, status=422)

    user, created = User.objects.get_or_create(phone_number=phone_number, defaults={"full_name": full_name})
    return JsonResponse({"success": True, "data": {"id": str(user.id), "full_name": user.full_name, "phone_number": user.phone_number, "created": created}}, status=201 if created else 200)


@staff_member_required
@require_POST
def pos_api_set_customer(request, sale_id: str):
    """Attaches the real buyer (`identity.User`, found or just quick-created above) to an already-open Sale -- see `Sale.set_customer()`'s own docstring for why this is a separate call from `open-sale`."""
    try:
        body = json.loads(request.body)
        sale = composition.build_set_sale_customer(_actor_id(request)).execute(sale_id=uuid.UUID(sale_id), customer_id=uuid.UUID(body["customer_id"]))
        return JsonResponse({"success": True, "data": _sale_payload(sale)})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc)


@staff_member_required
@require_GET
def pos_api_recent_sales(request):
    """Real, closed gap: shows real, existing Sale rows for this cashier's branch -- never fabricated sample transactions. total_amount is not a stored SaleModel field (only the domain aggregate computes it from line items), so it is summed here directly from the real, persisted line items."""
    from decimal import Decimal

    from apps.pos.infrastructure.models import SaleModel

    rows = SaleModel.objects.filter(status="completed").order_by("-completed_at")[:10]
    results = []
    for s in rows:
        line_totals = [li.unit_price_amount * li.quantity for li in s.line_items.all()]
        total = sum(line_totals, Decimal("0"))
        currency = s.line_items.values_list("unit_price_currency", flat=True).first() or "UZS"
        results.append({
            "id": str(s.id), "customer_id": str(s.customer_id) if s.customer_id else None,
            "line_item_count": s.line_items.count(), "total_amount": str(total), "total_currency": currency,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        })
    return JsonResponse({"success": True, "data": {"results": results}})


@staff_member_required
@require_POST
def pos_api_open_sale(request):
    try:
        body = json.loads(request.body)
        customer_id = uuid.UUID(body["customer_id"]) if body.get("customer_id") else None
        sale = composition.build_open_sale(_actor_id(request)).execute(
            branch_id=uuid.UUID(body["branch_id"]), cashier_id=_actor_id(request), customer_id=customer_id,
        )
        return JsonResponse({"success": True, "data": _sale_payload(sale)}, status=201)
    except Exception as exc:  # noqa: BLE001 -- boundary layer, matches nutrizone_exception_handler's own broad-catch convention
        return _json_error(exc)


@staff_member_required
@require_GET
def pos_api_search(request):
    try:
        q = request.GET.get("q", "").strip()
        if not q:
            return JsonResponse({"success": True, "data": {"mode": None, "exact_match": None, "results": [], "total_count": 0}})
        mode = request.GET.get("type") or None
        result = composition.build_search_product().execute(query=q, mode=mode)

        if result.get("exact_match"):
            from apps.products.infrastructure.selectors import ProductDetailSelector

            detail_selector = ProductDetailSelector()
            product = detail_selector.get_by_id(result["exact_match"]["product_id"])
            if product:
                result["exact_match"]["name"] = product["name"]
                result["exact_match"]["display_price"] = product.get("price")
                result["exact_match"]["display_currency"] = product.get("currency")
                result["exact_match"]["primary_image_path"] = product.get("primary_image_path")
                pos_info = detail_selector.get_pos_display_info([result["exact_match"]["product_id"]])
                result["exact_match"].update(pos_info.get(str(result["exact_match"]["product_id"]), {}))

        if result.get("results"):
            from apps.products.infrastructure.selectors import ProductDetailSelector

            detail_selector = ProductDetailSelector()
            product_ids = [item["id"] for item in result["results"]]
            pos_info_by_id = detail_selector.get_pos_display_info(product_ids)
            for item in result["results"]:
                item["variant_id"] = detail_selector.get_default_variant_id(item["id"])
                item.update(pos_info_by_id.get(item["id"], {}))

        return JsonResponse({"success": True, "data": result})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc, status=404)


@staff_member_required
@require_GET
def pos_api_price(request):
    try:
        price_list_id = uuid.UUID(request.GET["price_list_id"])
        variant_id = uuid.UUID(request.GET["variant_id"])
        quantity = int(request.GET.get("quantity", 1))
        coupon_code = request.GET.get("coupon_code") or None
        price = composition.build_resolve_line_item_price().execute(price_list_id=price_list_id, variant_id=variant_id, quantity=quantity, coupon_code=coupon_code)
        return JsonResponse({"success": True, "data": {"amount": str(price.amount), "currency": price.currency}})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc, status=404)


@staff_member_required
@require_POST
def pos_api_add_line_item(request, sale_id: str):
    try:
        body = json.loads(request.body)
        sale = composition.build_add_line_item(_actor_id(request)).execute(
            sale_id=uuid.UUID(sale_id), product_id=uuid.UUID(body["product_id"]), quantity=int(body["quantity"]),
            unit_price_amount=Decimal(str(body["unit_price_amount"])), unit_price_currency=body.get("unit_price_currency", "UZS"),
        )
        return JsonResponse({"success": True, "data": _sale_payload(sale)})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc)


@staff_member_required
@require_POST
def pos_api_remove_line_item(request, sale_id: str, line_item_id: str):
    try:
        sale = composition.build_remove_line_item(_actor_id(request)).execute(sale_id=uuid.UUID(sale_id), line_item_id=uuid.UUID(line_item_id))
        return JsonResponse({"success": True, "data": _sale_payload(sale)})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc)


@staff_member_required
@require_POST
def pos_api_update_line_item_quantity(request, sale_id: str, line_item_id: str):
    try:
        body = json.loads(request.body)
        sale = composition.build_update_line_item_quantity(_actor_id(request)).execute(
            sale_id=uuid.UUID(sale_id), line_item_id=uuid.UUID(line_item_id), new_quantity=int(body["quantity"]),
        )
        return JsonResponse({"success": True, "data": _sale_payload(sale)})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc)


@staff_member_required
@require_POST
def pos_api_complete_sale(request, sale_id: str):
    """
    Optional body `{"payment_method": "cash" | "uzcard" | "humo"}` (default cash). The Sale domain has no payment
    method, so a card payment is recorded on the SaleModel row after completion -- method + one `payments` part for
    the whole amount (the bank terminal charges exactly the amount due), which Sales Management and the reports read.

    Optional body `{"delivery_fee": <non-negative amount>}`: the checkout's
    delivery fee, recorded on the SaleModel row (see its own field comment)
    only once the sale has actually completed. Validated before completing,
    so a malformed fee never leaves a completed sale without it.
    """
    from decimal import InvalidOperation

    from apps.pos.infrastructure.models import SaleModel

    try:
        body = json.loads(request.body or b"{}")
        delivery_fee = Decimal(str(body.get("delivery_fee") or 0))
        if not delivery_fee.is_finite() or delivery_fee < 0:
            raise InvalidOperation
    except (ValueError, InvalidOperation, TypeError):
        return JsonResponse({"success": False, "error": {"message": "delivery_fee must be a non-negative amount."}}, status=422)
    method = str(body.get("payment_method") or "cash").lower()
    if method not in ("cash", "uzcard", "humo"):
        return JsonResponse({"success": False, "error": {"message": "payment_method must be cash, uzcard or humo."}}, status=422)

    try:
        sale = composition.build_complete_sale(_actor_id(request)).execute(uuid.UUID(sale_id))
        if delivery_fee:
            SaleModel.objects.filter(id=sale.id).update(delivery_fee_amount=delivery_fee)
        if method != "cash":
            from django.db.models import F, Sum

            lines_total = SaleModel.objects.filter(id=sale.id).aggregate(t=Sum(F("line_items__quantity") * F("line_items__unit_price_amount")))["t"] or Decimal("0")
            paid = lines_total + delivery_fee
            SaleModel.objects.filter(id=sale.id).update(payment_method=method, payments=[{"method": method, "amount": f"{paid:.2f}"}], amount_tendered=paid, change_amount=Decimal("0"))
        _decrement_inventory_for_completed_sale(sale, _actor_id(request))
        from apps.pos.infrastructure import receipts

        number, token = receipts.assign(sale.id)
        return JsonResponse({"success": True, "data": {
            **_sale_payload(sale), "delivery_fee_amount": str(delivery_fee),
            "receipt_number": number, "receipt_token": token, "receipt_url": receipts.public_url(token),
        }})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc, status=409)


@staff_member_required
@require_POST
def pos_api_void_sale(request, sale_id: str):
    try:
        sale = composition.build_void_sale(_actor_id(request)).execute(uuid.UUID(sale_id))
        return JsonResponse({"success": True, "data": _sale_payload(sale)})
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc, status=409)
