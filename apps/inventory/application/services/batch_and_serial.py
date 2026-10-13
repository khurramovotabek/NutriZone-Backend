"""
Batch & Serial Application Services: CreateBatch, UpdateBatch,
DeleteBatch, RegisterSerial, DeactivateSerial.
"""
from __future__ import annotations

import uuid
from datetime import date

from django.db import transaction

from apps.inventory.application.ports import BatchRepository, InventoryRepository, SerialRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.aggregates import Batch
from apps.inventory.domain.entities import SerialItem
from apps.inventory.domain.enums import SerialStatus
from apps.inventory.domain.exceptions import DuplicateBatch, DuplicateSerial, InventoryEntityNotFound
from apps.inventory.domain.services import BatchPolicy, SerialPolicy
from apps.inventory.domain.value_objects import BatchNumber, ExpirationDate, ManufactureDate, SerialNumber
from common.exceptions import ResourceNotFound


class CreateBatch:
    def __init__(self, batch_repo: BatchRepository, inventory_repo: InventoryRepository, ctx: InventoryServiceContext) -> None:
        self._batch_repo = batch_repo
        self._inventory_repo = inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, inventory_id: uuid.UUID, batch_number: str, manufacture_date: date | None = None, expiration_date: date | None = None) -> Batch:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryEntityNotFound(f"Inventory '{inventory_id}' does not exist.")
        if self._batch_repo.number_exists(batch_number):
            raise DuplicateBatch(f"Batch number '{batch_number}' already exists.")

        batch = Batch(
            id=uuid.uuid4(), inventory_id=inventory_id, batch_number=BatchNumber(batch_number),
            manufacture_date=ManufactureDate(manufacture_date) if manufacture_date else None,
            expiration_date=ExpirationDate(expiration_date) if expiration_date else None,
        )
        saved = self._batch_repo.save(batch)

        from apps.inventory.domain.events import BatchCreated

        self._ctx.stage_events([("BatchCreated", BatchCreated(batch_id=saved.id, inventory_id=inventory_id, batch_number=batch_number).to_payload())])
        self._ctx.audit().created(entity_type="Batch", entity_id=str(saved.id), after={"batch_number": batch_number})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("batches_created_total")
        return saved


class UpdateBatch:
    def __init__(self, repo: BatchRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, batch_id: uuid.UUID, expiration_date: date | None = None) -> Batch:
        batch = self._repo.get_by_id(batch_id)
        if batch is None:
            raise ResourceNotFound("Batch not found.")

        if expiration_date is not None:
            batch.expiration_date = ExpirationDate(expiration_date)
        saved = self._repo.save(batch)

        self._ctx.audit().updated(entity_type="Batch", entity_id=str(batch_id), before={}, after={"expiration_date": str(expiration_date) if expiration_date else None})
        self._ctx.invalidate_inventory_cache()
        return saved


class DeleteBatch:
    """A batch is only deletable while it holds zero quantity (fully consumed/transferred out) -- enforced here since it's an application-layer decision requiring a repository-sourced quantity check, not something the bare aggregate can verify against itself alone."""

    def __init__(self, repo: BatchRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, batch_id: uuid.UUID) -> None:
        from common.exceptions import ConflictError

        batch = self._repo.get_by_id(batch_id)
        if batch is None:
            raise ResourceNotFound("Batch not found.")
        if batch.quantity_received.value > 0 and batch.status.value != "depleted":
            raise ConflictError("Only a depleted batch (zero remaining quantity) may be deleted.")

        self._ctx.audit().deleted(entity_type="Batch", entity_id=str(batch_id), before={"batch_number": batch.batch_number.value})
        self._ctx.invalidate_inventory_cache()


class RegisterSerial:
    def __init__(self, batch_repo: BatchRepository, serial_repo: SerialRepository, ctx: InventoryServiceContext) -> None:
        self._batch_repo = batch_repo
        self._serial_repo = serial_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, batch_id: uuid.UUID, serial_number: str) -> Batch:
        batch = self._batch_repo.get_by_id(batch_id)
        if batch is None:
            raise ResourceNotFound("Batch not found.")
        if self._serial_repo.serial_exists(serial_number):
            raise DuplicateSerial(f"Serial number '{serial_number}' already exists.")

        serial = SerialItem(id=uuid.uuid4(), serial_number=SerialNumber(serial_number))
        event = batch.register_serial(serial)
        saved = self._batch_repo.save(batch)

        self._ctx.stage_events([("SerialRegistered", event.to_payload())])
        self._ctx.audit().created(entity_type="SerialItem", entity_id=str(serial.id), after={"serial_number": serial_number, "batch_id": str(batch_id)})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("serials_registered_total")
        return saved


class DeactivateSerial:
    def __init__(self, batch_repo: BatchRepository, ctx: InventoryServiceContext) -> None:
        self._batch_repo = batch_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, batch_id: uuid.UUID, serial_item_id: uuid.UUID) -> Batch:
        batch = self._batch_repo.get_by_id(batch_id)
        if batch is None:
            raise ResourceNotFound("Batch not found.")
        serial = batch.serials.get(serial_item_id)
        if serial is None:
            raise ResourceNotFound("Serial item not found on this batch.")

        serial.status = SerialStatus.DEACTIVATED
        saved = self._batch_repo.save(batch)

        self._ctx.audit().updated(entity_type="SerialItem", entity_id=str(serial_item_id), before={}, after={"status": "deactivated"})
        self._ctx.invalidate_inventory_cache()
        return saved
