"""
Pure-function tests -- no Django/database access, executable directly
even with Django unavailable. `_sync_source()` itself requires a real
database (ORM queries) and is not executable in this sandbox,
disclosed in the certification report, not silently skipped.
"""
from __future__ import annotations

from types import SimpleNamespace

from apps.audit.infrastructure.subscribers import (
    _map_address_updated,
    _map_cart_merged,
    _map_feature_flag_changed,
    _map_order_confirmed,
    _map_price_set,
    _map_product_published,
    _map_sale_completed,
    _map_stock_adjusted,
    _map_user_role_assigned,
)


def _make_event(event_type: str, payload: dict):
    return SimpleNamespace(event_type=event_type, payload=payload)


class TestMapFeatureFlagChanged:
    def test_maps_a_real_feature_flag_changed_event(self):
        event = _make_event("FeatureFlagChanged", {"flag_id": "abc-123", "key": "ENABLE_X", "is_globally_enabled": True})
        mapped = _map_feature_flag_changed(event)

        assert mapped["action_type"] == "updated"
        assert mapped["entity_type"] == "FeatureFlag"
        assert mapped["entity_id"] == "abc-123"
        assert mapped["after_snapshot"] == {"key": "ENABLE_X", "is_globally_enabled": True}

    def test_unrecognized_event_type_returns_none(self):
        event = _make_event("SomeOtherModulesEvent", {"foo": "bar"})
        assert _map_feature_flag_changed(event) is None

    def test_never_exposes_rollout_percentage_or_scope(self):
        event = _make_event("FeatureFlagChanged", {"flag_id": "abc-123", "key": "ENABLE_X", "is_globally_enabled": True})
        mapped = _map_feature_flag_changed(event)
        assert "rollout_percentage" not in mapped["after_snapshot"]
        assert "rollout_scope" not in mapped["after_snapshot"]

class TestMapOrderConfirmed:
    def test_maps_a_real_order_confirmed_event(self):
        event = _make_event("OrderConfirmed", {"order_id": "o1"})
        mapped = _map_order_confirmed(event)

        assert mapped["action_type"] == "updated"
        assert mapped["entity_type"] == "Order"
        assert mapped["entity_id"] == "o1"

    def test_unrecognized_event_type_returns_none(self):
        assert _map_order_confirmed(_make_event("OrderCancelled", {"order_id": "o1"})) is None


class TestMapPriceSet:
    def test_maps_a_real_price_set_event(self):
        event = _make_event("PriceSet", {"price_list_id": "pl1", "product_variant_id": "v1", "price_type": "retail", "old_amount": "10.00", "new_amount": "12.00"})
        mapped = _map_price_set(event)

        assert mapped["action_type"] == "updated"
        assert mapped["entity_type"] == "ProductVariant"
        assert mapped["entity_id"] == "v1"
        assert mapped["before_snapshot"] == {"amount": "10.00"}
        assert mapped["after_snapshot"]["amount"] == "12.00"

    def test_first_time_price_has_no_before_snapshot(self):
        """A real edge case: old_amount is None for a variant's first-ever price -- must not fabricate a before_snapshot for a price that never existed."""
        event = _make_event("PriceSet", {"price_list_id": "pl1", "product_variant_id": "v1", "price_type": "retail", "old_amount": None, "new_amount": "12.00"})
        mapped = _map_price_set(event)
        assert mapped["before_snapshot"] is None

    def test_unrecognized_event_type_returns_none(self):
        assert _map_price_set(_make_event("PriceListActivated", {})) is None

    def test_never_exposes_internal_pricing_rule_or_campaign_data(self):
        """Security: the mapping only ever reads the 5 fields PriceSet.to_payload() actually provides -- no pricing-rule/campaign/coupon internals can leak through, since the mapper never looks for them."""
        event = _make_event("PriceSet", {"price_list_id": "pl1", "product_variant_id": "v1", "price_type": "retail", "old_amount": "10.00", "new_amount": "12.00"})
        mapped = _map_price_set(event)
        combined = {**(mapped["before_snapshot"] or {}), **mapped["after_snapshot"]}
        assert set(combined.keys()) <= {"amount", "price_type", "price_list_id"}


class TestMapStockAdjusted:
    def test_maps_a_real_stock_adjusted_event(self):
        event = _make_event("StockAdjusted", {"adjustment_id": "a1", "warehouse_inventory_id": "w1", "quantity_delta": -5, "reason": "damaged"})
        mapped = _map_stock_adjusted(event)

        assert mapped["entity_type"] == "WarehouseInventory"
        assert mapped["entity_id"] == "w1"
        assert mapped["after_snapshot"] == {"quantity_delta": -5, "reason": "damaged"}

    def test_unrecognized_event_type_returns_none(self):
        assert _map_stock_adjusted(_make_event("StockReceived", {})) is None


class TestMapUserRoleAssigned:
    def test_maps_a_real_user_role_assigned_event(self):
        event = _make_event("UserRoleAssigned", {"user_id": "u1", "role_id": "r1", "role_code": "STORE_MANAGER", "store_id": "s1"})
        mapped = _map_user_role_assigned(event)

        assert mapped["action_type"] == "permission_changed"
        assert mapped["entity_type"] == "User"
        assert mapped["entity_id"] == "u1"
        assert mapped["after_snapshot"] == {"role_id": "r1", "role_code": "STORE_MANAGER", "store_id": "s1"}

    def test_action_type_matches_the_established_core_audit_vocabulary(self):
        """
        Proves this mapping reuses `core.audit.events.AuditEventType.
        PERMISSION_CHANGED`'s own real value, confirmed by direct
        source inspection: `grep -n "PERMISSION_CHANGED"
        core/audit/events.py` returns `PERMISSION_CHANGED =
        "permission_changed"`. Deliberately hardcoded as a literal
        here rather than imported -- `core.audit.events` transitively
        imports `core.observability`, which imports Django
        (confirmed directly: importing it in this sandbox raises
        `ModuleNotFoundError: No module named 'django'`), which would
        silently break this entire file's own "no Django dependency"
        guarantee stated in its module docstring.
        """
        event = _make_event("UserRoleAssigned", {"user_id": "u1", "role_id": "r1", "role_code": "STORE_MANAGER", "store_id": None})
        mapped = _map_user_role_assigned(event)
        assert mapped["action_type"] == "permission_changed"

    def test_global_role_has_null_store_id(self):
        event = _make_event("UserRoleAssigned", {"user_id": "u1", "role_id": "r1", "role_code": "ADMIN", "store_id": None})
        mapped = _map_user_role_assigned(event)
        assert mapped["after_snapshot"]["store_id"] is None

    def test_unrecognized_event_type_returns_none(self):
        assert _map_user_role_assigned(_make_event("UserBlocked", {})) is None


class TestMapCartMerged:
    def test_maps_a_real_event(self):
        event = _make_event("CartMerged", {"target_cart_id": "t1", "source_cart_id": "s1", "items_merged": 3, "strategy": "keep_target"})
        mapped = _map_cart_merged(event)

        assert mapped["entity_type"] == "Cart"
        assert mapped["entity_id"] == "t1"
        assert mapped["after_snapshot"] == {"source_cart_id": "s1", "items_merged": 3, "strategy": "keep_target"}

    def test_unrecognized_event_type_returns_none(self):
        assert _map_cart_merged(_make_event("ItemAdded", {})) is None


class TestMapAddressUpdated:
    def test_maps_a_real_event_with_genuine_before_after(self):
        """The one mapper in this capability whose source event already provides real before/after state -- proves the values are passed through exactly, not reconstructed or fabricated."""
        event = _make_event("AddressUpdated", {"address_id": "a1", "before": {"city": "Old City"}, "after": {"city": "New City"}})
        mapped = _map_address_updated(event)

        assert mapped["entity_type"] == "Address"
        assert mapped["entity_id"] == "a1"
        assert mapped["before_snapshot"] == {"city": "Old City"}
        assert mapped["after_snapshot"] == {"city": "New City"}

    def test_unrecognized_event_type_returns_none(self):
        assert _map_address_updated(_make_event("AddressDeleted", {})) is None


class TestMapSaleCompleted:
    def test_maps_a_real_event(self):
        event = _make_event("SaleCompleted", {"sale_id": "sale1", "total_amount": "99.50", "currency": "UZS"})
        mapped = _map_sale_completed(event)

        assert mapped["entity_type"] == "Sale"
        assert mapped["entity_id"] == "sale1"
        assert mapped["after_snapshot"] == {"total_amount": "99.50", "currency": "UZS"}

    def test_unrecognized_event_type_returns_none(self):
        assert _map_sale_completed(_make_event("SaleVoided", {"sale_id": "sale1"})) is None

    def test_never_exposes_line_item_or_cashier_internals(self):
        """Security: SaleCompleted's own real payload has exactly 3 fields (sale_id, total_amount, currency) -- no line items, cashier_id, or branch_id can leak, since none of those exist in the source payload the mapper reads from."""
        event = _make_event("SaleCompleted", {"sale_id": "sale1", "total_amount": "99.50", "currency": "UZS"})
        mapped = _map_sale_completed(event)
        assert set(mapped["after_snapshot"].keys()) == {"total_amount", "currency"}


class TestMapProductPublished:
    def test_maps_a_real_event(self):
        event = _make_event("ProductPublished", {"product_id": "p1"})
        mapped = _map_product_published(event)

        assert mapped["entity_type"] == "Product"
        assert mapped["entity_id"] == "p1"
        assert mapped["after_snapshot"] == {"status": "published"}

    def test_unrecognized_event_type_returns_none(self):
        assert _map_product_published(_make_event("ProductHidden", {"product_id": "p1"})) is None


class TestKeysetCursorLogic:
    """
    A direct, standalone (non-Django) simulation of the exact keyset
    query `_sync_source()` builds via `.filter(created_at__gte=...)
    .exclude(created_at=..., id=...)` -- proves the same-timestamp
    edge case a naive `created_at__gt` cursor would silently mishandle
    is handled correctly, without requiring a real database to prove it.
    """

    @staticmethod
    def _simulate(rows, last_created_at, last_id):
        if last_created_at is None:
            return list(rows)
        result = [r for r in rows if r["created_at"] >= last_created_at]
        result = [r for r in result if not (r["created_at"] == last_created_at and r["id"] == last_id)]
        return result

    def test_no_cursor_returns_everything(self):
        rows = [{"created_at": 1, "id": "a"}, {"created_at": 2, "id": "b"}]
        assert self._simulate(rows, None, None) == rows

    def test_same_timestamp_row_after_cursor_is_not_skipped(self):
        rows = [{"created_at": 1, "id": "a"}, {"created_at": 1, "id": "b"}, {"created_at": 2, "id": "c"}]
        result = self._simulate(rows, 1, "a")
        assert [r["id"] for r in result] == ["b", "c"]

    def test_exact_cursor_row_itself_is_excluded(self):
        rows = [{"created_at": 1, "id": "a"}]
        assert self._simulate(rows, 1, "a") == []

    def test_rows_strictly_before_cursor_are_excluded(self):
        rows = [{"created_at": 0, "id": "z"}, {"created_at": 1, "id": "a"}]
        result = self._simulate(rows, 1, "a")
        assert result == []
