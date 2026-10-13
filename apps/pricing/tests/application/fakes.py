"""
In-memory fakes implementing application/ports.py's Protocols, matching
every prior module's `tests/application/fakes.py` pattern.
"""
from __future__ import annotations


class FakePriceListRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, price_list_id):
        return self.by_id.get(price_list_id)

    def get_by_code(self, code):
        return next((p for p in self.by_id.values() if p.code.value == code), None)

    def get_active_for_region(self, region):
        return next((p for p in self.by_id.values() if p.status.value == "active" and (p.region.value if p.region else None) == region), None)

    def save(self, price_list):
        self.by_id[price_list.id] = price_list
        return price_list

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(p.code.value == code and p.id != exclude_id for p in self.by_id.values())

    def list_for_admin(self, status, page, page_size):
        results = list(self.by_id.values())
        if status:
            results = [p for p in results if p.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakePricingRuleRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, pricing_rule_id):
        return self.by_id.get(pricing_rule_id)

    def save(self, pricing_rule):
        self.by_id[pricing_rule.id] = pricing_rule
        return pricing_rule

    def list_active_at(self, at, rule_type=None):
        rules = [r for r in self.by_id.values() if r.is_active_at(at)]
        if rule_type:
            rules = [r for r in rules if r.rule_type.value == rule_type]
        return rules


class FakeCampaignRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, campaign_id):
        return self.by_id.get(campaign_id)

    def save(self, campaign):
        self.by_id[campaign.id] = campaign
        return campaign

    def list_active_for_target(self, target_type, target_id, at):
        return [c for c in self.by_id.values() if c.is_active_at(at) and c.applies_to(target_type, target_id)]


class FakeCouponRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, coupon_id):
        return self.by_id.get(coupon_id)

    def get_by_code(self, code):
        return next((c for c in self.by_id.values() if c.code.value == code), None)

    def save(self, coupon):
        self.by_id[coupon.id] = coupon
        return coupon

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(c.code.value == code and c.id != exclude_id for c in self.by_id.values())


class FakePriceSnapshotRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, snapshot_id):
        return self.by_id.get(snapshot_id)

    def get_by_token(self, token):
        return next((s for s in self.by_id.values() if str(s.token) == str(token)), None)

    def save(self, snapshot):
        self.by_id[snapshot.id] = snapshot
        return snapshot


def collect_events(sink: list):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
