"""
Pure loyalty rules -- no Django, no database. Everything that decides
"which tier is this customer in" and "how many coins does this order
earn" lives here so it can be unit-tested in isolation and reused by
the API, the admin and the reward service alike.

Tier ranges are half-open: `min_spend <= spend < max_spend`. A tier
with `max_spend=None` is open-ended (the top tier). Spend is the
customer's lifetime total of qualifying (delivered/completed) orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True, slots=True)
class TierRule:
    slug: str
    name: str
    min_spend: Decimal
    max_spend: Decimal | None
    percent: Decimal

    def contains(self, spend: Decimal) -> bool:
        return spend >= self.min_spend and (self.max_spend is None or spend < self.max_spend)


def sort_tiers(tiers: list[TierRule]) -> list[TierRule]:
    return sorted(tiers, key=lambda t: t.min_spend)


def resolve_tier(spend: Decimal, tiers: list[TierRule]) -> TierRule | None:
    """The tier whose range contains `spend`. If ranges leave a gap, the customer keeps the highest tier they have fully reached (never drops to "no tier")."""
    ordered = sort_tiers(tiers)
    for tier in ordered:
        if tier.contains(spend):
            return tier
    reached = [t for t in ordered if spend >= t.min_spend]
    return reached[-1] if reached else None


def next_tier(spend: Decimal, tiers: list[TierRule]) -> TierRule | None:
    """The first tier that starts above `spend` -- what the customer is working towards."""
    for tier in sort_tiers(tiers):
        if tier.min_spend > spend:
            return tier
    return None


def reward_coins(order_amount: Decimal, percent: Decimal) -> int:
    """1 so'm = 1 coin: coins are the order amount times the tier percent, rounded DOWN to a whole coin (never over-credits)."""
    if order_amount <= 0 or percent <= 0:
        return 0
    return int((order_amount * percent / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_DOWN))


def find_overlaps(tiers: list[TierRule]) -> list[tuple[TierRule, TierRule]]:
    """Pairs of tiers whose spend ranges overlap -- an admin configuration error (a customer must map to exactly one tier)."""
    ordered = sort_tiers(tiers)
    overlaps = []
    for current, following in zip(ordered, ordered[1:], strict=False):
        if current.max_spend is None or current.max_spend > following.min_spend:
            overlaps.append((current, following))
    return overlaps
