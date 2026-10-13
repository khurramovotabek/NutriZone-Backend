"""Pure tier/reward rules -- no database."""
from __future__ import annotations

from decimal import Decimal

from apps.loyalty.domain.tiers import TierRule, find_overlaps, next_tier, resolve_tier, reward_coins

D = Decimal
BRONZE = TierRule("bronze", "Bronza", D("0"), D("1000000"), D("1"))
SILVER = TierRule("silver", "Kumush", D("1000000"), D("5000000"), D("2"))
VIP = TierRule("vip", "VIP", D("5000000"), D("15000000"), D("3"))
DIAMOND = TierRule("diamond", "Diamond", D("15000000"), None, D("5"))
LADDER = [DIAMOND, BRONZE, VIP, SILVER]  # deliberately unsorted


def test_resolve_tier_uses_half_open_ranges():
    assert resolve_tier(D("0"), LADDER) is BRONZE
    assert resolve_tier(D("999999"), LADDER) is BRONZE
    assert resolve_tier(D("1000000"), LADDER) is SILVER
    assert resolve_tier(D("14000000"), LADDER) is VIP
    assert resolve_tier(D("15000000"), LADDER) is DIAMOND
    assert resolve_tier(D("900000000"), LADDER) is DIAMOND


def test_gap_in_ranges_keeps_highest_reached_tier():
    assert resolve_tier(D("3000000"), [BRONZE, VIP]) is BRONZE


def test_no_tiers_means_no_tier():
    assert resolve_tier(D("5"), []) is None


def test_next_tier():
    assert next_tier(D("0"), LADDER) is SILVER
    assert next_tier(D("6000000"), LADDER) is DIAMOND
    assert next_tier(D("20000000"), LADDER) is None


def test_reward_is_one_coin_per_som_times_percent_rounded_down():
    assert reward_coins(D("1000000"), D("3")) == 30000
    assert reward_coins(D("1000000"), D("5")) == 50000
    assert reward_coins(D("12345.67"), D("1")) == 123  # 123.4567 -> 123, never over-credits
    assert reward_coins(D("99"), D("1")) == 0
    assert reward_coins(D("0"), D("5")) == 0
    assert reward_coins(D("500000"), D("0")) == 0


def test_find_overlaps():
    assert find_overlaps(LADDER) == []
    overlapping = TierRule("x", "X", D("4000000"), D("6000000"), D("2"))
    assert find_overlaps([BRONZE, overlapping, VIP]) == [(overlapping, VIP)]
