"""Customer inbox: business events create localized, de-duplicated notifications; the inbox API; dashboard broadcasts."""
from __future__ import annotations

import importlib
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure import services as loyalty
from apps.loyalty.infrastructure.models import LoyaltySettings, LoyaltyTier
from apps.notifications.infrastructure import notify
from apps.notifications.infrastructure.models import NotificationBroadcast, NotificationModel
from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _no_telegram():
    """No Celery/Telegram in tests: record which notifications would have gone to Telegram."""
    sent = []
    with mock.patch("apps.notifications.infrastructure.tasks.deliver_telegram_notification.delay", side_effect=lambda nid: sent.append(nid)), \
         mock.patch("apps.loyalty.infrastructure.tasks.send_loyalty_notification.delay"), \
         mock.patch("apps.notifications.infrastructure.tasks.run_notification_broadcast.delay", side_effect=lambda bid: notify.run_broadcast(bid)):
        yield sent


def _user(**extra) -> User:
    return User.objects.create(phone_number=f"+99893{uuid.uuid4().int % 10_000_000:07d}", full_name="Test Mijoz", status="active", **extra)


def _order(user, status="pending_payment") -> OrderModel:
    o = OrderModel.objects.create(
        order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}", customer_id=user.id, currency="UZS", status=status,
        shipping_recipient_name="A", shipping_line1="B", shipping_city="T", shipping_country_code="UZ",
        billing_recipient_name="A", billing_line1="B", billing_city="T", billing_country_code="UZ", placed_at=timezone.now(),
    )
    OrderLineItemModel.objects.create(order=o, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("100000"))
    return o


def _inbox(user, kind=None):
    qs = NotificationModel.objects.filter(recipient_id=user.id)
    return qs.filter(kind=kind) if kind else qs


def test_welcome_note_for_a_new_customer():
    user = _user()
    row = _inbox(user, "welcome").get()
    assert row.i18n["uz"]["title"].endswith("'ga xush kelibsiz!") and row.link == "/loyalty"


def test_order_status_changes_notify_once_each_in_three_languages(_no_telegram):
    user = _user(telegram_user_id=777000111)
    order = _order(user)
    for status in ("confirmed", "processing", "shipped", "delivered"):
        order.status = status
        order.save()
    order.save()  # a re-save of the same status never notifies twice
    kinds = list(_inbox(user).exclude(kind="welcome").order_by("created_at").values_list("kind", flat=True))
    assert kinds == ["order_confirmed", "order_processing", "order_shipped", "order_delivered"]
    shipped = _inbox(user, "order_shipped").get()
    assert order.order_number in shipped.i18n["uz"]["body"] and "Заказ в пути" == shipped.i18n["ru"]["title"]
    assert shipped.link == f"/orders/{order.order_number}"
    assert str(shipped.id) in _no_telegram  # the linked customer also gets it on Telegram


def test_guest_order_is_skipped():
    o = _order(_user())
    OrderModel.objects.filter(pk=o.pk).update(customer_id=None)
    o.refresh_from_db()
    o.status = "confirmed"
    o.save()
    assert not NotificationModel.objects.filter(kind="order_confirmed").exists()


def test_manual_coin_grant_and_tier_change_reach_the_inbox(settings):
    settings.LOYALTY_EARN_SINCE = ""
    seed = importlib.import_module("apps.loyalty.infrastructure.migrations.0004_eight_tier_ladder")
    for slug, name, lo, hi, pct, icon, color, _desc in seed.LADDER:
        LoyaltyTier.objects.update_or_create(slug=slug, defaults={"name": name, "min_spend": Decimal(lo), "max_spend": Decimal(hi) if hi else None, "percent": Decimal(pct), "icon": icon, "color": color})
    LoyaltySettings.objects.update_or_create(pk=1, defaults={})
    user = _user()
    loyalty.adjust(user.id, 5000, "Tug'ilgan kun sovg'asi", actor="admin")
    granted = _inbox(user, "coins_granted").get()
    assert granted.i18n["uz"]["title"] == "+5 000 coin sovg'a" and "Tug'ilgan kun sovg'asi" in granted.i18n["uz"]["body"]
    top = LoyaltyTier.objects.order_by("-min_spend").first()
    loyalty.set_tier(user.id, top, "VIP", actor="admin")
    assert top.name in _inbox(user, "tier_changed").get().i18n["uz"]["title"]


def test_inbox_api_is_scoped_localized_and_marks_read():
    me, other = _user(), _user()
    notify.create_now(me.id, "promo_code", {"code": "SPORT10", "discount": "10%"})
    notify.create_now(other.id, "promo_code", {"code": "SECRET", "discount": "50%"})
    from apps.identity.infrastructure.security import SimpleJWTTokenIssuer

    client = APIClient()
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {SimpleJWTTokenIssuer().issue(me.id).access_token}"

    body = client.get("/api/v1/notifications/inbox?lang=ru").json()["data"]
    titles = [i["title"] for i in body["items"]]
    assert "Новый промокод: SPORT10" in titles and not any("SECRET" in t for t in titles)
    assert body["unread"] == 2  # welcome + promo
    assert client.get("/api/v1/notifications/inbox/unread-count").json()["data"]["unread"] == 2

    first = body["items"][0]["id"]
    assert client.post("/api/v1/notifications/inbox/read", {"ids": [first]}, format="json").json()["data"]["unread"] == 1
    foreign = _inbox(other).first()
    client.post("/api/v1/notifications/inbox/read", {"ids": [str(foreign.id)]}, format="json")
    foreign.refresh_from_db()
    assert foreign.status != "read"  # can never touch someone else's notification
    assert client.post("/api/v1/notifications/inbox/read", {"all": True}, format="json").json()["data"]["unread"] == 0
    assert APIClient().get("/api/v1/notifications/inbox").status_code in (401, 403)


def test_broadcast_reaches_the_audience_once():
    a, b = _user(), _user()
    blocked = _user()
    User.objects.filter(pk=blocked.pk).update(status="blocked")
    texts = notify.render("announcement", {"title": "Yangi filial ochildi", "body": "Chilonzorda kutamiz!"})
    bc = NotificationBroadcast.objects.create(kind="announcement", title="Yangi filial ochildi", body="Chilonzorda kutamiz!", i18n=texts, audience="all")
    notify.run_broadcast(bc.id)
    notify.run_broadcast(bc.id)  # re-running a finished broadcast is a no-op
    bc.refresh_from_db()
    assert bc.status == "sent"
    assert _inbox(a, "announcement").count() == 1 and _inbox(b, "announcement").count() == 1
    assert not _inbox(blocked, "announcement").exists()


def test_broadcast_to_one_phone():
    target, other = _user(), _user()
    bc = NotificationBroadcast.objects.create(kind="announcement", title="Test", body="Salom", audience="phone", target=target.phone_number[-9:])
    assert notify.run_broadcast(bc.id)["recipients"] == 1
    assert _inbox(target, "announcement").exists() and not _inbox(other, "announcement").exists()


def test_promo_code_is_announced_once_when_it_goes_live():
    from apps.pricing.infrastructure.models import CouponModel

    customer = _user()
    coupon = CouponModel.objects.create(code=f"QA{uuid.uuid4().hex[:6].upper()}", coupon_type="coupon", status="draft", discount_value_type="percentage", discount_percentage=Decimal("15"))
    assert not NotificationBroadcast.objects.filter(source="promo_code", source_ref=str(coupon.pk)).exists()  # a draft is not announced

    coupon.status = "active"
    coupon.save()
    coupon.save()  # editing a live promo never re-broadcasts
    assert NotificationBroadcast.objects.filter(source="promo_code", source_ref=str(coupon.pk)).count() == 1
    row = _inbox(customer, "promo_code").get()
    assert row.i18n["uz"]["title"] == f"Yangi promokod: {coupon.code}" and "15%" in row.i18n["ru"]["body"]


def test_an_already_live_promo_is_not_announced_on_edit():
    from apps.pricing.infrastructure.models import CouponModel

    _user()
    with mock.patch("apps.notifications.infrastructure.inbox_signals._announce") as announce:
        coupon = CouponModel.objects.create(code=f"QB{uuid.uuid4().hex[:6].upper()}", coupon_type="coupon", status="active", discount_value_type="percentage", discount_percentage=Decimal("5"))
        assert announce.call_count == 1  # created live -> announced
        coupon.max_redemptions = 100
        coupon.save()
        assert announce.call_count == 1


def _opt_out_of_telegram(user, notification_type: str) -> None:
    from apps.notifications.infrastructure.models import NotificationPreferenceModel

    NotificationPreferenceModel.objects.create(user_id=user.id, disabled_combinations=[["telegram", notification_type]])


def test_telegram_respects_the_customers_own_preference():
    gateway = mock.Mock()
    gateway.send_message_with_keyboard.return_value = "msg-1"
    muted = _user(telegram_user_id=777000201)
    _opt_out_of_telegram(muted, "promotional")
    promo = notify.create_now(muted.id, "announcement", {"title": "Aksiya", "body": "Chegirma"})
    order_update = notify.create_now(muted.id, "welcome", {})

    with mock.patch("apps.notifications.infrastructure.composition.build_telegram_gateway", return_value=gateway):
        assert notify.send_telegram(promo) is False  # promotional turned off -- stays in the inbox only
        assert notify.send_telegram(order_update) is True  # other categories still delivered

    assert NotificationModel.objects.filter(id=promo).exists()
    assert gateway.send_message_with_keyboard.call_count == 1


def test_broadcast_skips_opted_out_customers_without_counting_failures():
    gateway = mock.Mock()
    gateway.send_message_with_keyboard.return_value = "msg-1"
    keen = _user(telegram_user_id=777000202)
    muted = _user(telegram_user_id=777000203)
    _opt_out_of_telegram(muted, "promotional")
    texts = notify.render("announcement", {"title": "Aksiya", "body": "Chegirma"})
    bc = NotificationBroadcast.objects.create(kind="announcement", title="Aksiya", body="Chegirma", i18n=texts, audience="phone", target=keen.phone_number[-9:], send_in_app=True, send_telegram=True)
    bc2 = NotificationBroadcast.objects.create(kind="announcement", title="Aksiya", body="Chegirma", i18n=texts, audience="phone", target=muted.phone_number[-9:], send_in_app=True, send_telegram=True)

    with mock.patch("apps.notifications.infrastructure.composition.build_telegram_gateway", return_value=gateway), mock.patch("time.sleep"):
        first = notify.run_broadcast(bc.id)
        second = notify.run_broadcast(bc2.id)

    assert first["telegram_sent"] == 1
    assert second["telegram_sent"] == 0 and second["telegram_failed"] == 0
    assert NotificationModel.objects.filter(recipient_id=muted.id, broadcast=bc2).exists()  # still in the inbox
