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
