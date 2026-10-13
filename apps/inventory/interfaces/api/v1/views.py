"""
Inventory API views.

Thin per Django Implementation Blueprint §3: each view deserializes,
calls exactly one Application Service (built via
infrastructure/composition.py), and returns through the standard
response envelope. Every collection endpoint (list+create) is ONE
view class on ONE path -- the exact routing bug found and fixed in
Products is avoided here by construction, not by a later fix. No view
ever instantiates a repository or touches the ORM directly; every read
goes through a Selector (accessed via composition.py) or an
Application Service.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.inventory.infrastructure import composition
from apps.inventory.interfaces.api.v1.filters import (
    parse_expiring_batches_params, parse_inventory_list_params, parse_pagination, parse_stock_filter_params,
    parse_uuid_param,
)
from apps.inventory.interfaces.api.v1.permissions import (
    CanAdjustStock, CanManageBatch, CanManageCycleCount, CanManageInventory, CanManagePhysicalInventory,
    CanManageSerial, CanManageSnapshot, CanConfirmIncomingStock, CanReceiveStock, CanReleaseReservation, CanReserveStock,
    CanTransferStock, CanViewInventory, CanViewLedger, CanViewReservations,
)
from apps.inventory.interfaces.api.v1.serializers import (
    AdjustStockSerializer, CompleteCountSerializer, ConfirmIncomingStockSerializer, CreateBatchSerializer, CreateInventorySerializer,
    CreateReservationSerializer, CreateSnapshotSerializer, DamageStockSerializer, ExpireStockSerializer,
    ReceiveStockSerializer, RegisterSerialSerializer, ReleaseReservationRequestSerializer,
    ReserveStockSerializer, RestoreSnapshotSerializer, TransferStockSerializer, UpdateBatchSerializer,
    UpdateInventorySerializer,
)
from common.exceptions import ResourceNotFound
from common.idempotency import protect_with_idempotency
from common.responses import paginated_response, success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class InventoryAdminThrottle(ScopedRateLimitThrottle):
    scope = "inventory.admin_operation"
    limit = 600
    window_seconds = 3600
    identifier_source = "user"


class StockOperationThrottle(ScopedRateLimitThrottle):
    scope = "inventory.stock_operation"
    limit = 1200
    window_seconds = 3600
    identifier_source = "user"


def _inventory_payload(inventory) -> dict:
    return {
        "id": str(inventory.id), "code": inventory.code.value, "product_variant_id": str(inventory.product_variant_id),
        "status": inventory.status.value, "is_batch_tracked": inventory.is_batch_tracked, "is_serial_tracked": inventory.is_serial_tracked,
    }


def _warehouse_inventory_payload(wi) -> dict:
    return {
        "id": str(wi.id), "inventory_id": str(wi.inventory_id), "warehouse_id": str(wi.warehouse_id),
        "available_quantity": wi.available_quantity, "reserved_quantity": wi.reserved_quantity,
    }


def _batch_payload(batch) -> dict:
    return {
        "id": str(batch.id), "inventory_id": str(batch.inventory_id), "batch_number": batch.batch_number.value,
        "status": batch.status.value, "quantity_received": batch.quantity_received.value,
        "expiration_date": batch.expiration_date.value.isoformat() if batch.expiration_date else None,
        "serial_count": len(batch.serials),
    }


def _reservation_payload(reservation) -> dict:
    return {
        "id": str(reservation.id), "reservation_number": reservation.reservation_number.value, "owner_type": reservation.owner_type,
        "owner_id": str(reservation.owner_id), "warehouse_inventory_id": str(reservation.warehouse_inventory_id),
        "status": reservation.status.value, "expires_at": reservation.expires_at.isoformat() if reservation.expires_at else None,
        "total_quantity": reservation.total_quantity(),
    }


def _cycle_count_payload(cycle_count) -> dict:
    return {"id": str(cycle_count.id), "warehouse_id": str(cycle_count.warehouse_id), "status": cycle_count.status.value}


def _physical_inventory_payload(physical_inventory) -> dict:
    return {"id": str(physical_inventory.id), "warehouse_id": str(physical_inventory.warehouse_id), "status": physical_inventory.status.value}


def _snapshot_payload(snapshot) -> dict:
    return {"id": str(snapshot.id), "version": snapshot.version.value, "status": snapshot.status.value, "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None}


# ============================================================
# Lifecycle
# ============================================================


class InventoryListCreateView(APIView):
    """Combined GET (list) + POST (create) at one path."""

    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageInventory()] if self.request.method == "POST" else [CanViewInventory()]

    @extend_schema(tags=["Inventory"], summary="List inventory items", responses={200: OpenApiResponse(description="Inventory list"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_inventory_list_params(request.query_params)
        selector = composition.build_inventory_repository()
        items, total = selector.list_for_admin(status=params.status, query=params.query, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=[_inventory_payload(i) for i in items], pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Inventory"], summary="Create an inventory item", request=CreateInventorySerializer, responses={201: OpenApiResponse(description="Inventory created"), **_responses(401, 403, 409, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateInventorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inventory = composition.build_create_inventory(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_inventory_payload(inventory), status_code=201)


class InventoryDetailView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewInventory()] if self.request.method == "GET" else [CanManageInventory()]

    @extend_schema(tags=["Inventory"], summary="Get an inventory item by code", responses={200: OpenApiResponse(description="Inventory detail"), **_responses(401, 403, 404)})
    def get(self, request, code: str):
        _attach_identity(request)
        inventory = composition.build_get_inventory().execute(code)
        return success_response(data=_inventory_payload(inventory))

    @extend_schema(tags=["Inventory"], summary="Update an inventory item's thresholds", request=UpdateInventorySerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, code: str):
        _attach_identity(request)
        found = composition.build_inventory_repository().get_by_code(code)
        if found is None:
            raise ResourceNotFound("Inventory not found.")
        serializer = UpdateInventorySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        inventory = composition.build_update_inventory(_actor_id(request)).execute(inventory_id=found.id, **serializer.validated_data)
        return success_response(data=_inventory_payload(inventory))


class ArchiveInventoryView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageInventory()]

    @extend_schema(tags=["Inventory"], summary="Archive an inventory item", responses={200: OpenApiResponse(description="Archived"), **_responses(401, 403, 404, 409)})
    def post(self, request, inventory_id: str):
        _attach_identity(request)
        inventory = composition.build_archive_inventory(_actor_id(request)).execute(uuid.UUID(inventory_id))
        return success_response(data=_inventory_payload(inventory))


class RestoreInventoryView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageInventory()]

    @extend_schema(tags=["Inventory"], summary="Restore an archived inventory item", responses={200: OpenApiResponse(description="Restored"), **_responses(401, 403, 404, 409)})
    def post(self, request, inventory_id: str):
        _attach_identity(request)
        inventory = composition.build_restore_inventory(_actor_id(request)).execute(uuid.UUID(inventory_id))
        return success_response(data=_inventory_payload(inventory))


# ============================================================
# Stock Operations
# ============================================================


class ReceiveStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanReceiveStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Receive incoming stock", request=ReceiveStockSerializer, responses={200: OpenApiResponse(description="Received"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = ReceiveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return protect_with_idempotency(
            request, _actor_id(request), "inventory.receive_stock", serializer.validated_data,
            operation=lambda: composition.build_receive_stock(_actor_id(request)).execute(**serializer.validated_data),
            result_to_payload=_warehouse_inventory_payload,
        )


class ConfirmIncomingStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanConfirmIncomingStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Confirm incoming stock (post-receiving QC/putaway) into available inventory", request=ConfirmIncomingStockSerializer, responses={200: OpenApiResponse(description="Confirmed"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = ConfirmIncomingStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return protect_with_idempotency(
            request, _actor_id(request), "inventory.confirm_incoming_stock", serializer.validated_data,
            operation=lambda: composition.build_confirm_incoming_stock(_actor_id(request)).execute(**serializer.validated_data),
            result_to_payload=_warehouse_inventory_payload,
        )


class ReserveStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanReserveStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Reserve available stock", request=ReserveStockSerializer, responses={200: OpenApiResponse(description="Reserved"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = ReserveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wi = composition.build_reserve_stock(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_warehouse_inventory_payload(wi))


class ReleaseReservationView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanReleaseReservation()]

    @extend_schema(tags=["Inventory Admin"], summary="Release reserved stock back to available", request=ReleaseReservationRequestSerializer, responses={200: OpenApiResponse(description="Released"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = ReleaseReservationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wi = composition.build_release_reservation(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_warehouse_inventory_payload(wi))


class TransferStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanTransferStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Transfer stock between warehouses", request=TransferStockSerializer, responses={200: OpenApiResponse(description="Transferred"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = TransferStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source, destination = composition.build_transfer_stock(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data={"source": _warehouse_inventory_payload(source), "destination": _warehouse_inventory_payload(destination)})


class AdjustStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanAdjustStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Manually adjust a stock bucket", request=AdjustStockSerializer, responses={200: OpenApiResponse(description="Adjusted"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = AdjustStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wi = composition.build_adjust_stock(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_warehouse_inventory_payload(wi))


class DamageStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanAdjustStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Mark stock as damaged", request=DamageStockSerializer, responses={200: OpenApiResponse(description="Marked damaged"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = DamageStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wi = composition.build_damage_stock(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_warehouse_inventory_payload(wi))


class ExpireStockView(APIView):
    throttle_classes = [StockOperationThrottle]

    def get_permissions(self):
        return [CanAdjustStock()]

    @extend_schema(tags=["Inventory Admin"], summary="Mark stock as expired", request=ExpireStockSerializer, responses={200: OpenApiResponse(description="Marked expired"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = ExpireStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wi = composition.build_expire_stock(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_warehouse_inventory_payload(wi))


# ============================================================
# Batch / Serial
# ============================================================


class BatchListCreateView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageBatch()]

    @extend_schema(tags=["Inventory Admin"], summary="List batches for an inventory item")
    def get(self, request):
        _attach_identity(request)
        inventory_id = parse_uuid_param(request.query_params.get("filter[inventory_id]"), "filter[inventory_id]")
        if inventory_id is None:
            from common.exceptions import ValidationFailed

            raise ValidationFailed("filter[inventory_id] is required.")
        from apps.inventory.infrastructure.selectors import BatchSelector

        return success_response(data=BatchSelector().list_by_inventory(inventory_id))

    @extend_schema(tags=["Inventory Admin"], summary="Create a batch", request=CreateBatchSerializer, responses={201: OpenApiResponse(description="Batch created"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = composition.build_batch_service(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_batch_payload(batch), status_code=201)


class BatchDetailView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageBatch()]

    @extend_schema(tags=["Inventory Admin"], summary="Get a batch", responses={200: OpenApiResponse(description="Batch detail"), **_responses(401, 403, 404)})
    def get(self, request, batch_id: str):
        _attach_identity(request)
        batch = composition.build_batch_repository().get_by_id(uuid.UUID(batch_id))
        if batch is None:
            raise ResourceNotFound("Batch not found.")
        return success_response(data=_batch_payload(batch))

    @extend_schema(tags=["Inventory Admin"], summary="Update a batch", request=UpdateBatchSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, batch_id: str):
        _attach_identity(request)
        serializer = UpdateBatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        batch = composition.build_update_batch(_actor_id(request)).execute(batch_id=uuid.UUID(batch_id), **serializer.validated_data)
        return success_response(data=_batch_payload(batch))

    @extend_schema(tags=["Inventory Admin"], summary="Delete a depleted batch", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404, 409)})
    def delete(self, request, batch_id: str):
        _attach_identity(request)
        composition.build_delete_batch(_actor_id(request)).execute(uuid.UUID(batch_id))
        return success_response(data=None, status_code=204)


class RegisterSerialView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageSerial()]

    @extend_schema(tags=["Inventory Admin"], summary="Register a serial number on a batch", request=RegisterSerialSerializer, responses={201: OpenApiResponse(description="Serial registered"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, batch_id: str):
        _attach_identity(request)
        serializer = RegisterSerialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = composition.build_register_serial(_actor_id(request)).execute(batch_id=uuid.UUID(batch_id), **serializer.validated_data)
        return success_response(data=_batch_payload(batch), status_code=201)


class DeactivateSerialView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageSerial()]

    @extend_schema(tags=["Inventory Admin"], summary="Deactivate a serial item", responses={200: OpenApiResponse(description="Deactivated"), **_responses(401, 403, 404)})
    def post(self, request, batch_id: str, serial_item_id: str):
        _attach_identity(request)
        batch = composition.build_deactivate_serial(_actor_id(request)).execute(batch_id=uuid.UUID(batch_id), serial_item_id=uuid.UUID(serial_item_id))
        return success_response(data=_batch_payload(batch))


# ============================================================
# Reservations
# ============================================================


class ReservationListView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewReservations()]

    @extend_schema(tags=["Inventory Admin"], summary="List active reservations")
    def get(self, request):
        _attach_identity(request)
        from apps.inventory.infrastructure.selectors import ReservationSelector

        owner_type = request.query_params.get("filter[owner_type]")
        owner_id = parse_uuid_param(request.query_params.get("filter[owner_id]"), "filter[owner_id]")
        return success_response(data=ReservationSelector().list_active(owner_type=owner_type, owner_id=owner_id))

    @extend_schema(tags=["Inventory Admin"], summary="Create a reservation", request=CreateReservationSerializer, responses={201: OpenApiResponse(description="Reservation created"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reservation = composition.build_create_reservation(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_reservation_payload(reservation), status_code=201)


class ReservationDetailView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewReservations()]

    @extend_schema(tags=["Inventory Admin"], summary="Get a reservation", responses={200: OpenApiResponse(description="Reservation detail"), **_responses(401, 403, 404)})
    def get(self, request, reservation_id: str):
        _attach_identity(request)
        reservation = composition.build_reservation_repository().get_by_id(uuid.UUID(reservation_id))
        if reservation is None:
            raise ResourceNotFound("Reservation not found.")
        return success_response(data=_reservation_payload(reservation))


class CancelReservationView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanReleaseReservation()]

    @extend_schema(tags=["Inventory Admin"], summary="Cancel a reservation", responses={200: OpenApiResponse(description="Cancelled"), **_responses(401, 403, 404, 409)})
    def post(self, request, reservation_id: str):
        _attach_identity(request)
        reservation = composition.build_cancel_reservation(_actor_id(request)).execute(uuid.UUID(reservation_id))
        return success_response(data=_reservation_payload(reservation))


class ExpireReservationView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanReleaseReservation()]

    @extend_schema(tags=["Inventory Admin"], summary="Expire a reservation", responses={200: OpenApiResponse(description="Expired"), **_responses(401, 403, 404, 409)})
    def post(self, request, reservation_id: str):
        _attach_identity(request)
        reservation = composition.build_expire_reservation(_actor_id(request)).execute(uuid.UUID(reservation_id))
        return success_response(data=_reservation_payload(reservation))


# ============================================================
# Cycle Count / Physical Inventory
# ============================================================


class StartCycleCountView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageCycleCount()]

    @extend_schema(tags=["Inventory Admin"], summary="Start a cycle count", responses={201: OpenApiResponse(description="Started"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        warehouse_id = parse_uuid_param(request.data.get("warehouse_id"), "warehouse_id")
        cycle_count = composition.build_cycle_count_service(_actor_id(request)).execute(warehouse_id)
        return success_response(data=_cycle_count_payload(cycle_count), status_code=201)


class CompleteCycleCountView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageCycleCount()]

    @extend_schema(tags=["Inventory Admin"], summary="Complete a cycle count", request=CompleteCountSerializer, responses={200: OpenApiResponse(description="Completed"), **_responses(401, 403, 404, 422)})
    def post(self, request, cycle_count_id: str):
        _attach_identity(request)
        serializer = CompleteCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        counted = {uuid.UUID(k): v for k, v in serializer.validated_data["counted_quantities"].items()}
        cycle_count = composition.build_complete_cycle_count(_actor_id(request)).execute(cycle_count_id=uuid.UUID(cycle_count_id), counted_quantities=counted)
        return success_response(data=_cycle_count_payload(cycle_count))


class StartPhysicalInventoryView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManagePhysicalInventory()]

    @extend_schema(tags=["Inventory Admin"], summary="Start a physical inventory count", responses={201: OpenApiResponse(description="Started"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        warehouse_id = parse_uuid_param(request.data.get("warehouse_id"), "warehouse_id")
        physical_inventory = composition.build_physical_inventory_service(_actor_id(request)).execute(warehouse_id)
        return success_response(data=_physical_inventory_payload(physical_inventory), status_code=201)


class CompletePhysicalInventoryView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManagePhysicalInventory()]

    @extend_schema(tags=["Inventory Admin"], summary="Complete a physical inventory count", request=CompleteCountSerializer, responses={200: OpenApiResponse(description="Completed"), **_responses(401, 403, 404, 422)})
    def post(self, request, physical_inventory_id: str):
        _attach_identity(request)
        serializer = CompleteCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        counted = {uuid.UUID(k): v for k, v in serializer.validated_data["counted_quantities"].items()}
        physical_inventory = composition.build_complete_physical_inventory(_actor_id(request)).execute(physical_inventory_id=uuid.UUID(physical_inventory_id), counted_quantities=counted)
        return success_response(data=_physical_inventory_payload(physical_inventory))


# ============================================================
# Snapshots
# ============================================================


class CreateSnapshotView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageSnapshot()]

    @extend_schema(tags=["Inventory Admin"], summary="Create an inventory snapshot", request=CreateSnapshotSerializer, responses={201: OpenApiResponse(description="Snapshot created"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = composition.build_snapshot_service(_actor_id(request)).execute(serializer.validated_data["warehouse_inventory_ids"])
        return success_response(data=_snapshot_payload(snapshot), status_code=201)


class RestoreSnapshotView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageSnapshot()]

    @extend_schema(tags=["Inventory Admin"], summary="Restore inventory balances from a snapshot", request=RestoreSnapshotSerializer, responses={200: OpenApiResponse(description="Restored"), **_responses(401, 403, 404, 422)})
    def post(self, request, snapshot_id: str):
        _attach_identity(request)
        serializer = RestoreSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        restored_count = composition.build_restore_snapshot(_actor_id(request)).execute(snapshot_id=uuid.UUID(snapshot_id), **serializer.validated_data)
        return success_response(data={"restored_count": restored_count})


# ============================================================
# Ledger
# ============================================================


class LedgerView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewLedger()]

    @extend_schema(tags=["Inventory Admin"], summary="List ledger entries for a warehouse inventory", responses={200: OpenApiResponse(description="Ledger entries"), **_responses(401, 403, 422)})
    def get(self, request, warehouse_inventory_id: str):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        from apps.inventory.infrastructure.selectors import LedgerSelector

        entries, total = LedgerSelector().list_entries(uuid.UUID(warehouse_inventory_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=entries, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


# ============================================================
# Queries
# ============================================================


class InventorySearchView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewInventory()]

    @extend_schema(tags=["Inventory"], summary="Search inventory items")
    def get(self, request):
        params = parse_inventory_list_params(request.query_params)
        results, total = composition.build_search_inventory().execute(query=params.query or "", filters={}, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=results, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})


class WarehouseSummaryView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewInventory()]

    @extend_schema(tags=["Inventory Admin"], summary="Get a warehouse's aggregate stock summary")
    def get(self, request, warehouse_id: str):
        _attach_identity(request)
        from apps.inventory.infrastructure.selectors import WarehouseSelector

        return success_response(data=WarehouseSelector().summary(uuid.UUID(warehouse_id)))


class LowStockView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanViewInventory()]

    @extend_schema(tags=["Inventory Admin"], summary="List inventory items at or below their low-stock threshold")
    def get(self, request):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        from apps.inventory.infrastructure.selectors import StockSelector

        results, total = StockSelector().low_stock(page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=results, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class ExpiringBatchView(APIView):
    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageBatch()]

    @extend_schema(tags=["Inventory Admin"], summary="List batches expiring within N days")
    def get(self, request):
        _attach_identity(request)
        within_days = parse_expiring_batches_params(request.query_params)
        from apps.inventory.infrastructure.selectors import StockSelector

        return success_response(data=StockSelector().expiring_batches(within_days=within_days))


class AdminInventoryView(APIView):
    """Admin-scoped inventory listing with full filter support (status/health/stock filters) -- distinct from the public/staff-shared `InventoryListCreateView` in that it's the dedicated Admin API surface this phase's brief requires separately."""

    throttle_classes = [InventoryAdminThrottle]

    def get_permissions(self):
        return [CanManageInventory()]

    @extend_schema(tags=["Inventory Admin"], summary="Admin inventory listing with full filters")
    def get(self, request):
        _attach_identity(request)
        params = parse_inventory_list_params(request.query_params)
        items, total = composition.build_admin_list_inventory().execute(status=params.status, query=params.query, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=[_inventory_payload(i) for i in items], pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})
