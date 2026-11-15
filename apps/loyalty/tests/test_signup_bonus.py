"""Launch gift: the first N verified customers get coins once; slots are numbered and never exceed the limit."""
from __future__ import annotations

import uuid
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure import signup_bonus
from apps.loyalty.infrastructure.models import LoyaltySettings, SignupBonusGrant, Wallet, WalletTransaction
from apps.notifications.infrastructure.models import NotificationModel

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _on(settings):
    settings.LOYALTY_SIGNUP_BONUS = True
    LoyaltySettings.objects.update_or_create(pk=1, defaults={"signup_bonus_enabled": True, "signup_bonus_coins": 5000, "signup_bonus_limit": 3})
    with mock.patch("apps.notifications.infrastructure.tasks.deliver_telegram_notification.delay"):
        yield


def _user(status="active"):
    return User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10_000_000:07d}", full_name="Test", status=status)


def _balance(user) -> int:
    w = Wallet.objects.filter(user_id=user.id).first()
    return w.balance if w else 0


def test_verified_sign_up_gets_the_gift_once_with_a_slot_number():
    u = _user()
    assert _balance(u) == 5000
    row = SignupBonusGrant.objects.get(user_id=u.id)
    assert row.number == 1 and row.transaction.amount == 5000 and "№1" in row.transaction.note
    u.full_name = "Renamed"
    u.save()  # later saves never pay again
    assert _balance(u) == 5000 and SignupBonusGrant.objects.count() == 1
    note = NotificationModel.objects.get(recipient_id=u.id, kind="signup_bonus")
    assert "+5 000" in note.i18n["uz"]["title"] and "№1" in note.i18n["uz"]["body"] and "birinchi 3 mijoz" in note.i18n["uz"]["body"]


def test_unverified_account_waits_until_it_becomes_active():
    u = _user(status="pending_verification")
    assert _balance(u) == 0
    u.status = "active"
    u.save()
    assert _balance(u) == 5000


def test_campaign_closes_at_the_limit():
    users = [_user() for _ in range(4)]
    assert [_balance(u) for u in users] == [5000, 5000, 5000, 0]
    assert list(SignupBonusGrant.objects.values_list("number", flat=True)) == [1, 2, 3]
    assert not signup_bonus.status().is_open and signup_bonus.status().remaining == 0


def test_disabled_campaign_pays_nothing():
    LoyaltySettings.objects.filter(pk=1).update(signup_bonus_enabled=False)
    assert _balance(_user()) == 0


def test_backfill_gives_existing_customers_slots_oldest_first(settings):
    settings.LOYALTY_SIGNUP_BONUS = False
    old = [_user() for _ in range(2)]
    settings.LOYALTY_SIGNUP_BONUS = True
    out = StringIO()
    call_command("grant_signup_bonus", "--existing", "--dry-run", stdout=out)
    assert "2 customer(s) would get" in out.getvalue() and SignupBonusGrant.objects.count() == 0
    call_command("grant_signup_bonus", "--existing", stdout=StringIO())
    assert [_balance(u) for u in old] == [5000, 5000]
    assert SignupBonusGrant.objects.get(user_id=old[0].id).number == 1
    call_command("grant_signup_bonus", "--existing", stdout=StringIO())  # re-run is a no-op
    assert WalletTransaction.objects.filter(note__startswith="Ro'yxatdan o'tish sovg'asi").count() == 2


def test_public_endpoint_shows_slots_left():
    _user()
    body = APIClient().get("/api/v1/loyalty/signup-bonus").json()["data"]
    assert body["open"] is True and body["coins"] == 5000 and body["limit"] == 3 and body["remaining"] == 2 and body["mine"] is None
