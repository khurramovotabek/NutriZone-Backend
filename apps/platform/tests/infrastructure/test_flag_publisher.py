"""
`to_flag_definition()` is a pure function (no Django/database access),
so it can be tested directly even in an environment where Django is
unavailable -- unlike `DjangoFeatureFlagRepository`, which genuinely
requires a real database and is `@pytest.mark.django_db`-marked
elsewhere (not executable in this sandbox, disclosed in the
certification report rather than silently skipped).
"""
from __future__ import annotations

import uuid

from apps.platform.domain.aggregates import FeatureFlag
from apps.platform.infrastructure.flag_publisher import to_flag_definition


class TestToFlagDefinition:
    def test_translates_basic_fields(self):
        flag = FeatureFlag(id=uuid.uuid4(), key="ENABLE_X", is_globally_enabled=True, rollout_percentage=40)
        definition = to_flag_definition(flag)

        assert definition.key == "ENABLE_X"
        assert definition.enabled is True
        assert definition.rollout_percentage == 40

    def test_environments_always_none(self):
        """This aggregate has no environment-restriction concept (that's `core.flags.FlagKey`'s infra-flag territory, per that module's own docstring) -- the translation must never invent one."""
        flag = FeatureFlag(id=uuid.uuid4(), key="ENABLE_X")
        assert to_flag_definition(flag).environments is None

    def test_store_allowlist_extracted_from_rollout_scope(self):
        flag = FeatureFlag(id=uuid.uuid4(), key="ENABLE_X", rollout_scope={"store_allowlist": ["store-1", "store-2"]})
        definition = to_flag_definition(flag)
        assert definition.store_allowlist == frozenset({"store-1", "store-2"})

    def test_no_store_allowlist_in_scope_yields_none(self):
        flag = FeatureFlag(id=uuid.uuid4(), key="ENABLE_X", rollout_scope={"unrelated_key": "value"})
        assert to_flag_definition(flag).store_allowlist is None

    def test_disabled_flag_translates_correctly(self):
        flag = FeatureFlag(id=uuid.uuid4(), key="ENABLE_X", is_globally_enabled=False)
        assert to_flag_definition(flag).enabled is False
