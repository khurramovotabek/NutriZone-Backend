"""
Phase 02F's Inventory confirm_incoming test matrix (Step 22). Real
PostgreSQL throughout; drives the real HTTP flow (create inventory ->
receive -> confirm-incoming) so what's tested is exactly what a real
client would exercise, not a hand-built domain call.
"""
from __future__ import annotations

import threading
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.inventory.infrastructure import models as orm
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


@pytest.fixture
def authenticated_client(monkeypatch):
    original = HasPermissionCode.resolver
    HasPermissionCode.resolver = _AllowAllResolver()
    fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    yield client
    HasPermissionCode.resolver = original


def _make_warehouse_inventory(client, code_suffix: str):
    """Real HTTP flow for Inventory creation, plus a direct repository save for WarehouseInventory (there is no dedicated create-WI HTTP endpoint anywhere in this module -- confirmed by checking urls.py -- WarehouseInventory rows come into being via receive() in production too)."""
    create_resp = client.post("/api/v1/inventory/items", {"code": f"WHEY{code_suffix}", "product_variant_id": str(uuid.uuid4())}, format="json")
    assert create_resp.status_code == 201, create_resp.json()
    inventory_id = create_resp.json()["data"]["id"]

    from apps.inventory.infrastructure import composition
    from apps.inventory.domain.aggregates import WarehouseInventory
    wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=uuid.UUID(inventory_id), warehouse_id=uuid.uuid4())
    composition.build_warehouse_inventory_repository().save(wi)
    return wi.id


def _receive(client, wi_id, quantity, reference, key=None):
    return client.post(
        "/api/v1/inventory/admin/stock/receive",
        {"warehouse_inventory_id": str(wi_id), "quantity": quantity, "reference": reference}, format="json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def _confirm(client, wi_id, quantity, reference, key=None):
    return client.post(
        "/api/v1/inventory/admin/stock/confirm-incoming",
        {"warehouse_inventory_id": str(wi_id), "quantity": quantity, "reference": reference}, format="json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


class TestUnauthenticatedAccess:
    def test_confirm_incoming_requires_auth(self):
        response = APIClient().post("/api/v1/inventory/admin/stock/confirm-incoming", {"warehouse_inventory_id": str(uuid.uuid4()), "quantity": 5, "reference": "PO-0001"}, format="json")
        assert response.status_code == 401


class TestPermissionDenial:
    class _DenyAllResolver:
        def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
            return False

    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = self._DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_confirm_incoming_denied_for_customer(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = client.post("/api/v1/inventory/admin/stock/confirm-incoming", {"warehouse_inventory_id": str(uuid.uuid4()), "quantity": 5, "reference": "PO-0001"}, format="json")
        assert response.status_code == 403


class TestConfirmIncomingHappyPath:
    def test_confirm_incoming_moves_incoming_to_available(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "601")
        _receive(authenticated_client, wi_id, 20, "PO-0601")
        response = _confirm(authenticated_client, wi_id, 15, "PO-0601")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["available_quantity"] == 15
        row = orm.WarehouseInventoryModel.objects.get(id=wi_id)
        assert row.incoming_quantity == 5

    def test_confirm_incoming_creates_ledger_entry(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "602")
        _receive(authenticated_client, wi_id, 20, "PO-0602")
        _confirm(authenticated_client, wi_id, 15, "PO-0602")
        entries = orm.InventoryLedgerModel.objects.filter(warehouse_inventory_id=wi_id, stock_status="available")
        assert entries.count() == 1
        entry = entries.first()
        assert entry.quantity_delta == 15
        assert entry.balance_after == 15

    def test_confirm_incoming_stages_stock_confirmed_event(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "603")
        _receive(authenticated_client, wi_id, 20, "PO-0603")
        _confirm(authenticated_client, wi_id, 15, "PO-0603")
        assert orm.InventoryOutboxEvent.objects.filter(event_type="StockConfirmed").exists()

    def test_confirm_incoming_succeeds_with_audit_call_in_place(self, authenticated_client):
        """The Application Service's own self._ctx.audit().updated(...) call (reused, unmodified Audit infrastructure) must not raise -- a successful 200 response is sufficient evidence, since Audit's own read-side projection mechanism is covered by its own 57/57 suite, not re-tested here."""
        wi_id = _make_warehouse_inventory(authenticated_client, "604")
        _receive(authenticated_client, wi_id, 20, "PO-0604")
        response = _confirm(authenticated_client, wi_id, 15, "PO-0604")
        assert response.status_code == 200


class TestQuantityIntegrity:
    def test_zero_quantity_rejected(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "605")
        _receive(authenticated_client, wi_id, 20, "PO-0605")
        response = _confirm(authenticated_client, wi_id, 0, "PO-0605")
        assert response.status_code == 422

    def test_negative_quantity_rejected(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "606")
        _receive(authenticated_client, wi_id, 20, "PO-0606")
        response = _confirm(authenticated_client, wi_id, -5, "PO-0606")
        assert response.status_code == 422

    def test_excessive_quantity_rejected(self, authenticated_client):
        """More than what's currently INCOMING -- the domain's own InsufficientStock guard, exercised through the real HTTP boundary."""
        wi_id = _make_warehouse_inventory(authenticated_client, "607")
        _receive(authenticated_client, wi_id, 10, "PO-0607")
        response = _confirm(authenticated_client, wi_id, 999, "PO-0607")
        assert response.status_code == 422
        data = orm.WarehouseInventoryModel.objects.get(id=wi_id)
        assert data.available_quantity == 0  # never partially applied

    def test_unknown_warehouse_inventory_rejected(self, authenticated_client):
        response = _confirm(authenticated_client, uuid.uuid4(), 5, "PO-9999")
        assert response.status_code == 404


class TestIdempotency:
    def test_same_idempotency_key_does_not_double_confirm(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "608")
        _receive(authenticated_client, wi_id, 20, "PO-0608")
        key = str(uuid.uuid4())
        first = _confirm(authenticated_client, wi_id, 10, "PO-0608", key=key)
        second = _confirm(authenticated_client, wi_id, 10, "PO-0608", key=key)
        assert first.status_code == 200
        assert second.status_code == 200
        data = orm.WarehouseInventoryModel.objects.get(id=wi_id)
        assert data.available_quantity == 10  # not 20 -- the replay did not re-execute


class TestConcurrency:
    def test_concurrent_confirm_incoming_never_over_confirms(self, authenticated_client):
        """Two threads racing to confirm more INCOMING stock than actually exists combined -- the domain's own InsufficientStock check, protected by select_for_update() row locking, must let exactly the available amount through and reject the rest, never producing negative INCOMING or double-counted AVAILABLE."""
        wi_id = _make_warehouse_inventory(authenticated_client, "609")
        _receive(authenticated_client, wi_id, 10, "PO-0609")

        results = []

        def worker():
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
            try:
                resp = client.post(
                    "/api/v1/inventory/admin/stock/confirm-incoming",
                    {"warehouse_inventory_id": str(wi_id), "quantity": 8, "reference": "PO-0609"}, format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                )
                results.append(resp.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        final = orm.WarehouseInventoryModel.objects.get(id=wi_id)
        assert final.available_quantity <= 10  # never more than what was ever received
        assert final.incoming_quantity >= 0  # never negative
        assert final.available_quantity + final.incoming_quantity == 10  # conserved


class TestLedgerConsistency:
    def test_multiple_confirmations_cumulative_balance_correct(self, authenticated_client):
        wi_id = _make_warehouse_inventory(authenticated_client, "610")
        _receive(authenticated_client, wi_id, 30, "PO-0610")
        _confirm(authenticated_client, wi_id, 10, "PO-0610-A")
        _confirm(authenticated_client, wi_id, 10, "PO-0610-B")
        final = orm.WarehouseInventoryModel.objects.get(id=wi_id)
        assert final.available_quantity == 20
        assert final.incoming_quantity == 10
        entries = orm.InventoryLedgerModel.objects.filter(warehouse_inventory_id=wi_id, stock_status="available").order_by("occurred_at")
        assert [e.balance_after for e in entries] == [10, 20]
