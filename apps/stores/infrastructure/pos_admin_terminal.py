"""
Dashboard → POS → POS terminal: the ONLINE kassa, on the same engine as the branch tills (stores.pos_service).

Branch kassas sell from the storefront's own POS terminal (their cashiers are customer accounts linked to the kassa);
this Dashboard till only rings up online sales, from the main warehouse's stock (pos_cashiers.online_kassa) -- so the
staff never picks a branch. Opening the shift asks for an optional note and then the online kassa's PIN; there is no
opening float to type: the Z-report counts what was taken in the shift.

Identity: sales carry the staff member's stable uuid5 as the cashier (separate basket per staff member, name resolved
by sales_reports._staff_uuid_map); the shift stores the staff member's name (CashSession.opened_by_name).
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _t

from apps.pos.domain.enums import LIVE_PAYMENT_METHODS, PaymentMethod
from apps.stores.infrastructure import pos_cashiers
from apps.stores.infrastructure import pos_service as svc
from apps.stores.infrastructure.models import Store
from common.exceptions import DomainException, ValidationFailed


def staff_cashier_id(user) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"nutrizone-admin-staff-{user.pk}")


def _staff_name(user) -> str:
    return user.get_full_name() or user.get_username()


def _locale() -> str:
    lang = (get_language() or "uz")[:2]
    return lang if lang in ("uz", "ru", "en") else "uz"


def _guard(request):
    if not (request.user.is_active and request.user.is_staff and request.user.has_perm("pos.view_salemodel")):
        raise PermissionDenied


def _store() -> Store:
    store = pos_cashiers.online_kassa()
    if store is None:
        raise ValidationFailed(_t("The online kassa needs an active main warehouse -- create one in Warehouse."))
    return store


def _store_info(store) -> dict:
    return {"id": str(store.id), "name": pos_cashiers.kassa_name(store), "location": store.name, "address": store.address, "phone": svc._first_phone(store)}


def top_products(store, limit: int = 8) -> list:
    return svc.top_products(store, _locale(), limit)


def _body(request) -> dict:
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def _ok(data, status=200):
    return JsonResponse({"success": True, "data": data}, status=status)


def _err(exc, status=409):
    code = getattr(exc, "code", None) or exc.__class__.__name__
    return JsonResponse({"success": False, "error": {"code": code, "message": str(exc), "details": getattr(exc, "details", None) or {}}},
                        status=getattr(exc, "http_status", status))


def _dec(value, field) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value).replace(" ", ""))
        if not d.is_finite() or d < 0:
            raise InvalidOperation
        return d
    except (InvalidOperation, ValueError) as exc:
        raise ValidationFailed(f"{field} must be a non-negative amount.") from exc


def _uuid(v):
    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError) as exc:
        raise ValidationFailed("Invalid id.") from exc


# ---------------------------------------------------------------- page


def terminal_view(request):
    _guard(request)
    config = {
        "cashier": _staff_name(request.user),
        "currency": svc.CURRENCY,
        "max_discount_percent": str(svc.MAX_DISCOUNT_PERCENT.normalize()),
        "payment_methods": [m.value for m in PaymentMethod if m in LIVE_PAYMENT_METHODS],
        "urls": {"api": reverse("admin:nz_pos2_api", args=["__"]), "sales": reverse("admin:pos_salemodel_changelist"),
                 "sale": reverse("admin:pos_salemodel_change", args=["00000000-0000-0000-0000-000000000000"]),
                 "receipt": reverse("admin:nz_pos2_receipt", args=["00000000-0000-0000-0000-000000000000"]),
                 "shifts": reverse("admin:stores_cashsession_changelist"), "cashiers": reverse("admin:stores_storecashier_changelist")},
    }
    return render(request, "admin/pos/terminal.html", {**admin.site.each_context(request), "title": _t("Onlayn kassa"), "config": config, "i18n": i18n()})


def i18n() -> dict:
    t = _t
    return {
        "shiftClosed": t("The kassa is closed"), "shiftClosedHint": t("Open the shift to start selling. No cash count is needed -- the Z-report counts what was taken in the shift."),
        "openShift": t("Open the kassa"), "closeShift": t("Close the shift"), "kassa": t("Kassa"), "now": t("Now"),
        "openNote": t("Note (optional)"), "openNotePh": t("e.g. who is on duty today"), "openPinHint": t("The kassa PIN is asked after you press the button."),
        "enterKassaPin": t("Enter the kassa PIN"), "shiftOpened": t("The kassa is open"), "setPin": t("Set the PIN"),
        "pinNotSet": t("This kassa has no PIN yet -- ask the administrator to set it."),
        "search": t("Product name, SKU or barcode -- scan anywhere"), "scanReady": t("Ready to scan"), "inStockOnly": t("In stock only"),
        # scan → cart panel (right column): Uzbek source strings, ru/en in locale/
        "scanTitle": t("Skaner → savatga"), "scanPriceTitle": t("Narx tekshirish"), "scanMode": t("Skaner rejimi"), "scanModeAdd": t("Savatga"), "scanModePrice": t("Narx"),
        "scanPh": t("Shtrix-kodni skanerlang — darhol savatga"), "scanPricePh": t("Skanerlang — narx va qoldiq (savatga qo'shilmaydi)"),
        "scanQty": t("Keyingi skaner necha dona qo'shadi"), "scanUndo": t("Oxirgi skanni bekor qilish"), "scanPriceOnly": t("faqat narx"),
        "scanNotFound": t("bu kod bo'yicha mahsulot topilmadi"), "expiredBatch": t("Muddati o'tgan partiya — sotib bo'lmaydi"),
        "searchLeft": t("Qidiruv: nom, SKU yoki shtrix-kod"),
        "basket": t("Basket"), "emptyBasket": t("The basket is empty"), "emptyBasketHint": t("Scan a barcode or tap a product."),
        "customer": t("Customer"), "addCustomer": t("Add customer (coins)"), "customerPh": t("Phone or name…"), "newCustomer": t("New customer"),
        "fullName": t("Full name"), "remove": t("Remove"), "clear": t("Clear"), "subtotal": t("Subtotal"), "discount": t("Discount"),
        "coins": t("Coins"), "total": t("To pay"), "pay": t("Payment"), "pcs": t("pcs"), "som": t("so'm"), "stock": t("in stock"),
        "noPrice": t("no price"), "outOfStock": t("Out of stock"), "added": t("Added"), "batch": t("Batch"),
        "cash": t("Cash"), "uzcard": "Uzcard", "humo": "Humo", "split": t("Split payment"), "tendered": t("Cash received"), "changeDue": t("Change"),
        "discountReason": t("Discount reason"), "discountMax": t("At most %s%% of the basket"), "useCoins": t("Pay with coins"), "balance": t("balance"),
        "complete": t("Complete sale"), "cancel": t("Cancel"), "back": t("Back"), "voidSale": t("Cancel this basket"), "newSale": t("New sale"),
        "done": t("Sale completed"), "printReceipt": t("Print receipt"), "openSale": t("Open in Sales"), "receiptNo": t("Receipt"),
        "shift": t("Shift"), "shiftSales": t("sales"), "shiftSalesTitle": t("Sales count"), "shiftCash": t("cash in drawer"), "counted": t("Counted cash (so'm)"), "expected": t("Expected"),
        "difference": t("Difference"), "closeNote": t("Note (optional)"), "recent": t("Today's sales"), "noRecent": t("No sales yet in this shift."),
        "error": t("Something went wrong. Please try again."), "parts": t("Parts must add up to the amount due"), "keys": t("F2 qidiruv · F3 skaner · F4 to'lov · +/− oxirgi skan"),
        "earned": t("Coins earned"), "seller": t("Seller"), "online": t("Online"), "offline": t("Offline -- check the connection"),
        "pinWrong": t("Wrong PIN -- try again."), "pinLocked": t("Too many wrong PINs -- wait a few minutes."),
        "autoPrint": t("Auto print"), "autoPrintHint": t("Print the receipt on the thermal printer after every sale"),
        "autoPrintOn": t("Receipts print automatically"), "autoPrintOff": t("Automatic printing off"), "top": t("Best sellers"),
        "receiptSent": t("The e-receipt was sent to the customer (inbox and Telegram)."),
    }


# ---------------------------------------------------------------- API


def api(request, action: str):
    """One JSON endpoint per terminal action, all on stores.pos_service."""
    _guard(request)
    cashier = staff_cashier_id(request.user)
    staff = _staff_name(request.user)
    b = _body(request) if request.method == "POST" else {}
    try:
        store = _store()
        session = svc.current_session(store)
        if action == "state":
            sale = svc.sale_payload(store, svc.open_sale(store, cashier), _locale()) if session else None
            return _ok({"session": svc.session_payload(session), "store": _store_info(store), "has_pin": pos_cashiers.has_pin(store),
                        "sale": sale, "top": top_products(store) if session else []})
        if action == "top":
            return _ok({"top": top_products(store)})
        if action == "open_shift":
            pos_cashiers.verify_pin(store, str(b.get("pin") or ""))
            s = svc.open_session(store, None, Decimal(0), note=str(b.get("note") or "")[:200], by_name=staff, online=True)
            return _ok({"session": svc.session_payload(s), "sale": svc.sale_payload(store, svc.open_sale(store, cashier), _locale())})
        if action == "close_shift":
            s = svc.close_session(store, None, _dec(b.get("counted_cash"), "counted_cash") or Decimal(0), note=str(b.get("note") or ""), by_name=staff, actor_id=cashier)
            return _ok({"session": svc.session_payload(s)})
        if action == "shift_totals":
            return _ok({"session": svc.session_payload(session)})
        if action == "catalog":
            return _ok(svc.catalog(store, _locale(), q=request.GET.get("q", ""), page=max(1, int(request.GET.get("page") or 1)), in_stock_only=request.GET.get("in_stock") == "1"))
        if action == "customers":
            return _ok({"results": svc.customer_search(store, request.GET.get("q", ""))})
        if action == "recent":
            return _ok(svc.history(store, _locale(), period="today", page=1, page_size=15))
        sale_id = _uuid(b.get("sale_id") or request.GET.get("sale_id"))
        if action == "add":
            sale = svc.add_item(store, cashier, sale_id, _uuid(b.get("variant_id")), int(b.get("quantity") or 1), code=(str(b.get("code") or "")[:64] or None))
        elif action == "qty":
            sale = svc.set_quantity(store, cashier, sale_id, _uuid(b.get("line_id")), int(b.get("quantity") or 0))
        elif action == "remove":
            sale = svc.remove_item(store, cashier, sale_id, _uuid(b.get("line_id")))
        elif action == "clear":
            sale = svc.clear(store, cashier, sale_id)
        elif action == "set_customer":
            sale = svc.set_customer(store, cashier, sale_id, str(b.get("phone_number") or ""), str(b.get("full_name") or ""), str(b.get("customer_id")) if b.get("customer_id") else None)
        elif action == "remove_customer":
            sale = svc.remove_customer(store, cashier, sale_id)
        elif action == "void":
            svc.void(store, cashier, sale_id)
            sale = svc.open_sale(store, cashier)
        elif action == "complete":
            sale = svc.complete(
                store, cashier, sale_id, str(b.get("payment_method") or "cash"), _dec(b.get("amount_tendered"), "amount_tendered"),
                coins=int(b.get("coins") or 0), discount=_dec(b.get("discount"), "discount") or Decimal(0), discount_reason=str(b.get("discount_reason") or ""),
                payments=b.get("payments") if isinstance(b.get("payments"), list) else None,
            )
            done = svc.sale_payload(store, sale, _locale())
            nxt = svc.open_sale(store, cashier)
            return _ok({"done": done, "sale": svc.sale_payload(store, nxt, _locale()), "session": svc.session_payload(svc.current_session(store))})
        else:
            return _err(ValidationFailed(f"Unknown action {action}"), 404)
        return _ok({"sale": svc.sale_payload(store, sale, _locale())})
    except DomainException as exc:
        return _err(exc)
    except (ValueError, Store.DoesNotExist) as exc:
        return _err(ValidationFailed(str(exc)), 422)


# ---------------------------------------------------------------- thermal receipt


def receipt_view(request, sale_id):
    """
    The paper slip for a thermal printer (80 mm, or 58 mm with ?w=58): no admin chrome, monospace-friendly,
    the same receipt data the e-receipt shows (pos.receipts.receipt). ?print=1 opens the print dialog at once --
    with Chrome started as `--kiosk-printing` it prints silently to the default (thermal) printer.
    """
    _guard(request)
    from django.http import Http404

    from apps.pos.infrastructure import receipts
    from apps.pos.infrastructure.models import SaleModel

    sale = SaleModel.objects.filter(id=sale_id).first()
    if sale is None:
        raise Http404
    rc = receipts.receipt(sale, _locale(), public=False)
    store = Store.objects.filter(id=sale.branch_id).first()
    from apps.platform.infrastructure.branding import brand_name

    from zoneinfo import ZoneInfo

    width = 58 if request.GET.get("w") == "58" else 80
    return render(request, "admin/pos/thermal_receipt.html", {
        "rc": rc, "store": store, "brand": brand_name(), "width": width, "autoprint": request.GET.get("print") == "1",
        "issued": sale.completed_at.astimezone(ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M") if sale.completed_at else "",
        "has_discount": Decimal(rc["discount"] or 0) > 0, "has_coins": Decimal(rc["coins"] or 0) > 0, "has_change": Decimal(rc["change"] or 0) > 0,
        "lines": len(rc["items"]),
        "e_receipt": receipts.public_url(sale.receipt_token) if sale.receipt_token else None,
        "phone": svc._first_phone(store) if store else None,
        "methods": {"cash": _t("Cash"), "uzcard": "Uzcard", "humo": "Humo", "card": _t("Card")},
    })
