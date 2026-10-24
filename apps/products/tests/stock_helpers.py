"""Seeding storefront stock in tests: the storefront reads the WMS stock (stores.StoreProductStock, on hand − reserved)."""
from __future__ import annotations

import uuid


def location(name: str = "Shop", kind: str = "store", status: str = "active"):
    from apps.stores.infrastructure.models import Store

    return Store.objects.create(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", slug=f"s-{uuid.uuid4().hex[:8]}", kind=kind, status=status)


def put_stock(variant_id, quantity: int, store=None, reserved: int = 0):
    """`quantity` units on the shelf at `store` (a new active branch when omitted)."""
    from apps.stores.infrastructure.models import StoreProductStock

    return StoreProductStock.objects.create(store=store or location(), product_variant_id=variant_id, quantity=quantity, reserved_quantity=reserved)


def backdate_movement(movement_id, when) -> None:
    """Tests only: move a ledger row back in time (the ledger is append-only; this opens the trigger for one transaction)."""
    from django.db import connection, transaction

    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SET LOCAL nz.ledger_maintenance = 'on'")
        cur.execute("UPDATE stores_stock_movements SET created_at = %s WHERE id = %s", [when, movement_id])
