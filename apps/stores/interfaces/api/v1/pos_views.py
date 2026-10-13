"""
Store POS REST API -- `/api/v1/my-store/pos/...`, for the people who sell at a kassa: the store's owner and the
cashiers a superadmin linked to it (pos_cashiers.store_for_user). Every call resolves the kassa from the JWT user;
a sale id from another kassa is a 404. All logic lives in apps/stores/infrastructure/pos_service.py.

Who is selling: the signed-in user -- or, on a shared computer, the cashier the terminal was handed over to with the
kassa PIN (signed token in the X-Pos-Cashier header, see pos_cashiers.issue_token). Opening a shift needs the kassa PIN.
"""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.pos.domain.enums import LIVE_PAYMENT_METHODS, PaymentMethod
from apps.stores.infrastructure import payroll, pos_cashiers
from apps.stores.infrastructure import pos_service as svc
from apps.stores.infrastructure.models import Store
from common.exceptions import PermissionDenied, ValidationFailed
from common.responses import success_response


def _store(request) -> Store:
    """The kassa this user sells at; also fixes who is selling on this request (`_actor`)."""
    store, role = pos_cashiers.store_for_user(request.user.id)
    if store is None:
        raise Http404
    actor = pos_cashiers.cashier_from_token(store, request.headers.get("X-Pos-Cashier")) or request.user.id
    request._pos = {"role": role, "actor": actor}
    pos_cashiers.touch(store, actor)
    return store


def _actor(request):
    return request._pos["actor"]


def _owner_only(request):
    if request._pos["role"] != "owner":
        err = PermissionDenied("Only the store owner sees this.")
        err.code = "OWNER_ONLY"
        raise err


def _locale(request) -> str:
    loc = (request.headers.get("X-Locale") or "uz")[:2]
    return loc if loc in ("uz", "ru", "en") else "uz"


def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ValidationFailed("Invalid id.") from exc


def _int(value, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        if value is None:
            return default
        raise ValidationFailed("Quantity must be a whole number.") from exc


def _sale(request, store, sale):
    return success_response(data=svc.sale_payload(store, sale, _locale(request)))


class PosBase(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]


def _decimal(value, field: str) -> Decimal:
    try:
        d = Decimal(str(value if value not in (None, "") else "0"))
        if not d.is_finite() or d < 0:
            raise InvalidOperation
        return d
    except (InvalidOperation, ValueError) as exc:
        raise ValidationFailed(f"{field} must be a non-negative amount.") from exc


class PosConfigView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Terminal configuration (store, payment methods, current shift)")
    def get(self, request):
        store = _store(request)
        people = pos_cashiers.people(store)
        actor = str(_actor(request))
        me = next((p for p in people if p["id"] == str(request.user.id)), None)
        return success_response(data={
            "session": svc.session_payload(svc.current_session(store)),
            "store": {"id": str(store.id), "name": store.name, "address": store.address, "phone": svc._first_phone(store)},
            "kassa": {"name": pos_cashiers.kassa_name(store), "has_pin": pos_cashiers.has_pin(store), "locked_seconds": pos_cashiers.locked_seconds(store)},
            "role": request._pos["role"],
            "currency": svc.CURRENCY,
            "payment_methods": [{"code": m.value, "live": m in LIVE_PAYMENT_METHODS} for m in PaymentMethod if m not in (PaymentMethod.CARD, PaymentMethod.MIXED)],
            "max_discount_percent": str(svc.MAX_DISCOUNT_PERCENT.normalize()),
            "cashier": next((p for p in people if p["id"] == actor), None) or {"id": actor, "full_name": svc._actor_name(actor)},
            "me": me,
            "cashiers": people,
            # the signed-in cashier's own pay so far this month (base + KPI on their net sales)
            "earnings": payroll.earnings(request.user.id, store) if request._pos["role"] == "cashier" else None,
        })


class PosCatalogView(PosBase):
    @extend_schema(tags=["Store POS"], summary="My store's sellable products (search by name / SKU / barcode)")
    def get(self, request):
        store = _store(request)
        page = max(1, _int(request.query_params.get("page"), 1))
        return success_response(data=svc.catalog(store, _locale(request), q=request.query_params.get("q", ""), page=page, in_stock_only=request.query_params.get("in_stock") == "1"))


class PosCurrentSaleView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Resume my open sale, or open a new one")
    def post(self, request):
        store = _store(request)
        return _sale(request, store, svc.open_sale(store, _actor(request)))


class PosParkedView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Baskets on hold at my kassa")
    def get(self, request):
        return success_response(data={"results": svc.parked_sales(_store(request))})


class PosSaleParkView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Put the basket on hold and start a new one")
    def post(self, request, sale_id):
        store = _store(request)
        return _sale(request, store, svc.park_sale(store, _actor(request), _uuid(sale_id), str(request.data.get("label") or "")))


class PosSaleResumeView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Bring a basket on hold back to the till")
    def post(self, request, sale_id):
        store = _store(request)
        return _sale(request, store, svc.resume_sale(store, _actor(request), _uuid(sale_id)))


class PosSaleView(PosBase):
    @extend_schema(tags=["Store POS"], summary="One sale (receipt data)")
    def get(self, request, sale_id):
        store = _store(request)
        return _sale(request, store, svc._load(store, _uuid(sale_id)))


class PosSaleItemsView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Add a product to the basket (price resolved server-side)")
    def post(self, request, sale_id):
        store = _store(request)
        sale = svc.add_item(store, _actor(request), _uuid(sale_id), _uuid(request.data.get("variant_id")), _int(request.data.get("quantity"), 1),
                            code=str(request.data.get("code") or "")[:64] or None)  # the scanned code: a batch barcode records the batch
        return _sale(request, store, sale)

    @extend_schema(tags=["Store POS"], summary="Empty the basket")
    def delete(self, request, sale_id):
        store = _store(request)
        return _sale(request, store, svc.clear(store, _actor(request), _uuid(sale_id)))


class PosSaleItemView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Set a line's quantity (0 removes it)")
    def patch(self, request, sale_id, line_id):
        store = _store(request)
        return _sale(request, store, svc.set_quantity(store, _actor(request), _uuid(sale_id), _uuid(line_id), _int(request.data.get("quantity"))))

    @extend_schema(tags=["Store POS"], summary="Remove a line")
    def delete(self, request, sale_id, line_id):
        store = _store(request)
        return _sale(request, store, svc.remove_item(store, _actor(request), _uuid(sale_id), _uuid(line_id)))


class PosSaleCustomerView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Attach the buyer (customer_id from search, or phone -- created if new)")
    def post(self, request, sale_id):
        store = _store(request)
        customer_id = request.data.get("customer_id")
        sale = svc.set_customer(store, _actor(request), _uuid(sale_id), request.data.get("phone_number", "") or "", request.data.get("full_name", "") or "", str(_uuid(customer_id)) if customer_id else None)
        return _sale(request, store, sale)

    @extend_schema(tags=["Store POS"], summary="Detach the buyer")
    def delete(self, request, sale_id):
        store = _store(request)
        return _sale(request, store, svc.remove_customer(store, _actor(request), _uuid(sale_id)))


class PosCustomerSearchView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Find a customer (own buyers by name/phone, anyone by exact phone)")
    def get(self, request):
        store = _store(request)
        return success_response(data=svc.customer_search(store, request.query_params.get("q", "")))


class PosSessionView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Current shift")
    def get(self, request):
        return success_response(data=svc.session_payload(svc.current_session(_store(request))))


class PosSessionOpenView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Open the cash register (start of shift)")
    def post(self, request):
        store = _store(request)
        pos_cashiers.verify_pin(store, str(request.data.get("pin") or ""))  # one shared PIN per kassa; no opening float
        session = svc.open_session(store, _actor(request), Decimal("0"), str(request.data.get("note", "") or "")[:200])
        return success_response(data=svc.session_payload(session), status_code=201)


class PosSessionCloseView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Close the cash register (Z-report)")
    def post(self, request):
        store = _store(request)
        session = svc.close_session(store, _actor(request), _decimal(request.data.get("counted_cash"), "counted_cash"), str(request.data.get("note", "") or ""))
        return success_response(data=svc.session_payload(session))


class PosSessionListView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Shift history")
    def get(self, request):
        page = max(1, _int(request.query_params.get("page"), 1))
        return success_response(data=svc.sessions(_store(request), page=page))


class PosAnalyticsView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Day / week / month analytics")
    def get(self, request):
        store = _store(request)
        _owner_only(request)
        return success_response(data=svc.analytics(store, _locale(request), period=request.query_params.get("period", "today")))


class PosStockView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Read-only stock list with prices and low-stock attention list")
    def get(self, request):
        store = _store(request)
        return success_response(data=svc.stock_overview(store, _locale(request), q=request.query_params.get("q", ""), status=request.query_params.get("status", "all")))


class PosSaleCompleteView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Take payment and complete the sale (decrements store stock)")
    def post(self, request, sale_id):
        store = _store(request)
        raw = request.data.get("amount_tendered")
        try:
            tendered = Decimal(str(raw)) if raw not in (None, "") else None
            if tendered is not None and (not tendered.is_finite() or tendered < 0):
                raise InvalidOperation
        except (InvalidOperation, ValueError) as exc:
            raise ValidationFailed("amount_tendered must be a non-negative amount.") from exc
        raw_discount = request.data.get("discount")
        discount = _decimal(raw_discount, "discount") if raw_discount not in (None, "") else Decimal("0")
        sale = svc.complete(
            store, _actor(request), _uuid(sale_id), str(request.data.get("payment_method", "cash")), tendered,
            coins=_int(request.data.get("coins"), 0), discount=discount, discount_reason=str(request.data.get("discount_reason") or ""),
            payments=request.data.get("payments") if isinstance(request.data.get("payments"), list) else None,
        )
        return _sale(request, store, sale)


class PosSaleVoidView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Cancel an open sale")
    def post(self, request, sale_id):
        store = _store(request)
        return _sale(request, store, svc.void(store, _actor(request), _uuid(sale_id)))


def _preview_payload(p: dict) -> dict:
    return {
        "value": str(p["value"]), "amount": str(p["amount"]), "coins": str(p["coins"]), "cashback": p["cashback"], "final": p["final"],
        "split": {m: str(a) for m, a in p["split"].items()}, "lines": [{**ln, "value": str(ln["value"])} for ln in p["lines"]],
    }


class PosSaleRefundView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Return all or part of a completed sale (returns stock, money, coins); preview=true only computes")
    def post(self, request, sale_id):
        store = _store(request)
        items = request.data.get("items")
        if items is not None and not isinstance(items, list):
            raise ValidationFailed("items must be a list of {line_id, quantity}.")
        preview = str(request.data.get("preview", "")).lower() in ("1", "true")
        sale, figures = svc.refund(store, _actor(request), _uuid(sale_id), items=items or None, reason=str(request.data.get("reason") or ""), dry_run=preview)
        if preview:
            return success_response(data={"preview": _preview_payload(figures)})
        return success_response(data={**svc.sale_payload(store, sale, _locale(request)), "refund": _preview_payload(figures)})


class PosHistoryView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Closed sales + day/week/month summary")
    def get(self, request):
        store = _store(request)
        page = max(1, _int(request.query_params.get("page"), 1))
        return success_response(data=svc.history(store, _locale(request), period=request.query_params.get("period", "today"), status=request.query_params.get("status"), q=request.query_params.get("q", ""), page=page))


class PosCashierSwitchView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Hand the terminal to another cashier of this kassa (kassa PIN) -> X-Pos-Cashier token")
    def post(self, request):
        store = _store(request)
        cashier_id = str(_uuid(request.data.get("cashier_id")))
        person = next((p for p in pos_cashiers.people(store) if p["id"] == cashier_id), None)
        if person is None:
            err = ValidationFailed("This person isn't a cashier at this kassa.")
            err.code = "CASHIER_NOT_ALLOWED"
            raise err
        pos_cashiers.verify_pin(store, str(request.data.get("pin") or ""))
        pos_cashiers.touch(store, cashier_id)
        return success_response(data={"token": pos_cashiers.issue_token(store, cashier_id), "cashier": person})


class PosTopView(PosBase):
    @extend_schema(tags=["Store POS"], summary="Quick buttons: the kassa's 8 best sellers (30 days) still in stock")
    def get(self, request):
        store = _store(request)
        return success_response(data={"results": svc.top_products(store, _locale(request))})
