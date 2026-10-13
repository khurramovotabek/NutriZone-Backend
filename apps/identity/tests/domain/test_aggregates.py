from __future__ import annotations

import datetime
import uuid

import pytest

from apps.identity.domain.aggregates import Role, User
from apps.identity.domain.enums import LanguagePreference, UserStatus
from apps.identity.domain.exceptions import AccountBlockedError, InvalidProfileTransitionError
from apps.identity.domain.value_objects import Email, PhoneNumber

pytestmark = pytest.mark.unit


def _make_user(status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(id=uuid.uuid4(), phone_number=PhoneNumber("+998901234567"), full_name="Test User", status=status)


class TestUserStatusTransitions:
    def test_activate_from_pending(self):
        user = _make_user(status=UserStatus.PENDING_VERIFICATION)
        user.activate()
        assert user.status == UserStatus.ACTIVE

    def test_block_sets_status_and_returns_event(self):
        user = _make_user()
        event = user.block(reason="fraud")
        assert user.status == UserStatus.BLOCKED
        assert event.reason == "fraud"
        assert event.user_id == user.id

    def test_block_already_blocked_raises(self):
        user = _make_user(status=UserStatus.BLOCKED)
        with pytest.raises(InvalidProfileTransitionError):
            user.block()

    def test_unblock_restores_active(self):
        user = _make_user(status=UserStatus.BLOCKED)
        user.unblock()
        assert user.status == UserStatus.ACTIVE

    def test_unblock_when_not_blocked_raises(self):
        user = _make_user(status=UserStatus.ACTIVE)
        with pytest.raises(InvalidProfileTransitionError):
            user.unblock()

    def test_activate_a_blocked_account_directly_is_forbidden(self):
        user = _make_user(status=UserStatus.BLOCKED)
        with pytest.raises(InvalidProfileTransitionError):
            user.activate()

    def test_assert_can_authenticate_passes_for_active(self):
        user = _make_user(status=UserStatus.ACTIVE)
        user.assert_can_authenticate()  # should not raise

    def test_assert_can_authenticate_raises_for_blocked(self):
        user = _make_user(status=UserStatus.BLOCKED)
        with pytest.raises(AccountBlockedError):
            user.assert_can_authenticate()


class TestUserProfileUpdate:
    def test_update_profile_applies_only_supplied_fields(self):
        user = _make_user()
        original_bio = user.bio
        event = user.update_profile(full_name="New Name")
        assert user.full_name == "New Name"
        assert user.bio == original_bio
        assert event.before["full_name"] == "Test User"
        assert event.after["full_name"] == "New Name"

    def test_update_profile_email(self):
        user = _make_user()
        user.update_profile(email=Email("new@example.com"))
        assert str(user.email) == "new@example.com"

    def test_update_profile_language(self):
        user = _make_user()
        user.update_profile(language=LanguagePreference.RU)
        assert user.language == LanguagePreference.RU

    def test_update_profile_with_no_args_is_a_no_op(self):
        user = _make_user()
        before_snapshot = user._snapshot()
        user.update_profile()
        assert user._snapshot() == before_snapshot

    def test_explicit_none_clears_bio(self):
        """A real PATCH-semantics defect fixed here: previously, None was indistinguishable from 'not supplied,' making it structurally impossible to ever clear a nullable field. Matches UpdateProfileSerializer's own allow_null=True declaration for bio."""
        user = _make_user()
        user.update_profile(bio="Some bio text")
        assert user.bio == "Some bio text"

        user.update_profile(bio=None)
        assert user.bio is None

    def test_not_supplying_bio_leaves_it_unchanged(self):
        """The other half of the same fix: not passing bio at all (the default UNSET) must still mean 'leave unchanged,' not accidentally clear it."""
        user = _make_user()
        user.update_profile(bio="Some bio text")
        user.update_profile(full_name="Different Name")  # bio not mentioned at all
        assert user.bio == "Some bio text"

    def test_explicit_none_clears_email_username_and_birthday(self):
        user = _make_user()
        user.update_profile(email=Email("a@b.com"), username="testuser", birthday=datetime.date(1990, 1, 1))
        assert user.email is not None
        assert user.username == "testuser"
        assert user.birthday is not None

        user.update_profile(email=None, username=None, birthday=None)
        assert user.email is None
        assert user.username is None
        assert user.birthday is None

    def test_birthday_is_a_date_not_a_datetime(self):
        """A real type-consistency defect fixed here: the Domain aggregate previously annotated birthday as `datetime`, while the ORM (`models.DateField`) and serializer (`serializers.DateField`) both use `date` -- a documentation/type mismatch, not a runtime crash (Django's ORM already returned real `date` objects), but a real correctness gap nonetheless."""
        user = _make_user()
        user.update_profile(birthday=datetime.date(1995, 6, 15))
        assert isinstance(user.birthday, datetime.date)
        assert not isinstance(user.birthday, datetime.datetime)

    def test_set_avatar_updates_media_id(self):
        user = _make_user()
        media_id = uuid.uuid4()
        user.set_avatar(media_id)
        assert user.profile_picture_media_id == media_id


class TestRoleAggregate:
    def test_assign_to_returns_event_with_role_and_user(self):
        role = Role(id=uuid.uuid4(), code="customer", name="Customer")
        user_id = uuid.uuid4()
        event = role.assign_to(user_id)
        assert event.user_id == user_id
        assert event.role_id == role.id
        assert event.role_code == "customer"
        assert event.store_id is None

    def test_assign_to_with_store_scope(self):
        role = Role(id=uuid.uuid4(), code="store_manager", name="Store Manager")
        store_id = uuid.uuid4()
        event = role.assign_to(uuid.uuid4(), store_id=store_id)
        assert event.store_id == store_id
