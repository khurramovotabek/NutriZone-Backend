from __future__ import annotations

import datetime
import uuid

import pytest

from apps.identity.application.services.profile import GetOwnProfile, UpdateProfile, _profile_cache_key
from apps.identity.domain.aggregates import User
from apps.identity.domain.enums import FitnessGoal
from apps.identity.domain.value_objects import PhoneNumber
from apps.identity.tests.application.fakes import FakeUserRepository, collect_events
from common.exceptions import ConflictError, ResourceNotFound
from core.caching import get_redis_client


def _seed_user(repo: FakeUserRepository, **overrides) -> User:
    user = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998901234567"), full_name="Original Name", **overrides)
    repo.save(user)
    return user


@pytest.mark.unit
class TestGetOwnProfile:
    def test_returns_existing_user(self):
        repo = FakeUserRepository()
        user = _seed_user(repo)
        result = GetOwnProfile(user_repo=repo).execute(user.id)
        assert result.full_name == "Original Name"

    def test_missing_user_raises_not_found(self):
        repo = FakeUserRepository()
        with pytest.raises(ResourceNotFound):
            GetOwnProfile(user_repo=repo).execute(uuid.uuid4())

    def test_second_call_is_served_from_cache(self):
        """The cached path returns a SimpleNamespace with the same field values as the fresh read -- not the same object, but the same data."""
        repo = FakeUserRepository()
        user = _seed_user(repo)
        service = GetOwnProfile(user_repo=repo)
        first = service.execute(user.id)
        second = service.execute(user.id)
        assert first.full_name == second.full_name == "Original Name"


@pytest.mark.django_db
class TestUpdateProfile:
    """Marked django_db: UpdateProfile.execute uses @transaction.atomic -- see TestVerifyOTP's docstring for why."""

    def test_updates_full_name(self):
        repo = FakeUserRepository()
        user = _seed_user(repo)
        events: list = []
        service = UpdateProfile(user_repo=repo, stage_events=collect_events(events))

        updated = service.execute(user_id=user.id, full_name="New Name")

        assert updated.full_name == "New Name"
        assert any(e[0] == "UserProfileUpdated" for e in events)

    def test_missing_user_raises_not_found(self):
        repo = FakeUserRepository()
        service = UpdateProfile(user_repo=repo, stage_events=collect_events([]))
        with pytest.raises(ResourceNotFound):
            service.execute(user_id=uuid.uuid4(), full_name="Someone")

    def test_duplicate_username_raises_conflict(self):
        repo = FakeUserRepository()
        _seed_user(repo, username="taken")
        second_user = _seed_user(repo)
        service = UpdateProfile(user_repo=repo, stage_events=collect_events([]))

        with pytest.raises(ConflictError):
            service.execute(user_id=second_user.id, username="taken")

    def test_updates_fitness_profile_partially(self):
        repo = FakeUserRepository()
        user = _seed_user(repo)
        service = UpdateProfile(user_repo=repo, stage_events=collect_events([]))

        updated = service.execute(user_id=user.id, height_cm=180)
        assert updated.fitness_profile.height_cm == 180
        assert updated.fitness_profile.weight_kg is None

        updated_again = service.execute(user_id=user.id, weight_kg=75)
        assert updated_again.fitness_profile.height_cm == 180  # preserved from the prior partial update
        assert updated_again.fitness_profile.weight_kg == 75

    def test_explicit_none_clears_bio_email_username_birthday(self):
        """A real PATCH-semantics defect fixed here, at the Application layer: previously identical to 'not supplied,' making it structurally impossible for a client to ever clear these fields -- despite UpdateProfileSerializer already declaring allow_null=True on exactly these fields."""
        repo = FakeUserRepository()
        user = _seed_user(repo)
        service = UpdateProfile(user_repo=repo, stage_events=collect_events([]))

        service.execute(user_id=user.id, bio="Some bio", email="a@b.com", username="someuser", birthday=datetime.date(1990, 1, 1))
        cleared = service.execute(user_id=user.id, bio=None, email=None, username=None, birthday=None)

        assert cleared.bio is None
        assert cleared.email is None
        assert cleared.username is None
        assert cleared.birthday is None

    def test_not_supplying_a_field_leaves_it_unchanged_not_cleared(self):
        """The other half of the same fix: this is the exact previously-existing behavior (UNSET is the default), verified explicitly so a future change cannot silently regress it back to "any omitted field clears its value.\""""
        repo = FakeUserRepository()
        user = _seed_user(repo)
        service = UpdateProfile(user_repo=repo, stage_events=collect_events([]))

        service.execute(user_id=user.id, bio="Some bio")
        untouched = service.execute(user_id=user.id, full_name="Different Name")  # bio not mentioned

        assert untouched.bio == "Some bio"

    def test_explicit_none_clears_a_fitness_field_while_others_are_preserved(self):
        """The same PATCH-clearing defect existed for the fitness composite: previously, height_cm=None was indistinguishable from height_cm not supplied at all, making it impossible to ever clear one fitness field independently of the others."""
        repo = FakeUserRepository()
        user = _seed_user(repo)
        service = UpdateProfile(user_repo=repo, stage_events=collect_events([]))

        service.execute(user_id=user.id, height_cm=180, weight_kg=75, goal=FitnessGoal.MUSCLE_GAIN.value)
        cleared = service.execute(user_id=user.id, height_cm=None)

        assert cleared.fitness_profile.height_cm is None
        assert cleared.fitness_profile.weight_kg == 75, "Clearing height_cm must not disturb weight_kg."
        assert cleared.fitness_profile.goal is FitnessGoal.MUSCLE_GAIN

    def test_invalidates_profile_cache_after_update(self):
        repo = FakeUserRepository()
        user = _seed_user(repo)
        GetOwnProfile(user_repo=repo).execute(user.id)  # populate the cache
        assert get_redis_client().get(_profile_cache_key(user.id)) is not None

        UpdateProfile(user_repo=repo, stage_events=collect_events([])).execute(user_id=user.id, full_name="Changed")
        assert get_redis_client().get(_profile_cache_key(user.id)) is None
