"""
Branch "Mahsulot qabul qilish" REST API -- `/api/v1/my-store/transfers/...`, for the people of a branch (its owner and
its cashiers, pos_cashiers.store_for_user): the transfers coming to the branch, scan-and-count receiving, partial or
final confirmation, and the waybill. Read-only for transfers the branch sent.

Every rule stays in transfer_service (state machine, row locks, posting into the batches the units left from,
discrepancy reasons); settling a shortage / excess remains a Dashboard manager's decision.
"""
from __future__ import annotations

import uuid

from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.stores.infrastructure import pos_cashiers, transfer_read, transfer_service
from apps.stores.infrastructure.models import DiscrepancyReason, StockTransfer, Store
from common.exceptions import ValidationFailed
from common.responses import success_response

RECEIVE_MODES = ("save", "partial", "final")
HISTORY_LIMIT = 50


def _store(request) -> Store:
    store, role = pos_cashiers.store_for_user(request.user.id)
    if store is None:
        raise Http404
    request._branch_role = role
    return store


def _actor(request) -> str:
    from apps.identity.infrastructure.models import User

    row = User.objects.filter(id=request.user.id).values("full_name", "phone_number").first() or {}
    name = row.get("full_name") or row.get("phone_number") or "Filial"
    return f"{name} ({'filial egasi' if request._branch_role == 'owner' else 'kassir'})"[:150]


def _transfer(store: Store, transfer_id) -> StockTransfer:
    try:
        tid = uuid.UUID(str(transfer_id))
    except (TypeError, ValueError) as exc:
        raise Http404 from exc
    t = StockTransfer.objects.select_related("source", "destination").filter(Q(destination=store) | Q(source=store), pk=tid).first()
    if t is None:
        raise Http404
    return t


def can_receive(store: Store, t: StockTransfer) -> bool:
    return t.destination_id == store.id and t.status in transfer_service.RECEIVABLE and not t.discrepancy_open


def _detail(store: Store, t: StockTransfer) -> dict:
    data = transfer_read.payload(t)
    data["direction"] = "incoming" if t.destination_id == store.id else "outgoing"
    data["can_receive"] = can_receive(store, t)
    data["reasons"] = [{"code": c, "label": str(label)} for c, label in DiscrepancyReason.choices]
    return data


def _row(t: StockTransfer, store: Store) -> dict:
    return {
        "id": str(t.pk), "number": t.number, "status": t.status, "status_label": t.get_status_display(), "discrepancy_open": t.discrepancy_open,
        "direction": "incoming" if t.destination_id == store.id else "outgoing",
        "source": transfer_read.location(t.source), "destination": transfer_read.location(t.destination),
        "created_at": transfer_read.local(t.created_at), "dispatched_at": transfer_read.local(t.dispatched_at), "dispatched_by": t.dispatched_by,
        "received_at": transfer_read.local(t.received_at), "received_by": t.received_by,
        "lines": t._lines, "sent": t._sent or 0, "received": t._recv or 0, "value": str(t._value or 0),
    }


class TransferBase(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]


class MyStoreTransfersView(TransferBase):
    @extend_schema(tags=["Store transfers"], summary="Transfers coming to this branch (incoming) or its recent history")
    def get(self, request):
        from django.db.models import F

        store = _store(request)
        scope = request.query_params.get("scope", "incoming")
        q = (request.query_params.get("q") or "").strip()
        mine = StockTransfer.objects.filter(Q(destination=store) | Q(source=store))
        incoming = StockTransfer.objects.filter(destination=store, status__in=transfer_service.RECEIVABLE)
        qs = incoming if scope == "incoming" else mine.exclude(pk__in=incoming.values("pk")).exclude(status="draft")
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(items__name__icontains=q) | Q(items__barcode=q) | Q(items__sku__iexact=q)).distinct()
        qs = (qs.select_related("source", "destination")
              .annotate(_lines=Count("items", distinct=True), _sent=Sum("items__dispatched_quantity"), _recv=Sum("items__received_quantity"),
                        _value=Sum(F("items__unit_cost") * F("items__dispatched_quantity")))
              .order_by("-dispatched_at", "-created_at"))
        counts = {
            "incoming": incoming.filter(discrepancy_open=False).count(),  # what the branch still has to receive (the nav badge)
            "receiving": incoming.filter(status__in=("receiving", "partial"), discrepancy_open=False).count(),
            "discrepancy": incoming.filter(discrepancy_open=True).count(),
        }
        return success_response(data={"results": [_row(t, store) for t in qs[:HISTORY_LIMIT]], "counts": counts, "store": transfer_read.location(store)})


class MyStoreTransferDetailView(TransferBase):
    @extend_schema(tags=["Store transfers"], summary="One transfer of this branch with its lines, batches and history")
    def get(self, request, transfer_id):
        store = _store(request)
        return success_response(data=_detail(store, _transfer(store, transfer_id)))


class MyStoreTransferReceiveView(TransferBase):
    @extend_schema(tags=["Store transfers"], summary="Save counts, receive partially, or confirm the receipt (absolute counts per line)")
    def post(self, request, transfer_id):
        store = _store(request)
        t = _transfer(store, transfer_id)
        if t.destination_id != store.id:
            raise Http404  # a branch only receives what was sent to it
        mode = str(request.data.get("mode") or "save")
        if mode not in RECEIVE_MODES:
            raise ValidationFailed("Unknown receiving mode.")
        counts, reasons = request.data.get("counts") or {}, request.data.get("reasons") or None
        if not isinstance(counts, dict) or (reasons is not None and not isinstance(reasons, dict)):
            raise ValidationFailed("counts must be {line_id: quantity}.")
        try:
            counts = {str(k): int(v) for k, v in counts.items()}
        except (TypeError, ValueError) as exc:
            raise ValidationFailed("Counts must be whole numbers.") from exc
        if any(v < 0 for v in counts.values()):
            raise ValidationFailed("Counts can't be negative.")
        actor = _actor(request)
        if mode == "save":
            transfer_service.save_receiving(t.pk, actor, counts, reasons)
        else:
            transfer_service.confirm_receipt(t.pk, actor, counts=counts, reasons=reasons, final=mode == "final")
        return success_response(data=_detail(store, StockTransfer.objects.select_related("source", "destination").get(pk=t.pk)))


class MyStoreTransferLookupView(TransferBase):
    @extend_schema(tags=["Store transfers"], summary="A scanned barcode / SKU -> the product (and the batch an extra batch barcode names)")
    def get(self, request):
        store = _store(request)
        data = transfer_read.lookup(request.query_params.get("code", ""), store)
        if data is None:
            from common.exceptions import ResourceNotFound

            raise ResourceNotFound("No product with this barcode.")
        return success_response(data=data)


class MyStoreTransferDocumentView(TransferBase):
    @extend_schema(tags=["Store transfers"], summary="The waybill (.xlsx)")
    def get(self, request, transfer_id):
        from apps.platform.infrastructure.branding import brand_name
        from apps.stores.infrastructure import transfer_export

        store = _store(request)
        t = _transfer(store, transfer_id)
        response = HttpResponse(transfer_export.workbook(t, brand_name()), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{transfer_export.filename(t)}"'
        return response
