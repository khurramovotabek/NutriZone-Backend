from __future__ import annotations

import uuid

import pytest

from apps.platform.domain.aggregates import UNSET, FeatureFlag
from apps.platform.domain.exceptions import InvalidRolloutPercentage


def _make_flag(**overrides) -> FeatureFlag:
    defaults = {"id": uuid.uuid4(), "key": "ENABLE_NEW_CHECKOUT"}
    defaults.update(overrides)
    return FeatureFlag(**defaults)


class TestFeatureFlagConstruction:
    def test_valid_construction(self):
        flag = _make_flag(is_globally_enabled=True, rollout_percentage=50)
        assert flag.is_globally_enabled is True
        assert flag.rollout_percentage == 50

    def test_defaults(self):
        flag = _make_flag()
        assert flag.is_globally_enabled is False
        assert flag.rollout_percentage is None
        assert flag.rollout_scope == {}

    @pytest.mark.parametrize("pct", [-1, 101, -50, 200])
    def test_rejects_out_of_range_rollout_percentage(self, pct):
        with pytest.raises(InvalidRolloutPercentage):
            _make_flag(rollout_percentage=pct)

    @pytest.mark.parametrize("pct", [0, 1, 50, 99, 100])
    def test_accepts_boundary_and_mid_range_rollout_percentage(self, pct):
        flag = _make_flag(rollout_percentage=pct)
        assert flag.rollout_percentage == pct


class TestUpdateRollout:
    def test_not_supplying_any_field_is_a_no_op(self):
        flag = _make_flag(is_globally_enabled=True, rollout_percentage=25, rollout_scope={"a": 1})
        flag.update_rollout()
        assert flag.is_globally_enabled is True
        assert flag.rollout_percentage == 25
        assert flag.rollout_scope == {"a": 1}

    def test_updates_is_globally_enabled(self):
        flag = _make_flag(is_globally_enabled=False)
        flag.update_rollout(is_globally_enabled=True)
        assert flag.is_globally_enabled is True

    def test_updates_rollout_scope(self):
        flag = _make_flag()
        flag.update_rollout(rollout_scope={"store_allowlist": ["a", "b"]})
        assert flag.rollout_scope == {"store_allowlist": ["a", "b"]}

    def test_explicit_none_clears_rollout_percentage(self):
        """A real PATCH-semantics fix, matching the identical bug already found and fixed in the Identity module: rollout_percentage=None must genuinely clear it (a real Domain state -- "no rollout gating"), not be indistinguishable from not supplying it at all."""
        flag = _make_flag(rollout_percentage=50)
        flag.update_rollout(rollout_percentage=None)
        assert flag.rollout_percentage is None

    def test_not_supplying_rollout_percentage_leaves_it_unchanged(self):
        """The other half of the same fix: UNSET (the default) must not be confused with an explicit None."""
        flag = _make_flag(rollout_percentage=50)
        flag.update_rollout(is_globally_enabled=True)  # rollout_percentage not mentioned at all
        assert flag.rollout_percentage == 50

    def test_setting_a_new_rollout_percentage_value(self):
        flag = _make_flag(rollout_percentage=10)
        flag.update_rollout(rollout_percentage=75)
        assert flag.rollout_percentage == 75

    def test_update_rollout_still_validates_the_new_percentage(self):
        flag = _make_flag(rollout_percentage=50)
        with pytest.raises(InvalidRolloutPercentage):
            flag.update_rollout(rollout_percentage=150)

    def test_unset_sentinel_is_distinct_from_none(self):
        assert UNSET is not None
        assert UNSET != None  # noqa: E711 - explicit, deliberate equality check, not an identity-vs-equality mistake
