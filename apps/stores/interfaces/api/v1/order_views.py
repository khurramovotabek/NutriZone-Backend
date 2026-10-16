"""
Branch online orders (stores/infrastructure/store_orders.py):

* `GET  /stores/pickup-options?items=<variant>:<qty>,...&lat=&lng=` -- public: branches ranked for a cart (all in stock, nearest).
* `GET  /my-store/orders?scope=active|done|all&q=`                 -- the orders this branch handles (owner and its cashiers).
* `POST /my-store/orders/<number>/action  {action, reason}`        -- confirm / start_processing / ship / deliver / hand_back.
* `GET  /my-store/report?days=7|30|90`                              -- owner only: this branch's speed / outcomes vs the network.
"""
from __future__ import annotations

import uuid

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.stores.infrastructure import pos_cashiers, store_orders
from common.exceptions import ConflictError, PermissionDenied, ValidationFailed
from common.responses import success_response


def _items(raw: str) -> list[tuple]:
    out = []
    for part in (raw or "").split(",")[:50]:
        vid, _, qty = part.partition(":")
        try:
            out.append((uuid.UUID(vid.strip()), max(1, min(int(qty or 1), 999))))
        except (ValueError, TypeError):
            continue
    if not out:
        raise ValidationFailed("items is required: <variant_id>:<qty>,...", details={"fields": [{"field": "items", "code": "REQUIRED"}]})
    return out


def _float(value):
    try:
        v = float(value)
        return v if -180 <= v <= 180 else None
    except (TypeError, ValueError):
        return None


class PickupOptionsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Stores"], summary="Branches to pick a cart up from (in stock first, then nearest)")
    def get(self, request):
        lines = _items(request.query_params.get("items", ""))
        return success_response(data=store_orders.pickup_options(lines, _float(request.query_params.get("lat")), _float(request.query_params.get("lng"))))


def _my_store(request):
    store, role = pos_cashiers.store_for_user(request.user.id)
    if store is None:
        raise Http404
    return store, role


class MyStoreOrdersView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="Online orders my branch handles")
    def get(self, request):
        store, _role = _my_store(request)
        scope = request.query_params.get("scope", "active")
        return success_response(data=store_orders.orders_for(store, scope if scope in ("active", "done", "all") else "active", (request.query_params.get("q") or "").strip()[:60]))


class MyStoreOrderActionView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="Move one of my branch's orders a step forward (or hand it back)")
    def post(self, request, number: str):
        store, role = _my_store(request)
        action = str(request.data.get("action") or "")
        if action == "hand_back" and role != "owner":
            err = PermissionDenied("Only the store owner can hand an order back.")
            err.code = "OWNER_ONLY"
            raise err
        user = getattr(request, "identity", None) or request.user
        label = getattr(user, "full_name", "") or ""
        try:
            data = store_orders.act(store, number, action, actor_id=request.user.id, actor_label=label, reason=str(request.data.get("reason") or ""))
        except store_orders.StoreOrderError as exc:
            err = ConflictError(exc.message)
            err.code = exc.code
            raise err from exc
        return success_response(data=data)


class MyStoreReportView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="My branch's online-order performance (owner only)")
    def get(self, request):
        from apps.stores.infrastructure.branch_report import my_branch_report

        store, role = _my_store(request)
        if role != "owner":
            err = PermissionDenied("Only the store owner can see the branch report.")
            err.code = "OWNER_ONLY"
            raise err
        days = request.query_params.get("days")
        return success_response(data=my_branch_report(store, int(days) if days in ("7", "30", "90") else 30))


class MyStoreReceiptsView(APIView):
    """`GET /api/v1/my-store/receipts?days=1|7|30&q=` -- the branch's receipts (kassa sales, refunds, online orders it
    handed out) with today's totals; each opens / reprints the QR e-receipt. Customer phones are masked."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="My branch's receipts")
    def get(self, request):
        from django.db.models import Count, Q, Sum
        from django.utils import timezone

        from apps.receipts.infrastructure.models import Receipt

        store, _role = _my_store(request)
        days = request.query_params.get("days")
        days = int(days) if days in ("1", "7", "30") else 7
        since = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) - timezone.timedelta(days=days - 1)
        rows = Receipt.objects.filter(store_id=store.id, issued_at__gte=since)
        q = (request.query_params.get("q") or "").strip()[:40]
        if q:
            match = Q(number__icontains=q) | Q(order_number__icontains=q) | Q(customer_name__icontains=q)
            rows = rows.filter(match | Q(customer_phone__endswith=q) if q.isdigit() else match)
        today = Receipt.objects.filter(store_id=store.id, issued_at__gte=timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)).exclude(status="cancelled")
        agg = {k: today.filter(kind=k).aggregate(n=Count("id"), total=Sum("total")) for k in ("sale", "refund")}

        def mask(phone: str) -> str:
            return f"{phone[:6]}***{phone[-2:]}" if len(phone) > 8 else phone

        return success_response(data={
            "days": days,
            "today": {"sales": agg["sale"]["n"], "revenue": str(agg["sale"]["total"] or 0), "refunds": agg["refund"]["n"], "refunded": str(agg["refund"]["total"] or 0)},
            "receipts": [{
                "number": r.number, "token": r.token, "source": r.source, "kind": r.kind, "status": r.status, "total": str(r.total),
                "payment_method": r.payment_method, "issued_at": r.issued_at.isoformat(), "order_number": r.order_number,
                "customer": r.customer_name, "phone": mask(r.customer_phone), "cashier": (r.data or {}).get("cashier") or r.created_by,
                "items": (r.data or {}).get("item_count") or len((r.data or {}).get("items") or []), "fiscal": bool(r.fiscal_number),
            } for r in rows.order_by("-issued_at")[:200]],
        })
