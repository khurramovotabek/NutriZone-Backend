"""Rolling tier window, coin expiry (FIFO lots), checkout redemption/refund, referrals, Telegram notifications."""
from __future__ import annotations

import importlib
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure import notifications, services
from apps.loyalty.infrastructure.models import (
    LoyaltySettings,
    LoyaltyTier,
    Referral,
    Wallet,
    WalletTransaction,
)
from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _setup(settings):
    settings.LOYALTY_EARN_SINCE = ""
    seed = importlib.import_module("apps.loyalty.infrastructure.migrations.0004_eight_tier_ladder")
    for slug, name, lo, hi, pct, icon, color, _desc in seed.LADDER:
        LoyaltyTier.objects.update_or_create(slug=slug, defaults={"name": name, "min_spend": Decimal(lo), "max_spend": Decimal(hi) if hi else None, "percent": Decimal(pct), "icon": icon, "color": color})
    LoyaltySettings.objects.update_or_create(pk=1, defaults={})


@pytest.fixture(autouse=True)
def sent():
    """Captures Telegram notifications instead of hitting Celery/Telegram."""
    calls = []
    with mock.patch.object(notifications, "queue", side_effect=lambda kind, user_id, **p: calls.append((kind, user_id, p))):
        yield calls


def _user(**extra):
    return User.objects.create(phone_number=f"+99891{uuid.uuid4().int % 10_000_000:07d}", full_name="Ali Valiyev", **extra)


def _order(user, amount: str, status="confirmed", placed_at=None) -> OrderModel:
    o = OrderModel.objects.create(
        order_number=f"ORD-{uuid.uuid4().hex[:10]}", customer_id=user.id, currency="UZS", status=status,
        shipping_recipient_name="A", shipping_line1="B", shipping_city="T", shipping_country_code="UZ",
        billing_recipient_name="A", billing_line1="B", billing_city="T", billing_country_code="UZ",
        placed_at=placed_at or timezone.now(),
    )
    OrderLineItemModel.objects.create(order=o, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal(amount))
    return o


def _status(order, status):
    order.status = status
    order.save()


def _balance(user) -> int:
    return Wallet.objects.get(user_id=user.id).balance


def _lots_sum(user) -> int:
    return sum(WalletTransaction.objects.filter(wallet__user_id=user.id, remaining__gt=0).values_list("remaining", flat=True))


# ---------------------------------------------------------------- rolling window


def test_tier_counts_only_the_last_365_days():
    u = _user()
    _order(u, "15000000", status="completed", placed_at=timezone.now() - timedelta(days=400))  # outside window
    _order(u, "2000000", status="completed", placed_at=timezone.now() - timedelta(days=30))
    s = services.summary(u.id)
    assert s.total_spend == Decimal("2000000")
    assert s.current_tier.slug == "silver"


def test_window_zero_means_lifetime():
    LoyaltySettings.objects.filter(pk=1).update(tier_window_days=0)
    u = _user()
    _order(u, "15000000", status="completed", placed_at=timezone.now() - timedelta(days=400))
    assert services.summary(u.id).current_tier.slug == "diamond"


# ---------------------------------------------------------------- expiry


def test_lot_expires_and_is_burned_fifo():
    u = _user()
    old = services.adjust(u.id, 10_000, "old")
    services.adjust(u.id, 5_000, "new")
    WalletTransaction.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    assert services.expire_lots() == 1
    assert _balance(u) == 5_000 == _lots_sum(u)
    burn = WalletTransaction.objects.get(wallet__user_id=u.id, kind="expiry")
    assert burn.amount == -10_000 and burn.allocations == [{"lot": str(old.id), "amount": 10_000}]


def test_spending_consumes_soonest_expiring_lot_first():
    u = _user()
    later = services.adjust(u.id, 10_000, "later")
    sooner = services.adjust(u.id, 10_000, "sooner")
    WalletTransaction.objects.filter(pk=sooner.pk).update(expires_at=timezone.now() + timedelta(days=3))
    spend = services.redeem_for_order(u.id, 12_000, uuid.uuid4(), "ORD-X", Decimal("100000"))
    assert spend.allocations[0] == {"lot": str(sooner.id), "amount": 10_000}
    assert spend.allocations[1] == {"lot": str(later.id), "amount": 2_000}
    assert _balance(u) == 8_000 == _lots_sum(u)


def test_expiry_reminder_task_notifies_once(sent):
    from apps.loyalty.infrastructure.tasks import expire_coins

    u = _user()
    lot = services.adjust(u.id, 7_000, "gift")
    WalletTransaction.objects.filter(pk=lot.pk).update(expires_at=timezone.now() + timedelta(days=3))
    expire_coins()
    expire_coins()
    reminders = [c for c in sent if c[0] == "expiring"]
    assert len(reminders) == 1 and reminders[0][2]["coins"] == 7_000


# ---------------------------------------------------------------- redemption


def test_redemption_limits():
    u = _user()
    services.adjust(u.id, 50_000, "gift")
    assert services.max_redeemable(u.id, Decimal("100000")) == (30_000, 50_000)  # 30% cap
    with pytest.raises(services.LoyaltyError) as exc:
        services.validate_redemption(u.id, 30_001, Decimal("100000"))
    assert exc.value.code == "REDEEM_ABOVE_LIMIT"
    with pytest.raises(services.LoyaltyError) as exc:
        services.validate_redemption(u.id, 500, Decimal("100000"))
    assert exc.value.code == "REDEEM_BELOW_MINIMUM"
    assert services.validate_redemption(u.id, 30_000, Decimal("100000")) == 30_000


def test_allocate_discount_is_exact_and_bounded():
    shares = services.allocate_discount([Decimal("100000"), Decimal("50000"), Decimal("33333")], Decimal("30000"))
    assert sum(shares) == Decimal("30000")
    assert all(share <= line for share, line in zip(shares, [Decimal("100000"), Decimal("50000"), Decimal("33333")], strict=True))


def test_cancelled_order_returns_spent_coins_to_their_lots():
    u = _user()
    lot = services.adjust(u.id, 20_000, "gift")
    order = _order(u, "100000")
    services.redeem_for_order(u.id, 20_000, order.id, order.order_number, Decimal("100000"))
    assert _balance(u) == 0

    _status(order, "cancelled")
    assert _balance(u) == 20_000 == _lots_sum(u)
    assert WalletTransaction.objects.get(pk=lot.pk).remaining == 20_000
    services.sync_order(order.id)  # idempotent
    assert WalletTransaction.objects.filter(order_id=order.id, kind="refund").count() == 1


def test_coins_paid_do_not_earn_coins():
    u = _user()
    order = _order(u, "1000000")
    # 100 000 of the order paid with coins -> the line carries it as discount
    OrderLineItemModel.objects.filter(order=order).update(discount_amount=Decimal("100000"))
    _status(order, "delivered")
    assert WalletTransaction.objects.get(order_id=order.id, kind="earn").amount == 9_000  # 1% of 900 000


# ---------------------------------------------------------------- referral


def test_referral_pays_both_sides_on_first_delivered_order(sent):
    referrer, friend = _user(), _user()
    code = services.referral_code_for(referrer.id)
    assert code.startswith("NZ") and services.referral_code_for(referrer.id) == code

    services.claim_referral(friend.id, code)
    order = _order(friend, "300000")
    _status(order, "delivered")

    assert Referral.objects.get(referee=friend).status == "rewarded"
    assert WalletTransaction.objects.get(wallet__user_id=referrer.id, kind="referral").amount == 5_000
    assert WalletTransaction.objects.get(wallet__user_id=friend.id, kind="referral").amount == 5_000
    assert sum(1 for c in sent if c[0] == "referral") == 2

    _status(_order(friend, "300000"), "delivered")  # second order pays nothing extra
    assert WalletTransaction.objects.filter(kind="referral").count() == 2


@pytest.mark.parametrize("case", ["self", "twice", "existing_customer", "bad_code", "cycle"])
def test_referral_abuse_is_rejected(case):
    a, b = _user(), _user()
    code_a = services.referral_code_for(a.id)
    if case == "self":
        user, code, expected = a, code_a, "REFERRAL_SELF"
    elif case == "twice":
        services.claim_referral(b.id, code_a)
        user, code, expected = b, services.referral_code_for(_user().id), "REFERRAL_NOT_ELIGIBLE"
    elif case == "existing_customer":
        _order(b, "100000", status="delivered")
        user, code, expected = b, code_a, "REFERRAL_NOT_ELIGIBLE"
    elif case == "bad_code":
        user, code, expected = b, "NZNOPE00", "REFERRAL_CODE_INVALID"
    else:
        services.claim_referral(b.id, code_a)  # a invited b
        user, code, expected = a, services.referral_code_for(b.id), "REFERRAL_CYCLE"
    with pytest.raises(services.LoyaltyError) as exc:
        services.claim_referral(user.id, code)
    assert exc.value.code == expected


# ---------------------------------------------------------------- notifications


def test_tier_upgrade_is_announced(sent):
    u = _user()
    _order(u, "2900000", status="completed")  # silver
    order = _order(u, "500000")
    _status(order, "delivered")  # 3.4M after this order -> gold
    kinds = [c[0] for c in sent]
    assert "earned" in kinds
    tier_up = [c for c in sent if c[0] == "tier_up"]
    assert tier_up and tier_up[0][2]["tier_slug"] == "gold"


def test_notification_renders_in_customer_language():
    u = _user(telegram_user_id=777000111, language="ru")
    tier = LoyaltyTier.objects.get(slug="elite")
    gateway = mock.Mock()
    with mock.patch("apps.notifications.infrastructure.composition.build_telegram_gateway", return_value=gateway):
        assert notifications.send("tier_up", u.id, {"tier_slug": tier.slug}) is True
    chat_id, text, keyboard = gateway.send_message_with_keyboard.call_args.args
    assert chat_id == "777000111" and "Поздравляем" in text and "Elite" in text and "6%" in text
    assert keyboard[0][0]["callback_data"] == "menu:loyalty"


def test_no_telegram_account_means_no_send():
    u = _user()
    assert notifications.send("tier_up", u.id, {"tier_slug": "gold"}) is False


# ---------------------------------------------------------------- API


def _auth(client, user):
    from apps.identity.infrastructure.security import SimpleJWTTokenIssuer

    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {SimpleJWTTokenIssuer().issue(user.id).access_token}"
    return client


def test_me_exposes_programme_expiry_and_referral(client):
    u = _user()
    lot = services.adjust(u.id, 4_000, "gift")
    WalletTransaction.objects.filter(pk=lot.pk).update(expires_at=timezone.now() + timedelta(days=10))
    data = _auth(client, u).get("/api/v1/loyalty/me").json()["data"]
    assert data["programme"]["max_redeem_percent"] == 30
    assert data["expiring"]["coins"] == 4_000
    assert data["referral"]["code"].startswith("NZ") and data["referral"]["can_enter_code"] is True


def test_claim_api_returns_stable_error_codes(client):
    u = _user()
    body = _auth(client, u).post("/api/v1/loyalty/referral/claim", {"code": services.referral_code_for(u.id)}, content_type="application/json").json()
    assert body["success"] is False and body["error"]["code"] == "REFERRAL_SELF"


def test_me_lists_the_expiry_schedule_soonest_first(client):
    u = _user()
    a, b, c = (services.adjust(u.id, n, "gift") for n in (1_000, 2_000, 3_000))
    WalletTransaction.objects.filter(pk=a.pk).update(expires_at=timezone.now() + timedelta(days=40))
    WalletTransaction.objects.filter(pk=b.pk).update(expires_at=timezone.now() + timedelta(days=5))
    WalletTransaction.objects.filter(pk=c.pk).update(expires_at=timezone.now() + timedelta(days=5, minutes=1))
    schedule = _auth(client, u).get("/api/v1/loyalty/me").json()["data"]["expiry_schedule"]
    assert [row["coins"] for row in schedule] in ([5_000, 1_000], [2_000, 3_000, 1_000])  # same-day lots merge unless they straddle midnight
    assert sum(row["coins"] for row in schedule) == 6_000


def test_transactions_filter_by_direction_server_side(client):
    u = _user()
    o = _order(u, "500000", status="confirmed")
    services.adjust(u.id, 9_000, "gift")
    services.redeem_for_order(u.id, 2_000, o.id, o.order_number, Decimal("500000"))
    for _ in range(3):
        services.adjust(u.id, 100, "small")
    api = _auth(client, u)

    spent = api.get("/api/v1/loyalty/me/transactions?direction=out&page_size=2").json()
    assert spent["pagination"]["total_count"] == 1
    row = spent["data"][0]
    assert row["kind"] == "spend" and row["order_linkable"] is True and row["expires_at"] is None

    received = api.get("/api/v1/loyalty/me/transactions?direction=in&page_size=2").json()
    assert received["pagination"]["total_count"] == 4 and received["pagination"]["total_pages"] == 2
    assert all(r["amount"] > 0 and r["expires_at"] for r in received["data"])


# ---------------------------------------------------------------- tier at risk / rate


def test_purchases_add_up_to_qualifying_spend():
    u = _user()
    _order(u, "700000", status="delivered", placed_at=timezone.now() - timedelta(days=100))
    _order(u, "500000", status="completed", placed_at=timezone.now() - timedelta(days=10))
    _order(u, "900000", status="cancelled")
    rows = services.qualifying_purchases(u.id, services.window_start())
    assert [a for _w, a in rows] == [Decimal("700000"), Decimal("500000")]
    assert sum(a for _w, a in rows) == services.qualifying_spend(u.id)[0]


def test_tier_risk_names_the_deadline_and_the_gap():
    u = _user()
    now = timezone.now()
    _order(u, "2500000", status="delivered", placed_at=now - timedelta(days=355))  # leaves the window in ~10 days
    _order(u, "800000", status="delivered", placed_at=now - timedelta(days=20))
    assert services.summary(u.id).current_tier.slug == "gold"  # 3.3M

    risk = services.tier_risk(u.id, now=now)
    assert risk.tier.slug == "gold" and risk.falls_to.slug == "bronze"
    assert risk.needed == Decimal("2200000")  # 3M floor − 800K that stays
    assert abs((risk.drop_at - (now + timedelta(days=10))).total_seconds()) < 60


def test_tier_risk_is_none_when_safe_pinned_entry_or_lifetime():
    now = timezone.now()
    safe = _user()
    _order(safe, "3500000", status="delivered", placed_at=now - timedelta(days=30))
    assert services.tier_risk(safe.id, now=now) is None  # nothing leaves the window within 30 days

    entry = _user()
    _order(entry, "500000", status="delivered", placed_at=now - timedelta(days=360))
    assert services.tier_risk(entry.id, now=now) is None  # bronze can't drop

    pinned = _user()
    _order(pinned, "1500000", status="delivered", placed_at=now - timedelta(days=360))
    services.set_tier(pinned.id, LoyaltyTier.objects.get(slug="silver"), "VIP guest", actor="test")
    assert services.tier_risk(pinned.id, now=now) is None

    LoyaltySettings.objects.filter(pk=1).update(tier_window_days=0)
    risky = _user()
    _order(risky, "1500000", status="delivered", placed_at=now - timedelta(days=360))
    assert services.tier_risk(risky.id, now=now) is None


def test_tier_risk_reminder_task_warns_once(sent):
    from apps.loyalty.infrastructure.tasks import tier_risk_reminders

    u = _user()
    _order(u, "1200000", status="delivered", placed_at=timezone.now() - timedelta(days=360))
    sent.clear()
    assert tier_risk_reminders()["warned"] == 1
    kind, uid, payload = sent[-1]
    assert kind == "tier_risk" and uid == u.id and payload["tier_slug"] == "silver" and payload["needed"] == 1_000_000


def test_me_and_rate_expose_tier_risk_and_cashback(client):
    u = _user()
    _order(u, "1200000", status="delivered", placed_at=timezone.now() - timedelta(days=360))
    api = _auth(client, u)
    risk = api.get("/api/v1/loyalty/me").json()["data"]["tier_risk"]
    assert risk["tier"]["slug"] == "silver" and risk["falls_to"]["slug"] == "bronze" and risk["needed"] == "1000000" and risk["days_left"] == 5
    rate = api.get("/api/v1/loyalty/me/rate").json()["data"]
    assert rate["current_tier"]["percent"] == "2" and rate["next_tier"]["slug"] == "gold" and rate["amount_to_next"] == "1800000"
