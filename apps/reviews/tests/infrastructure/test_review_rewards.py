"""Coins for a review: one review per delivered online order earns the reward, any rating (rewards.py)."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ordering.infrastructure import replenishment as rp
from apps.reviews.infrastructure import rewards

pytestmark = pytest.mark.django_db
NOW = timezone.now()
BODY = "Ta'mi juda yoqdi, yaxshi eriydi va qorin dam bo'lmadi."


def _user(guest=False):
    from apps.identity.infrastructure.models import User

    return User.objects.create(id=uuid.uuid4(), phone_number=f"+99893{uuid.uuid4().int % 10**7:07d}", status="active", full_name="Rew Test", is_guest=guest)


def _review(customer, product, rating=5, body=BODY, status="published"):
    from apps.reviews.infrastructure.models import ReviewModel

    return ReviewModel.objects.create(id=uuid.uuid4(), product_id=product, customer_id=customer, rating=rating, body=body, status=status)


def _orders(monkeypatch, customer, *lines):
    """lines: (product, ref, days_ago)"""
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [
        rp.Purchase(customer, product, None, 1, NOW - timedelta(days=days), ref) for product, ref, days in lines])


def _balance(user_id):
    from apps.loyalty.infrastructure.models import Wallet

    w = Wallet.objects.filter(user_id=user_id).first()
    return w.balance if w else 0


def test_one_review_per_order_any_rating(monkeypatch, django_capture_on_commit_callbacks):
    from apps.notifications.infrastructure.models import NotificationModel

    user, whey, creatine, bcaa = _user(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _orders(monkeypatch, user.id, (whey, "order:a", 5), (creatine, "order:a", 5), (bcaa, "order:b", 2))
    with django_capture_on_commit_callbacks(execute=True):
        row = rewards.award(_review(user.id, whey, rating=1).id)  # an honest 1★ counts too
    assert row and row.coins == 1000 and row.received_ref == "order:a"
    assert rewards.award(_review(user.id, creatine).id) is None  # order a already paid its one review
    assert rewards.award(_review(user.id, bcaa, rating=3).id).received_ref == "order:b"  # the next order pays again
    assert _balance(user.id) == 2000
    assert "+1 000 coin" in NotificationModel.objects.filter(recipient_id=user.id, kind="review_reward").first().i18n["uz"]["title"]


def test_reordering_the_same_product_earns_again(monkeypatch):
    user, whey = _user(), uuid.uuid4()
    _orders(monkeypatch, user.id, (whey, "order:a", 40), (whey, "order:b", 3))
    first = rewards.award(_review(user.id, whey).id)
    second = rewards.award(_review(user.id, whey).id)
    assert (first.received_ref, second.received_ref) == ("order:a", "order:b")
    assert rewards.award(_review(user.id, whey).id) is None


@pytest.mark.parametrize("case", ["short", "before_delivery", "store_sale_only", "not_received", "guest", "draft", "off"])
def test_does_not_pay(monkeypatch, case):
    from apps.reviews.infrastructure.models import ReviewRequestSettings

    user, product = _user(guest=case == "guest"), uuid.uuid4()
    if case == "not_received":
        _orders(monkeypatch, user.id)
    elif case == "store_sale_only":
        _orders(monkeypatch, user.id, (product, "sale:x", 3))
    else:
        _orders(monkeypatch, user.id, (product, "order:x", -2 if case == "before_delivery" else 3))  # delivered 2 days AFTER the review
    if case == "off":
        cfg = ReviewRequestSettings.load()
        cfg.reward_enabled = False
        cfg.save()
    review = _review(user.id, product, body="Zo'r" if case == "short" else BODY, status="draft" if case == "draft" else "published")
    assert rewards.award(review.id) is None
    assert _balance(user.id) == 0


def test_offer_for_the_form(monkeypatch):
    user, product = _user(), uuid.uuid4()
    assert rewards.offer(None, product) == {"enabled": True, "coins": 1000, "min_rating": 1, "min_chars": 30, "state": "anonymous"}
    _orders(monkeypatch, user.id)
    assert rewards.offer(user.id, product)["state"] == "not_received"
    _orders(monkeypatch, user.id, (product, "order:x", 3))
    assert rewards.offer(user.id, product)["state"] == "eligible"
    rewards.award(_review(user.id, product).id)
    assert rewards.offer(user.id, product)["state"] == "rewarded"


def test_public_endpoint(client):
    r = client.get(f"/api/v1/reviews/reward?product_id={uuid.uuid4()}")
    assert r.status_code == 200 and r.json()["data"]["coins"] == 1000
