"""
**Per this phase's own explicit warning, `NotificationTitle` and
`NotificationBody`'s length limits are NOT assumed identical** --
re-verified fresh from live source (`MAX_TITLE_LENGTH = 150`,
`MAX_BODY_LENGTH = 1000`) before writing any boundary test below.
"""
from __future__ import annotations

import pytest

from apps.notifications.domain.exceptions import EmptyNotificationContent, NotificationContentTooLong
from apps.notifications.domain.value_objects import MAX_BODY_LENGTH, MAX_TITLE_LENGTH, NotificationBody, NotificationTitle

pytestmark = pytest.mark.unit


def test_title_and_body_limits_are_genuinely_different():
    """Guards against ever assuming these two limits are equal -- they are not, and this test fails loudly if that ever changes silently."""
    assert MAX_TITLE_LENGTH == 150
    assert MAX_BODY_LENGTH == 1000
    assert MAX_TITLE_LENGTH != MAX_BODY_LENGTH


class TestNotificationTitle:
    def test_valid_construction(self):
        assert NotificationTitle("Your order shipped").value == "Your order shipped"

    def test_rejects_empty_string_with_specific_exception(self):
        with pytest.raises(EmptyNotificationContent):
            NotificationTitle("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(EmptyNotificationContent):
            NotificationTitle("   ")

    def test_rejects_too_long_with_specific_exception(self):
        with pytest.raises(NotificationContentTooLong):
            NotificationTitle("x" * (MAX_TITLE_LENGTH + 1))

    def test_exactly_max_length_allowed(self):
        NotificationTitle("x" * MAX_TITLE_LENGTH)

    def test_equality(self):
        assert NotificationTitle("Hi") == NotificationTitle("Hi")

    def test_immutability(self):
        title = NotificationTitle("Hi")
        with pytest.raises(Exception):
            title.value = "Changed"  # type: ignore[misc]


class TestNotificationBody:
    def test_valid_construction(self):
        assert NotificationBody("Your order is on its way.").value == "Your order is on its way."

    def test_rejects_empty_string_with_specific_exception(self):
        with pytest.raises(EmptyNotificationContent):
            NotificationBody("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(EmptyNotificationContent):
            NotificationBody("   ")

    def test_rejects_too_long_with_specific_exception(self):
        with pytest.raises(NotificationContentTooLong):
            NotificationBody("x" * (MAX_BODY_LENGTH + 1))

    def test_exactly_max_length_allowed(self):
        NotificationBody("x" * MAX_BODY_LENGTH)

    def test_title_length_limit_does_not_apply_to_body(self):
        """A concrete, executable proof that the two limits are independent -- a body longer than MAX_TITLE_LENGTH but within MAX_BODY_LENGTH must succeed."""
        assert MAX_TITLE_LENGTH < MAX_BODY_LENGTH
        NotificationBody("x" * (MAX_TITLE_LENGTH + 1))
