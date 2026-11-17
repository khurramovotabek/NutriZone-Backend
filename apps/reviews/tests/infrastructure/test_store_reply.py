"""
Sharh → "Do'kon javobi": the store answers a review from the dashboard; the answer is public under the review
(product page, home wall, the customer's own list), the customer is told once (first answer to a live review),
editing the review itself keeps the answer, and clearing it removes it from the site.
"""
from __future__ import annotations

import uuid
from unittest import mock

import pytest
from django.utils import timezone

from apps.reviews.infrastructure import models as orm
from apps.reviews.infrastructure.admin import REPLY_MAX, set_store_reply
from apps.reviews.infrastructure.selectors import ReviewSelector

pytestmark = pytest.mark.django_db


def _review(status="published", **kw):
    return orm.ReviewModel.objects.create(product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=5, body="Juda sifatli mahsulot", status=status,
                                          submitted_at=timezone.now(), published_at=timezone.now() if status == "published" else None, **kw)


@pytest.fixture
def notified():
    with mock.patch("apps.notifications.infrastructure.notify.notify") as m:
        yield m


class TestService:
    def test_first_answer_to_a_live_review_notifies_once(self, notified):
        r = _review()
        assert set_store_reply(r.pk, "  Rahmat!  \n", "Admin") == "added"
        r.refresh_from_db()
        assert (r.store_reply, r.store_reply_by) == ("Rahmat!", "Admin") and r.store_reply_at is not None
        assert notified.call_count == 1 and notified.call_args.args[1] == "review_reply"
        assert set_store_reply(r.pk, "Rahmat! Yana kutamiz.", "Admin") == "edited"
        assert set_store_reply(r.pk, "Rahmat! Yana kutamiz.", "Admin") == "same"
        assert notified.call_count == 1  # edits never re-notify

    def test_answer_before_publishing_is_kept_silently(self, notified):
        r = _review(status="pending_moderation")
        assert set_store_reply(r.pk, "Rahmat", "Admin") == "added"
        notified.assert_not_called()

    def test_clear_and_limit(self, notified):
        r = _review(store_reply="Eski javob", store_reply_at=timezone.now(), store_reply_by="Admin")
        assert set_store_reply(r.pk, "   ", "Admin") == "removed"
        r.refresh_from_db()
        assert (r.store_reply, r.store_reply_at, r.store_reply_by) == ("", None, "")
        with pytest.raises(ValueError):
            set_store_reply(r.pk, "x" * (REPLY_MAX + 1), "Admin")


class TestPublic:
    def test_public_list_carries_the_answer_without_its_author(self):
        r = _review(store_reply="Rahmat!", store_reply_at=timezone.now(), store_reply_by="Ichki xodim")
        cards, total = ReviewSelector().list_published_for_product(r.product_id, 1, 10)
        assert total == 1 and cards[0]["store_reply"]["body"] == "Rahmat!" and "Ichki xodim" not in str(cards[0])
        bare = _review()
        assert ReviewSelector().list_published_for_product(bare.product_id, 1, 10)[0][0]["store_reply"] is None

    def test_editing_the_review_keeps_the_answer(self):
        from apps.reviews.infrastructure.repositories import DjangoReviewRepository

        r = _review(store_reply="Rahmat!", store_reply_at=timezone.now())
        repo = DjangoReviewRepository()
        review = repo.get_by_id(r.pk)
        repo.save(review)
        r.refresh_from_db()
        assert r.store_reply == "Rahmat!"


class TestDashboard:
    def test_panel_and_post(self, admin_client, notified):
        r = _review()
        html = admin_client.get(f"/django-admin/reviews/reviewmodel/{r.pk}/change/").content.decode()
        assert "Do&#x27;kon javobi" in html or "Do'kon javobi" in html
        assert 'name="store_reply"' in html
        admin_client.post(f"/django-admin/reviews/reviewmodel/{r.pk}/nz/reply/", {"store_reply": "Rahmat!"})
        r.refresh_from_db()
        assert r.store_reply == "Rahmat!"
        assert "javob berilgan" in admin_client.get("/django-admin/reviews/reviewmodel/").content.decode()
        admin_client.post(f"/django-admin/reviews/reviewmodel/{r.pk}/nz/reply/?clear=1", {"store_reply": "Rahmat!"})
        r.refresh_from_db()
        assert r.store_reply == ""

    def test_get_is_refused(self, admin_client):
        r = _review()
        assert admin_client.get(f"/django-admin/reviews/reviewmodel/{r.pk}/nz/reply/").status_code == 403
