from __future__ import annotations

import pytest

from core.audit import AuditEventBuilder, AuditEventType
from core.clock import Clock
from core.observability import correlation_scope

pytestmark = pytest.mark.unit


def test_created_event_shape():
    builder = AuditEventBuilder(context_schema="catalog", actor_id="user-1")
    event = builder.created("Product", "product-1", after={"status": "draft"})
    assert event.event_type == AuditEventType.CREATED
    assert event.entity_type == "Product"
    assert event.entity_id == "product-1"
    assert event.actor_id == "user-1"
    assert event.after_snapshot == {"status": "draft"}
    assert event.before_snapshot is None


def test_updated_event_carries_before_and_after():
    builder = AuditEventBuilder(context_schema="pricing")
    event = builder.updated("PriceEntry", "pe-1", before={"price": 10}, after={"price": 12})
    assert event.before_snapshot == {"price": 10}
    assert event.after_snapshot == {"price": 12}


def test_wallet_changed_event_has_no_before_snapshot():
    """Wallet is append-only -- a 'change' is a new ledger entry, never a diff of an existing row."""
    builder = AuditEventBuilder(context_schema="wallet")
    event = builder.wallet_changed("entry-1", after={"amount": 500})
    assert event.before_snapshot is None
    assert event.after_snapshot == {"amount": 500}


def test_login_and_logout_events_target_user_entity():
    builder = AuditEventBuilder(context_schema="identity")
    login = builder.login("user-1")
    logout = builder.logout("user-1")
    assert login.entity_type == "User"
    assert logout.entity_type == "User"
    assert login.event_type == AuditEventType.LOGIN
    assert logout.event_type == AuditEventType.LOGOUT


def test_occurred_at_uses_clock_and_is_freezable():
    from datetime import datetime, timezone

    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Clock.freeze(fixed):
        builder = AuditEventBuilder(context_schema="catalog")
        event = builder.viewed("Product", "p1")
    assert event.occurred_at == fixed.isoformat()


def test_event_picks_up_active_correlation_scope():
    builder = AuditEventBuilder(context_schema="ordering")
    with correlation_scope(correlation_id="corr-123", causation_id="caus-456"):
        event = builder.order_status_changed("order-1", before={"status": "pending"}, after={"status": "confirmed"})
    assert event.correlation_id == "corr-123"
    assert event.causation_id == "caus-456"


def test_each_event_has_a_unique_id():
    builder = AuditEventBuilder(context_schema="reviews")
    event_a = builder.viewed("Review", "r1")
    event_b = builder.viewed("Review", "r2")
    assert event_a.id != event_b.id


def test_all_mission_required_event_types_exist():
    required = {
        "created",
        "updated",
        "deleted",
        "viewed",
        "downloaded",
        "exported",
        "login",
        "logout",
        "permission_changed",
        "price_changed",
        "stock_changed",
        "wallet_changed",
        "coupon_used",
        "order_status_changed",
    }
    assert required.issubset({member.value for member in AuditEventType})


def test_coupon_used_event_supports_extra_metadata():
    builder = AuditEventBuilder(context_schema="coupons")
    event = builder.coupon_used("coupon-1", extra={"order_id": "order-9"})
    assert event.extra == {"order_id": "order-9"}
