from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.inventory.interfaces.api.v1.permissions import (
    CanAdjustStock, CanManageBatch, CanManageCycleCount, CanManageInventory, CanManagePhysicalInventory,
    CanManageSerial, CanManageSnapshot, CanReceiveStock, CanReleaseReservation, CanReserveStock,
    CanTransferStock, CanViewInventory, CanViewLedger, CanViewReservations,
)
from common.permissions import HasPermissionCode

pytestmark = pytest.mark.unit


class _FakeResolver:
    def __init__(self, granted_codes: set[str]) -> None:
        self.granted_codes = granted_codes

    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code in self.granted_codes


@pytest.fixture(autouse=True)
def _reset_resolver():
    original = HasPermissionCode.resolver
    yield
    HasPermissionCode.resolver = original


@pytest.mark.parametrize(
    "permission_cls,expected_code",
    [
        (CanViewInventory, "inventory.item.view"),
        (CanManageInventory, "inventory.item.manage"),
        (CanReceiveStock, "inventory.stock.receive"),
        (CanReserveStock, "inventory.stock.reserve"),
        (CanReleaseReservation, "inventory.reservation.release"),
        (CanTransferStock, "inventory.stock.transfer"),
        (CanAdjustStock, "inventory.stock.adjust"),
        (CanManageBatch, "inventory.batch.manage"),
        (CanManageSerial, "inventory.serial.manage"),
        (CanManageSnapshot, "inventory.snapshot.manage"),
        (CanManageCycleCount, "inventory.cycle_count.manage"),
        (CanManagePhysicalInventory, "inventory.physical_inventory.manage"),
        (CanViewLedger, "inventory.ledger.view"),
        (CanViewReservations, "inventory.reservation.view"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_fourteen_permission_codes_are_unique():
    codes = {
        CanViewInventory.permission_code, CanManageInventory.permission_code, CanReceiveStock.permission_code,
        CanReserveStock.permission_code, CanReleaseReservation.permission_code, CanTransferStock.permission_code,
        CanAdjustStock.permission_code, CanManageBatch.permission_code, CanManageSerial.permission_code,
        CanManageSnapshot.permission_code, CanManageCycleCount.permission_code, CanManagePhysicalInventory.permission_code,
        CanViewLedger.permission_code, CanViewReservations.permission_code,
    }
    assert len(codes) == 14


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"inventory.stock.receive"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CanReceiveStock().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"inventory.stock.transfer"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert CanTransferStock().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert CanManageInventory().has_permission(request, view=None) is False
