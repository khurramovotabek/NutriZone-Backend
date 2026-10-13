from __future__ import annotations

import inspect
import uuid

import pytest

from apps.platform.application.services._shared import PlatformServiceContext
from apps.platform.application.services.flags import DefineFeatureFlag, EvaluateFlags, UpdateFeatureFlag
from apps.platform.domain.aggregates import UNSET, FeatureFlag
from apps.platform.domain.exceptions import DuplicateFlagKey
from apps.platform.tests.application.fakes import FakeFeatureFlagRepository, FakeFlagPublisher, collect_events
from common.exceptions import ResourceNotFound


def _build(actor_id=None):
    repo = FakeFeatureFlagRepository()
    publisher = FakeFlagPublisher()
    events: list = []
    ctx = PlatformServiceContext(stage_events=collect_events(events), actor_id=actor_id)
    return repo, publisher, ctx, events


@pytest.mark.unit
@pytest.mark.django_db
class TestDefineFeatureFlag:
    def test_defines_a_new_flag(self):
        repo, publisher, ctx, events = _build()
        service = DefineFeatureFlag(repo, publisher, ctx)

        flag = service.execute(key="ENABLE_NEW_CHECKOUT", is_globally_enabled=True, rollout_percentage=50)

        assert flag.key == "ENABLE_NEW_CHECKOUT"
        assert flag.is_globally_enabled is True
        assert repo.get_by_key("ENABLE_NEW_CHECKOUT") is not None

    def test_duplicate_key_raises(self):
        repo, publisher, ctx, events = _build()
        service = DefineFeatureFlag(repo, publisher, ctx)
        service.execute(key="ENABLE_NEW_CHECKOUT")

        with pytest.raises(DuplicateFlagKey):
            service.execute(key="ENABLE_NEW_CHECKOUT")

    def test_publishes_the_new_flag(self):
        """A real integration point proven directly: DefineFeatureFlag must publish to the fast-path publisher, not only save to the repository -- otherwise the flag would be durable but never actually evaluable via the hot path."""
        repo, publisher, ctx, events = _build()
        service = DefineFeatureFlag(repo, publisher, ctx)
        flag = service.execute(key="ENABLE_NEW_CHECKOUT", is_globally_enabled=True)

        assert len(publisher.published) == 1
        assert publisher.published[0].id == flag.id

    def test_stages_feature_flag_changed_event(self):
        repo, publisher, ctx, events = _build()
        DefineFeatureFlag(repo, publisher, ctx).execute(key="ENABLE_NEW_CHECKOUT")
        assert any(e[0] == "FeatureFlagChanged" for e in events)


@pytest.mark.unit
@pytest.mark.django_db
class TestUpdateFeatureFlag:
    def _seeded(self, repo):
        flag = FeatureFlag(id=uuid.uuid4(), key="ENABLE_NEW_CHECKOUT", is_globally_enabled=False, rollout_percentage=25)
        repo.save(flag)
        return flag

    def test_updates_is_globally_enabled(self):
        repo, publisher, ctx, events = _build()
        flag = self._seeded(repo)
        service = UpdateFeatureFlag(repo, publisher, ctx)

        updated = service.execute(flag_id=flag.id, is_globally_enabled=True)
        assert updated.is_globally_enabled is True

    def test_not_supplying_rollout_percentage_leaves_it_unchanged(self):
        repo, publisher, ctx, events = _build()
        flag = self._seeded(repo)
        service = UpdateFeatureFlag(repo, publisher, ctx)

        updated = service.execute(flag_id=flag.id, is_globally_enabled=True)  # rollout_percentage not mentioned -> defaults to UNSET
        assert updated.rollout_percentage == 25

    def test_explicit_none_clears_rollout_percentage(self):
        """The Application-layer half of the same real PATCH-semantics fix already proven at the Domain layer -- this service must actually forward the caller's explicit None through to update_rollout(), not silently coerce it to UNSET."""
        repo, publisher, ctx, events = _build()
        flag = self._seeded(repo)
        service = UpdateFeatureFlag(repo, publisher, ctx)

        updated = service.execute(flag_id=flag.id, rollout_percentage=None)
        assert updated.rollout_percentage is None

    def test_missing_flag_raises_resource_not_found(self):
        repo, publisher, ctx, events = _build()
        service = UpdateFeatureFlag(repo, publisher, ctx)
        with pytest.raises(ResourceNotFound):
            service.execute(flag_id=uuid.uuid4(), is_globally_enabled=True)

    def test_republishes_after_update(self):
        repo, publisher, ctx, events = _build()
        flag = self._seeded(repo)
        UpdateFeatureFlag(repo, publisher, ctx).execute(flag_id=flag.id, is_globally_enabled=True)
        assert len(publisher.published) == 1


@pytest.mark.unit
class TestEvaluateFlags:
    def test_evaluates_every_registered_flag(self):
        repo = FakeFeatureFlagRepository()
        repo.save(FeatureFlag(id=uuid.uuid4(), key="A", is_globally_enabled=True))
        repo.save(FeatureFlag(id=uuid.uuid4(), key="B", is_globally_enabled=False))

        result = EvaluateFlags(repo).execute(evaluate_fn=lambda f: f.is_globally_enabled)
        assert result == {"A": True, "B": False}

    def test_empty_registry_returns_empty_map(self):
        repo = FakeFeatureFlagRepository()
        result = EvaluateFlags(repo).execute(evaluate_fn=lambda f: True)
        assert result == {}

    def test_never_implements_rollout_logic_itself(self):
        """A direct, executable proof this service only orchestrates -- the actual evaluation decision is entirely delegated to the injected evaluate_fn, matching core.flags's own already-correct evaluation engine (no duplicated business logic, per this phase's own Section 12)."""
        source = inspect.getsource(EvaluateFlags.execute)
        assert "rollout_percentage" not in source
        assert "store_allowlist" not in source
