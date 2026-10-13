"""
Audit event builder.

Produces a uniform `AuditEvent` payload shape for every event type the
mission names (Created/Updated/Deleted/Viewed/Downloaded/Exported/
Login/Logout/PermissionChanged/PriceChanged/StockChanged/
WalletChanged/CouponUsed/OrderStatusChanged). This is the concrete
mechanism behind the platform-wide `audit.activity_timeline` sink
described in Enterprise Database Blueprint §4.19/§11 -- an
`AuditEvent` this builder produces is exactly the payload a future
`audit` app's outbox-subscribing event handler stages into that table
(no `audit` app model exists yet; that is `apps.audit`'s own
implementation, this module only standardizes the event *shape* every
other module emits).

No module is required to use every event type -- a module builds only
the events relevant to it (e.g. `catalog` emits PriceChanged-adjacent
events via `pricing`, not itself). This module supplies the closed
vocabulary and the builder; it does not decide which module emits what.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.clock import Clock
from core.observability.correlation import get_causation_id, get_correlation_id


class AuditEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    VIEWED = "viewed"
    DOWNLOADED = "downloaded"
    EXPORTED = "exported"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_CHANGED = "permission_changed"
    PRICE_CHANGED = "price_changed"
    STOCK_CHANGED = "stock_changed"
    WALLET_CHANGED = "wallet_changed"
    COUPON_USED = "coupon_used"
    ORDER_STATUS_CHANGED = "order_status_changed"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """
    Matches the shape `audit.activity_timeline` (Database Blueprint
    §4.19) will persist: actor, action, entity reference, before/after
    snapshots, plus the correlation/causation metadata from
    core/observability (see AuditEventBuilder for how these are
    populated automatically).
    """

    id: uuid.UUID
    event_type: AuditEventType
    entity_type: str
    entity_id: str
    actor_id: str | None
    occurred_at: str  # ISO8601, via Clock -- never datetime.now()/timezone.now() directly
    context_schema: str  # the emitting bounded-context app label
    before_snapshot: dict[str, Any] | None
    after_snapshot: dict[str, Any] | None
    correlation_id: str | None
    causation_id: str | None
    extra: dict[str, Any] = field(default_factory=dict)


class AuditEventBuilder:
    """
    Usage:
        builder = AuditEventBuilder(context_schema="catalog", actor_id=str(user.id))
        event = builder.updated(
            entity_type="Product", entity_id=str(product.id),
            before={"status": "draft"}, after={"status": "published"},
        )
        # then: core.outbox.stage_event(SomeOutboxModel, "ProductAudited", asdict(event))
    """

    def __init__(self, context_schema: str, actor_id: str | None = None) -> None:
        self.context_schema = context_schema
        self.actor_id = actor_id

    def _build(
        self,
        event_type: AuditEventType,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=self.actor_id,
            occurred_at=Clock.now().isoformat(),
            context_schema=self.context_schema,
            before_snapshot=before,
            after_snapshot=after,
            correlation_id=get_correlation_id(),
            causation_id=get_causation_id(),
            extra=extra or {},
        )

    def created(self, entity_type: str, entity_id: str, after: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.CREATED, entity_type, entity_id, after=after)

    def updated(self, entity_type: str, entity_id: str, before: dict[str, Any], after: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.UPDATED, entity_type, entity_id, before=before, after=after)

    def deleted(self, entity_type: str, entity_id: str, before: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.DELETED, entity_type, entity_id, before=before)

    def viewed(self, entity_type: str, entity_id: str) -> AuditEvent:
        return self._build(AuditEventType.VIEWED, entity_type, entity_id)

    def downloaded(self, entity_type: str, entity_id: str) -> AuditEvent:
        return self._build(AuditEventType.DOWNLOADED, entity_type, entity_id)

    def exported(self, entity_type: str, entity_id: str, extra: dict[str, Any] | None = None) -> AuditEvent:
        return self._build(AuditEventType.EXPORTED, entity_type, entity_id, extra=extra)

    def login(self, entity_id: str, extra: dict[str, Any] | None = None) -> AuditEvent:
        return self._build(AuditEventType.LOGIN, "User", entity_id, extra=extra)

    def logout(self, entity_id: str) -> AuditEvent:
        return self._build(AuditEventType.LOGOUT, "User", entity_id)

    def permission_changed(self, entity_id: str, before: dict[str, Any], after: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.PERMISSION_CHANGED, "User", entity_id, before=before, after=after)

    def price_changed(self, entity_id: str, before: dict[str, Any], after: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.PRICE_CHANGED, "PriceEntry", entity_id, before=before, after=after)

    def stock_changed(self, entity_id: str, before: dict[str, Any], after: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.STOCK_CHANGED, "StockItem", entity_id, before=before, after=after)

    def wallet_changed(self, entity_id: str, after: dict[str, Any]) -> AuditEvent:
        # Wallet is append-only (Database Blueprint §4.8) -- a "change"
        # is always a new ledger entry, never a before/after diff of an
        # existing row, so `before` is intentionally omitted here.
        return self._build(AuditEventType.WALLET_CHANGED, "WalletLedgerEntry", entity_id, after=after)

    def coupon_used(self, entity_id: str, extra: dict[str, Any] | None = None) -> AuditEvent:
        return self._build(AuditEventType.COUPON_USED, "Coupon", entity_id, extra=extra)

    def order_status_changed(self, entity_id: str, before: dict[str, Any], after: dict[str, Any]) -> AuditEvent:
        return self._build(AuditEventType.ORDER_STATUS_CHANGED, "Order", entity_id, before=before, after=after)
