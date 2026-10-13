"""
Pricing's Domain Event Catalogue registration.

Imported once from `apps/pricing/apps.py::PricingConfig.ready()`,
matching every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.pricing.domain.events import (
    CampaignActivated,
    CampaignCancelled,
    CampaignCreated,
    CampaignEnded,
    CashbackCalculated,
    CouponCreated,
    CouponRedeemed,
    CouponRevoked,
    PriceListActivated,
    PriceListArchivedEvent,
    PriceListCreated,
    PriceLocked,
    PriceSet,
    PriceSnapshotConsumed,
    PriceSnapshotReleased,
    PricingRuleActivated,
    PricingRuleArchived,
    PricingRuleCreated,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("PriceListCreated", PriceListCreated),
    ("PriceListActivated", PriceListActivated),
    ("PriceListArchivedEvent", PriceListArchivedEvent),
    ("PriceSet", PriceSet),
    ("PricingRuleCreated", PricingRuleCreated),
    ("PricingRuleActivated", PricingRuleActivated),
    ("PricingRuleArchived", PricingRuleArchived),
    ("CampaignCreated", CampaignCreated),
    ("CampaignActivated", CampaignActivated),
    ("CampaignEnded", CampaignEnded),
    ("CampaignCancelled", CampaignCancelled),
    ("CouponCreated", CouponCreated),
    ("CouponRedeemed", CouponRedeemed),
    ("CouponRevoked", CouponRevoked),
    ("PriceLocked", PriceLocked),
    ("PriceSnapshotConsumed", PriceSnapshotConsumed),
    ("PriceSnapshotReleased", PriceSnapshotReleased),
    ("CashbackCalculated", CashbackCalculated),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="pricing", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
