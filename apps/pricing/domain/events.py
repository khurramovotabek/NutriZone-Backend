"""
Pricing domain events.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PriceListCreated:
    price_list_id: uuid.UUID
    code: str

    def to_payload(self) -> dict:
        return {**asdict(self), "price_list_id": str(self.price_list_id)}


@dataclass(frozen=True, slots=True)
class PriceListActivated:
    price_list_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"price_list_id": str(self.price_list_id)}


@dataclass(frozen=True, slots=True)
class PriceListArchivedEvent:
    price_list_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"price_list_id": str(self.price_list_id)}


@dataclass(frozen=True, slots=True)
class PriceSet:
    """Fired whenever a PriceListEntry's price changes -- the event backing 'Pricing History'/downstream cache invalidation."""

    price_list_id: uuid.UUID
    product_variant_id: uuid.UUID
    price_type: str
    old_amount: str | None
    new_amount: str

    def to_payload(self) -> dict:
        return {**asdict(self), "price_list_id": str(self.price_list_id), "product_variant_id": str(self.product_variant_id)}


@dataclass(frozen=True, slots=True)
class PricingRuleCreated:
    pricing_rule_id: uuid.UUID
    rule_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "pricing_rule_id": str(self.pricing_rule_id)}


@dataclass(frozen=True, slots=True)
class PricingRuleActivated:
    pricing_rule_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"pricing_rule_id": str(self.pricing_rule_id)}


@dataclass(frozen=True, slots=True)
class PricingRuleArchived:
    pricing_rule_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"pricing_rule_id": str(self.pricing_rule_id)}


@dataclass(frozen=True, slots=True)
class CampaignCreated:
    campaign_id: uuid.UUID
    campaign_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "campaign_id": str(self.campaign_id)}


@dataclass(frozen=True, slots=True)
class CampaignActivated:
    campaign_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"campaign_id": str(self.campaign_id)}


@dataclass(frozen=True, slots=True)
class CampaignEnded:
    campaign_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"campaign_id": str(self.campaign_id)}


@dataclass(frozen=True, slots=True)
class CampaignCancelled:
    campaign_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"campaign_id": str(self.campaign_id)}


@dataclass(frozen=True, slots=True)
class CouponCreated:
    coupon_id: uuid.UUID
    code: str

    def to_payload(self) -> dict:
        return {**asdict(self), "coupon_id": str(self.coupon_id)}


@dataclass(frozen=True, slots=True)
class CouponRedeemed:
    coupon_id: uuid.UUID
    redeemed_by: uuid.UUID
    order_reference: str

    def to_payload(self) -> dict:
        return {**asdict(self), "coupon_id": str(self.coupon_id), "redeemed_by": str(self.redeemed_by)}


@dataclass(frozen=True, slots=True)
class CouponRevoked:
    coupon_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"coupon_id": str(self.coupon_id)}


@dataclass(frozen=True, slots=True)
class PriceLocked:
    """The event backing 'Price Lock' / 'Price Snapshot'."""

    snapshot_id: uuid.UUID
    product_variant_id: uuid.UUID
    locked_amount: str

    def to_payload(self) -> dict:
        return {**asdict(self), "snapshot_id": str(self.snapshot_id), "product_variant_id": str(self.product_variant_id)}


@dataclass(frozen=True, slots=True)
class PriceSnapshotConsumed:
    snapshot_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"snapshot_id": str(self.snapshot_id)}


@dataclass(frozen=True, slots=True)
class PriceSnapshotReleased:
    snapshot_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"snapshot_id": str(self.snapshot_id)}


@dataclass(frozen=True, slots=True)
class CashbackCalculated:
    """
    One-directional, event-driven handoff to the future Wallet module
    -- Pricing computes the cashback amount a purchase would earn and
    publishes this event; crediting it to a wallet balance is entirely
    Wallet's responsibility once built, consumed asynchronously via
    the Outbox. Pricing never calls Wallet directly.
    """

    product_variant_id: uuid.UUID
    customer_reference: uuid.UUID
    cashback_amount: str
    order_reference: str

    def to_payload(self) -> dict:
        return {**asdict(self), "product_variant_id": str(self.product_variant_id), "customer_reference": str(self.customer_reference)}
