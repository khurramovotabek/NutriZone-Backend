from __future__ import annotations

import pytest

from core.flags import (
    ChainedFlagProvider,
    EnvironmentFlagProvider,
    FeatureFlags,
    FlagContext,
    FlagDefinition,
    FlagKey,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_feature_flags():
    original_provider = FeatureFlags._provider
    yield
    FeatureFlags._provider = original_provider


def test_disabled_flag_definition_evaluates_false():
    definition = FlagDefinition(key="X", enabled=False)
    assert definition.evaluate(FlagContext()) is False


def test_globally_enabled_flag_with_no_restrictions_is_true():
    definition = FlagDefinition(key="X", enabled=True)
    assert definition.evaluate(FlagContext()) is True


def test_environment_restriction_blocks_mismatched_environment():
    definition = FlagDefinition(key="X", enabled=True, environments=frozenset({"production"}))
    assert definition.evaluate(FlagContext(environment="development")) is False
    assert definition.evaluate(FlagContext(environment="production")) is True


def test_store_allowlist_blocks_non_listed_store():
    definition = FlagDefinition(key="X", enabled=True, store_allowlist=frozenset({"store-1"}))
    assert definition.evaluate(FlagContext(store_id="store-2")) is False
    assert definition.evaluate(FlagContext(store_id="store-1")) is True
    assert definition.evaluate(FlagContext(store_id=None)) is False


def test_rollout_percentage_zero_is_always_false():
    definition = FlagDefinition(key="X", enabled=True, rollout_percentage=0)
    assert definition.evaluate(FlagContext(user_id="u1")) is False


def test_rollout_percentage_hundred_is_always_true():
    definition = FlagDefinition(key="X", enabled=True, rollout_percentage=100)
    assert definition.evaluate(FlagContext(user_id="u1")) is True


def test_rollout_percentage_is_deterministic_for_same_identity():
    definition = FlagDefinition(key="X", enabled=True, rollout_percentage=50)
    context = FlagContext(user_id="stable-user")
    first = definition.evaluate(context)
    second = definition.evaluate(context)
    assert first == second


def test_rollout_percentage_distribution_is_roughly_bucketed():
    definition = FlagDefinition(key="X", enabled=True, rollout_percentage=50)
    results = [definition.evaluate(FlagContext(user_id=f"user-{i}")) for i in range(500)]
    enabled_count = sum(results)
    # Not a strict statistical assertion -- just checks the bucketing
    # isn't degenerate (all-true or all-false) for a 50% rollout.
    assert 100 < enabled_count < 400


def test_environment_flag_provider_returns_none_for_unknown_flag():
    provider = EnvironmentFlagProvider({"ENABLE_CHAT": True})
    assert provider.get_definition("ENABLE_AI") is None


def test_environment_flag_provider_returns_definition_for_known_flag():
    provider = EnvironmentFlagProvider({"ENABLE_CHAT": True})
    definition = provider.get_definition("ENABLE_CHAT")
    assert definition is not None
    assert definition.enabled is True


def test_chained_provider_returns_first_match():
    empty = EnvironmentFlagProvider({})
    fallback = EnvironmentFlagProvider({"ENABLE_POS": True})
    chain = ChainedFlagProvider([empty, fallback])
    definition = chain.get_definition("ENABLE_POS")
    assert definition is not None
    assert definition.enabled is True


def test_feature_flags_facade_fails_closed_when_unconfigured():
    FeatureFlags.configure(EnvironmentFlagProvider({}))
    assert FeatureFlags.is_enabled(FlagKey.ENABLE_MARKETPLACE) is False


def test_feature_flags_facade_respects_configured_provider():
    FeatureFlags.configure(EnvironmentFlagProvider({FlagKey.ENABLE_WALLET.value: True}))
    assert FeatureFlags.is_enabled(FlagKey.ENABLE_WALLET) is True


def test_feature_flags_get_definition_returns_disabled_default_for_unknown():
    FeatureFlags.configure(EnvironmentFlagProvider({}))
    definition = FeatureFlags.get_definition(FlagKey.ENABLE_B2B)
    assert definition.enabled is False


def test_all_mission_required_flags_exist_in_enum():
    required = {
        "ENABLE_AI",
        "ENABLE_CHAT",
        "ENABLE_POS",
        "ENABLE_ANALYTICS",
        "ENABLE_WALLET",
        "ENABLE_MARKETPLACE",
        "ENABLE_B2B",
        "ENABLE_WHOLESALE",
    }
    assert required.issubset({member.value for member in FlagKey})
