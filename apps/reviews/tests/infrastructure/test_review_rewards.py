"""Coins for a review written after the goods were received (rewards.py)."""
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


def _received(monkeypatch, customer, product, days_ago=3):
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [rp.Purchase(customer, product, None, 1, NOW - timedelta(days=days_ago), "order:x")])


def _balance(user_id):
    from apps.loyalty.infrastructure.models import Wallet

    w = Wallet.objects.filter(user_id=user_id).first()
    return w.balance if w else 0


def test_pays_once_per_product_for_a_good_review_after_delivery(monkeypatch, django_capture_on_commit_callbacks):
    from apps.notifications.infrastructure.models import NotificationModel

    user, product = _user(), uuid.uuid4()
    _received(monkeypatch, user.id, product)
    with django_capture_on_commit_callbacks(execute=True):
        row = rewards.award(_review(user.id, product).id)
    assert row and row.coins == 1000 and row.received_ref == "order:x"
    assert _balance(user.id) == 1000
    assert rewards.award(_review(user.id, product, rating=4).id) is None  # second review of the same product
    assert _balance(user.id) == 1000
    n = NotificationModel.objects.get(recipient_id=user.id, kind="review_reward")
    assert "+1 000 coin" in n.i18n["uz"]["title"]
    assert rewards.offer(user.id, product)["state"] == "rewarded"


@pytest.mark.parametrize("case", ["low_rating", "short", "before_delivery", "not_received", "guest", "draft", "off"])
def test_does_not_pay(monkeypatch, case):
    from apps.reviews.infrastructure.models import ReviewRequestSettings

    user, product = _user(guest=case == "guest"), uuid.uuid4()
    if case == "not_received":
        monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [])
    else:
        _received(monkeypatch, user.id, product, days_ago=-2 if case == "before_delivery" else 3)  # delivered 2 days AFTER the review
    if case == "off":
        cfg = ReviewRequestSettings.load()
        cfg.reward_enabled = False
        cfg.save()
    review = _review(user.id, product, rating=3 if case == "low_rating" else 5, body="Zo'r" if case == "short" else BODY,
                     status="draft" if case == "draft" else "published")
    assert rewards.award(review.id) is None
    assert _balance(user.id) == 0


def test_offer_for_the_form(monkeypatch):
    user, product = _user(), uuid.uuid4()
    assert rewards.offer(None, product) == {"enabled": True, "coins": 1000, "min_rating": 4, "min_chars": 30, "state": "anonymous"}
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [])
    assert rewards.offer(user.id, product)["state"] == "not_received"
    _received(monkeypatch, user.id, product)
    assert rewards.offer(user.id, product)["state"] == "eligible"


def test_public_endpoint(client):
    r = client.get(f"/api/v1/reviews/reward?product_id={uuid.uuid4()}")
    assert r.status_code == 200 and r.json()["data"]["coins"] == 1000
