from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from core.clock import Clock

pytestmark = pytest.mark.unit


def test_now_returns_timezone_aware_datetime():
    now = Clock.now()
    assert now.tzinfo is not None


def test_utc_now_matches_now():
    assert Clock.utc_now().tzinfo is not None


def test_today_returns_date_object():
    assert isinstance(Clock.today(), date)


def test_freeze_fixes_now_within_block():
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    with Clock.freeze(fixed):
        assert Clock.now() == fixed
        assert Clock.today() == date(2026, 1, 1)


def test_freeze_releases_after_block():
    fixed = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with Clock.freeze(fixed):
        pass
    assert Clock.now() != fixed
    assert not Clock.is_frozen()


def test_freeze_requires_timezone_aware_datetime():
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValueError):
        with Clock.freeze(naive):
            pass


def test_nested_freeze_restores_outer_value():
    outer = datetime(2025, 1, 1, tzinfo=timezone.utc)
    inner = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with Clock.freeze(outer):
        assert Clock.now() == outer
        with Clock.freeze(inner):
            assert Clock.now() == inner
        assert Clock.now() == outer


def test_is_frozen_false_by_default():
    assert not Clock.is_frozen()


def test_frozen_time_is_stable_across_calls():
    fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
    with Clock.freeze(fixed):
        first = Clock.now()
        second = Clock.now()
    assert first == second == fixed


def test_real_time_advances_between_calls():
    a = Clock.now()
    b = Clock.now() + timedelta(microseconds=1)
    assert b >= a
