"""Opening gift: the first N customers who ORDER get coins once (on their first confirmed order); slots are numbered."""
from __future__ import annotations

import uuid
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure import signup_bonus
from apps.loyalty.infrastructure.models import LoyaltySettings, SignupBonusGrant, Wallet, WalletTransaction
from apps.notifications.infrastructure.models import NotificationModel
from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _on(settings):
    settings.LOYALTY_SIGNUP_BONUS = True
    LoyaltySettings.objects.update_or_create(pk=1, defaults={"signup_bonus_enabled": True, "signup_bonus_coins": 5000, "signup_bonus_limit": 3})
    with mock.patch("apps.notifications.infrastructure.tasks.deliver_telegram_notification.delay"):
        yield


def _user():
    return User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10_000_000:07d}", full_name="Test", status="active")


def _order(user, status="pending_payment") -> OrderModel:
    o = OrderModel.objects.create(
        order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}", customer_id=user.id, currency="UZS", status=status,
        shipping_recipient_name="A", shipping_line1="B", shipping_city="T", shipping_country_code="UZ",
        billing_recipient_name="A", billing_line1="B", billing_city="T", billing_country_code="UZ", placed_at=timezone.now(),
    )
    OrderLineItemModel.objects.create(order=o, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("100000"))
    return o


def _confirm(order):
    order.status = "confirmed"
    order.save()


def _gift(user) -> int:
    return int(WalletTransaction.objects.filter(wallet__user_id=user.id, note__startswith="Birinchi buyurtma sovg'asi").values_list("amount", flat=True).first() or 0)


def test_sign_up_alone_pays_nothing():
    u = _user()
    assert _gift(u) == 0 and not SignupBonusGrant.objects.exists()


def test_unconfirmed_order_waits_then_first_confirmation_pays_once():
    u = _user()
    order = _order(u)
    assert _gift(u) == 0
    _confirm(order)
    assert _gift(u) == 5000
    row = SignupBonusGrant.objects.get(user_id=u.id)
    assert row.number == 1 and row.source == "first_order" and "№1" in row.transaction.note
    _confirm(_order(u))  # a second order never pays again
    assert SignupBonusGrant.objects.count() == 1
    note = NotificationModel.objects.get(recipient_id=u.id, kind="signup_bonus")
    assert "+5 000" in note.i18n["uz"]["title"] and "№1" in note.i18n["uz"]["body"] and "xarid qilgan birinchi 3 mijoz" in note.i18n["uz"]["body"]


def test_campaign_closes_at_the_limit():
    users = [_user() for _ in range(4)]
    for u in users:
        _confirm(_order(u))
    assert [_gift(u) for u in users] == [5000, 5000, 5000, 0]
    assert list(SignupBonusGrant.objects.order_by("number").values_list("number", flat=True)) == [1, 2, 3]
    assert not signup_bonus.status().is_open and signup_bonus.status().remaining == 0


def test_disabled_campaign_pays_nothing():
    LoyaltySettings.objects.filter(pk=1).update(signup_bonus_enabled=False)
    u = _user()
    _confirm(_order(u))
    assert _gift(u) == 0


def test_backfill_pays_existing_buyers_earliest_first_and_skips_non_buyers(settings):
    settings.LOYALTY_SIGNUP_BONUS = False
    first, second, browser, unpaid = _user(), _user(), _user(), _user()
    _order(first, status="delivered")
    _order(second, status="confirmed")
    _order(unpaid, status="pending_payment")
    settings.LOYALTY_SIGNUP_BONUS = True
    out = StringIO()
    call_command("grant_signup_bonus", "--existing", "--dry-run", stdout=out)
    assert "2 customer(s) would get" in out.getvalue() and SignupBonusGrant.objects.count() == 0
    call_command("grant_signup_bonus", "--existing", stdout=StringIO())
    assert [_gift(u) for u in (first, second, browser, unpaid)] == [5000, 5000, 0, 0]
    assert SignupBonusGrant.objects.get(user_id=first.id).number == 1
    call_command("grant_signup_bonus", "--existing", stdout=StringIO())  # re-run is a no-op
    assert SignupBonusGrant.objects.count() == 2


def test_public_endpoint_shows_slots_left():
    _confirm(_order(_user()))
    body = APIClient().get("/api/v1/loyalty/signup-bonus").json()["data"]
    assert body["open"] is True and body["coins"] == 5000 and body["limit"] == 3 and body["remaining"] == 2 and body["mine"] is None
