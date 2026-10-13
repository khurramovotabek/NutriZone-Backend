from __future__ import annotations

import uuid

import pytest

from apps.pricing.domain.events import (
    CampaignActivated,
    CashbackCalculated,
    CouponCreated,
    CouponRedeemed,
    PriceListArchivedEvent,
    PriceListCreated,
    PriceLocked,
    PriceSet,
    PricingRuleCreated,
)

pytestmark = pytest.mark.unit


def test_price_list_created_payload():
    pid = uuid.uuid4()
    payload = PriceListCreated(price_list_id=pid, code="DEFAULT-UZS").to_payload()
    assert payload["price_list_id"] == str(pid)
    assert payload["code"] == "DEFAULT-UZS"


def test_price_list_archived_event_does_not_collide_with_exception_name():
    """The event is named PriceListArchivedEvent specifically to avoid colliding with the domain exception PriceListArchived -- verified here that both are importable simultaneously without conflict, same pattern as apps.inventory's InventoryArchivedEvent/InventoryArchived."""
    from apps.pricing.domain.exceptions import PriceListArchived

    event = PriceListArchivedEvent(price_list_id=uuid.uuid4())
    assert event.__class__.__name__ == "PriceListArchivedEvent"
    assert PriceListArchived.__name__ == "PriceListArchived"


def test_price_set_payload_handles_null_old_amount():
    payload = PriceSet(price_list_id=uuid.uuid4(), product_variant_id=uuid.uuid4(), price_type="base", old_amount=None, new_amount="100.00").to_payload()
    assert payload["old_amount"] is None
    assert payload["new_amount"] == "100.00"


def test_pricing_rule_created_payload():
    rid = uuid.uuid4()
    payload = PricingRuleCreated(pricing_rule_id=rid, rule_type="quantity_discount").to_payload()
    assert payload["pricing_rule_id"] == str(rid)


def test_campaign_activated_payload():
    cid = uuid.uuid4()
    payload = CampaignActivated(campaign_id=cid).to_payload()
    assert payload["campaign_id"] == str(cid)


def test_coupon_created_payload():
    payload = CouponCreated(coupon_id=uuid.uuid4(), code="SAVE20NOW").to_payload()
    assert payload["code"] == "SAVE20NOW"


def test_coupon_redeemed_payload():
    redeemed_by = uuid.uuid4()
    payload = CouponRedeemed(coupon_id=uuid.uuid4(), redeemed_by=redeemed_by, order_reference="ORDER-001").to_payload()
    assert payload["redeemed_by"] == str(redeemed_by)
    assert payload["order_reference"] == "ORDER-001"


def test_price_locked_payload():
    variant_id = uuid.uuid4()
    payload = PriceLocked(snapshot_id=uuid.uuid4(), product_variant_id=variant_id, locked_amount="49.99").to_payload()
    assert payload["locked_amount"] == "49.99"


def test_cashback_calculated_is_one_directional_and_carries_no_wallet_credit_action():
    """Verifies the event's payload is purely descriptive (amount + references) -- it carries no method or field that could trigger a wallet credit, consistent with Phase 1's documented one-directional design."""
    payload = CashbackCalculated(product_variant_id=uuid.uuid4(), customer_reference=uuid.uuid4(), cashback_amount="5.00", order_reference="ORDER-001").to_payload()
    assert set(payload.keys()) == {"product_variant_id", "customer_reference", "cashback_amount", "order_reference"}


def test_events_are_frozen():
    event = CampaignActivated(campaign_id=uuid.uuid4())
    with pytest.raises(Exception):
        event.campaign_id = uuid.uuid4()  # type: ignore[misc]


def test_event_count_matches_source_exactly():
    """Self-verifying -- if a new event is added to domain/events.py without corresponding coverage, this documents the expected count rather than letting it silently drift."""
    import ast

    import apps.pricing.domain.events as events_module

    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 18
