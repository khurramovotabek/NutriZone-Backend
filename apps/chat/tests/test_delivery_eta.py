"""Estimated delivery day: zone promise in working days (Sunday off), pickup has none."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from apps.chat.infrastructure.automation import add_working_days, delivery_eta

TZ = ZoneInfo("Asia/Tashkent")


@pytest.mark.parametrize("start,days,expected", [
    (date(2026, 11, 13), 1, date(2026, 11, 14)),  # Friday + 1 -> Saturday
    (date(2026, 11, 14), 1, date(2026, 11, 16)),  # Saturday + 1 -> Monday (Sunday skipped)
    (date(2026, 11, 14), 2, date(2026, 11, 17)),
    (date(2026, 11, 15), 0, date(2026, 11, 16)),  # a Sunday start moves to Monday
])
def test_add_working_days(start, days, expected):
    assert add_working_days(start, days) == expected


def _order(**kw):
    base = {"status": "confirmed", "fulfilment_method": "delivery", "delivery_zone": "tashkent",
            "placed_at": datetime(2026, 11, 14, 12, 0, tzinfo=TZ), "created_at": None}
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.django_db
def test_delivery_eta_follows_the_zone_promise():
    today = mock.patch("apps.chat.infrastructure.automation.timezone.localdate", return_value=date(2026, 11, 14))
    with today:
        assert delivery_eta(_order()) == date(2026, 11, 16)
        assert delivery_eta(_order(delivery_zone="regions")) == date(2026, 11, 17)
        assert delivery_eta(_order(fulfilment_method="pickup")) is None
        assert delivery_eta(_order(status="delivered")) is None
