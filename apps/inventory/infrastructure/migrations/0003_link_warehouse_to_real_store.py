"""
Real, confirmed gap this closes: `WarehouseInventoryModel.warehouse_id`
has always been a bare, unresolvable placeholder UUID
(`00000000-0000-0000-0000-000000000002`, per this app's own module
docstring -- "no real Warehouse model exists, Store/Branch was
removed") -- so the Inventory dashboard could only ever show a fake
"Filial 1" label, never the real store name the site owner actually
manages ("LifeSport Olmazor"). This does NOT merge or reconcile
`apps.stores.StoreProductStock` (a completely separate, independently-
tracked counter used only by the Store Profile "Add Products" page) --
that stays untouched. This ONLY relabels the *existing* warehouse
identity to the one real Store that already exists, so `warehouse_id`
finally means something real going forward, exactly matching this
project's own "bare cross-app UUID reference" convention (the same one
already used for every other cross-app id in this codebase).

Deliberately conditional: only remaps when EXACTLY ONE real Store
exists AND the placeholder warehouse id is the only one present --
multiple real stores (a genuine future multi-branch deployment) would
need a real per-warehouse-row assignment decision this migration
cannot safely guess, so it does nothing rather than guess wrong.
"""
from __future__ import annotations

import uuid

from django.db import migrations

_PLACEHOLDER_WAREHOUSE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _relink_to_real_store(apps, schema_editor):
    WarehouseInventoryModel = apps.get_model("inventory", "WarehouseInventoryModel")
    Store = apps.get_model("stores", "Store")

    distinct_warehouse_ids = set(WarehouseInventoryModel.objects.values_list("warehouse_id", flat=True).distinct())
    if distinct_warehouse_ids != {_PLACEHOLDER_WAREHOUSE_ID}:
        return  # Either no warehouse rows yet, or more than one warehouse id already in real use -- nothing safe to guess here.

    stores = list(Store.objects.all())
    if len(stores) != 1:
        return  # Zero or multiple real stores -- no single, unambiguous target to relink to.

    WarehouseInventoryModel.objects.filter(warehouse_id=_PLACEHOLDER_WAREHOUSE_ID).update(warehouse_id=stores[0].id)


def _relink_to_placeholder(apps, schema_editor):
    """Reverse: cannot know which real store id came from the placeholder without re-deriving the same single-store condition, so this reapplies the identical, deterministic rule in reverse."""
    WarehouseInventoryModel = apps.get_model("inventory", "WarehouseInventoryModel")
    Store = apps.get_model("stores", "Store")

    stores = list(Store.objects.all())
    if len(stores) != 1:
        return
    WarehouseInventoryModel.objects.filter(warehouse_id=stores[0].id).update(warehouse_id=_PLACEHOLDER_WAREHOUSE_ID)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_alter_batchmodel_options_and_more"),
        ("stores", "0002_storerating"),
    ]

    operations = [
        migrations.RunPython(_relink_to_real_store, _relink_to_placeholder),
    ]
