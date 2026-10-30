"""Review requests: "how was it?" a few days after a customer received their goods."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ordering.infrastructure import replenishment as rp
from apps.ordering.infrastructure import review_requests as rr
from apps.products.infrastructure.models import Product, ProductTranslation

pytestmark = pytest.mark.django_db
NOW = timezone.now()


def _buy(customer, product, days_ago, ref):
    return rp.Purchase(customer, product, None, 1, NOW - timedelta(days=days_ago), ref)


def _product(status="published"):
    return Product.objects.create(id=uuid.uuid4(), status=status)


def test_asks_inside_the_window_once_per_purchase_skipping_reviewed_and_hidden(monkeypatch):
    from apps.reviews.infrastructure.models import ReviewModel

    customer = uuid.uuid4()
    whey, creatine, reviewed, early, late = (_product() for _ in range(5))
    draft = _product("draft")
    ReviewModel.objects.create(id=uuid.uuid4(), product_id=reviewed.id, customer_id=customer, rating=5, body="Zo'r")
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [
        _buy(customer, whey.id, 7, "order:a"), _buy(customer, creatine.id, 7, "order:a"), _buy(customer, reviewed.id, 7, "order:a"),
        _buy(customer, draft.id, 7, "order:a"),
        _buy(customer, early.id, 2, "order:b"),  # too soon to judge
        _buy(customer, late.id, 30, "order:c"),  # long forgotten
    ])

    asks = rr.due(NOW)
    assert [(a.ref, a.product_ids) for a in asks] == [("order:a", [whey.id, creatine.id])]


def test_daily_task_sends_one_message_per_purchase_in_each_language(monkeypatch, django_capture_on_commit_callbacks):
    from apps.identity.infrastructure.models import User
    from apps.notifications.infrastructure.models import NotificationModel
    from apps.ordering.infrastructure.tasks import review_requests

    user = User.objects.create(id=uuid.uuid4(), phone_number=f"+99893{uuid.uuid4().int % 10**7:07d}", status="active", full_name="Rev Test")
    whey, creatine = _product(), _product()
    for loc, name in (("uz", "Oltin Whey"), ("ru", "Золотой Whey"), ("en", "Gold Whey")):
        ProductTranslation.objects.create(id=uuid.uuid4(), product=whey, locale_code=loc, name=name, slug=f"gold-{loc}-{uuid.uuid4().hex[:4]}")
    monkeypatch.setattr(rr, "due", lambda now=None: [rr.ReviewAsk(user.id, "order:x1", [whey.id, creatine.id])])

    with django_capture_on_commit_callbacks(execute=True):
        review_requests()
    with django_capture_on_commit_callbacks(execute=True):
        review_requests()  # the same purchase again -> no second message

    rows = NotificationModel.objects.filter(recipient_id=user.id, kind="review_request")
    assert rows.count() == 1
    i18n = rows.get().i18n
    assert "Oltin Whey" in i18n["uz"]["title"] and "Золотой Whey" in i18n["ru"]["title"] and "Gold Whey" in i18n["en"]["title"]
    assert "va yana 1 ta mahsulot" in i18n["uz"]["body"] and "and 1 more" in i18n["en"]["body"]
    assert rows.get().link.startswith("/products/gold-uz-") and rows.get().link.endswith("#reviews")


def test_the_task_is_on_the_beat_schedule():
    from django_celery_beat.models import PeriodicTask

    assert PeriodicTask.objects.filter(task="ordering.review_requests", enabled=True).exists()
