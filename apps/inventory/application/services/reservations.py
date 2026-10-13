"""
Reservation Application Services: CreateReservation, CancelReservation,
ExpireReservation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.inventory.application.ports import ReservationRepository, WarehouseInventoryRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.aggregates import Reservation
from apps.inventory.domain.entities import ReservationItem
from apps.inventory.domain.services import ReservationPolicy
from apps.inventory.domain.value_objects import ReservationNumber, StockQuantity
from common.exceptions import ResourceNotFound


class CreateReservation:
    def __init__(self, reservation_repo: ReservationRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._reservation_repo = reservation_repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, reservation_number: str, owner_type: str, owner_id: uuid.UUID, warehouse_inventory_id: uuid.UUID, quantity: int, expires_in_minutes: int | None = None) -> Reservation:
        wi = self._warehouse_inventory_repo.get_by_id(warehouse_inventory_id)
        if wi is None:
            raise ResourceNotFound("Warehouse inventory not found.")

        ReservationPolicy.assert_sufficient_available(quantity, wi.available_quantity)

        expires_at = django_timezone.now() + timedelta(minutes=expires_in_minutes or ReservationPolicy.default_expiry_minutes())
        reservation = Reservation(id=uuid.uuid4(), reservation_number=ReservationNumber(reservation_number), owner_type=owner_type, owner_id=owner_id, warehouse_inventory_id=warehouse_inventory_id, expires_at=expires_at)
        reservation.add_item(ReservationItem(id=uuid.uuid4(), quantity=StockQuantity(quantity)))

        wi.reserve(StockQuantity(quantity), reservation_number, django_timezone.now())
        self._warehouse_inventory_repo.save(wi)
        saved = self._reservation_repo.save(reservation)

        from apps.inventory.domain.events import ReservationCreated

        self._ctx.stage_events([("ReservationCreated", ReservationCreated(reservation_id=saved.id, reservation_number=reservation_number, warehouse_inventory_id=warehouse_inventory_id).to_payload())])
        self._ctx.audit().created(entity_type="Reservation", entity_id=str(saved.id), after={"reservation_number": reservation_number, "quantity": quantity})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("reservations_created_total")
        return saved


class CancelReservation:
    def __init__(self, reservation_repo: ReservationRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._reservation_repo = reservation_repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = self._reservation_repo.get_by_id(reservation_id)
        if reservation is None:
            raise ResourceNotFound("Reservation not found.")

        event = reservation.cancel()

        wi = self._warehouse_inventory_repo.get_by_id(reservation.warehouse_inventory_id)
        if wi is not None:
            wi.release_reservation(StockQuantity(reservation.total_quantity()), reservation.reservation_number.value, django_timezone.now())
            self._warehouse_inventory_repo.save(wi)

        saved = self._reservation_repo.save(reservation)

        self._ctx.stage_events([("ReservationCancelled", event.to_payload())])
        self._ctx.audit().updated(entity_type="Reservation", entity_id=str(reservation_id), before={"status": "pending"}, after={"status": "cancelled"})
        self._ctx.invalidate_inventory_cache()
        return saved


class ExpireReservation:
    def __init__(self, reservation_repo: ReservationRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._reservation_repo = reservation_repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = self._reservation_repo.get_by_id(reservation_id)
        if reservation is None:
            raise ResourceNotFound("Reservation not found.")

        event = reservation.expire(django_timezone.now())

        wi = self._warehouse_inventory_repo.get_by_id(reservation.warehouse_inventory_id)
        if wi is not None:
            wi.release_reservation(StockQuantity(reservation.total_quantity()), reservation.reservation_number.value, django_timezone.now())
            self._warehouse_inventory_repo.save(wi)

        saved = self._reservation_repo.save(reservation)

        self._ctx.stage_events([("ReservationExpiredEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Reservation", entity_id=str(reservation_id), before={}, after={"status": "expired"})
        self._ctx.invalidate_inventory_cache()
        return saved
