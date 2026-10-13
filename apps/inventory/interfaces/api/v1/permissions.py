"""
Inventory API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern -- every class below is a
thin, named wrapper calling `common.permissions.HasPermissionCode.
resolver` (wired once, globally, by `apps.identity.apps.IdentityConfig.
ready()`) with an Inventory-specific permission code. No authorization
logic is duplicated here.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class _InventoryPermission(BasePermission):
    """Base class -- subclasses set `permission_code`."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        from common.permissions import HasPermissionCode

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class CanViewInventory(_InventoryPermission):
    permission_code = "inventory.item.view"


class CanManageInventory(_InventoryPermission):
    permission_code = "inventory.item.manage"


class CanReceiveStock(_InventoryPermission):
    permission_code = "inventory.stock.receive"


class CanConfirmIncomingStock(_InventoryPermission):
    permission_code = "inventory.stock.confirm"


class CanReserveStock(_InventoryPermission):
    permission_code = "inventory.stock.reserve"


class CanReleaseReservation(_InventoryPermission):
    permission_code = "inventory.reservation.release"


class CanTransferStock(_InventoryPermission):
    permission_code = "inventory.stock.transfer"


class CanAdjustStock(_InventoryPermission):
    """Covers Adjust/Damage/Expire -- all three are manual corrections to a warehouse's stock buckets with the same blast radius, sharing one permission code rather than three near-identical ones."""

    permission_code = "inventory.stock.adjust"


class CanManageBatch(_InventoryPermission):
    permission_code = "inventory.batch.manage"


class CanManageSerial(_InventoryPermission):
    permission_code = "inventory.serial.manage"


class CanManageSnapshot(_InventoryPermission):
    permission_code = "inventory.snapshot.manage"


class CanManageCycleCount(_InventoryPermission):
    permission_code = "inventory.cycle_count.manage"


class CanManagePhysicalInventory(_InventoryPermission):
    permission_code = "inventory.physical_inventory.manage"


class CanViewLedger(_InventoryPermission):
    permission_code = "inventory.ledger.view"


class CanViewReservations(_InventoryPermission):
    permission_code = "inventory.reservation.view"
