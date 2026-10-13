"""
Dashboard → Sharhlar: the moderation desk. Approve publishes in one step (also an "approved" review that was never
re-published after an edit), reject / hide carry a reason, everything goes through the services; reviews are never
added or deleted by hand; the media page is a gallery.
"""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from apps.reviews.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def _review(status="pending_moderation", rating=5, body="Juda sifatli mahsulot, tavsiya qilaman", **kw):
    return orm.ReviewModel.objects.create(product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=rating, body=body, status=status,
                                          submitted_at=timezone.now(), **kw)


class TestPages:
    @pytest.mark.parametrize("url", ["/django-admin/reviews/reviewmodel/", "/django-admin/reviews/reviewmediamodel/",
                                     "/django-admin/reviews/reviewmodel/?status__exact=pending_moderation", "/django-admin/reviews/reviewmodel/?stars=low&media=1"])
    def test_pages_render(self, admin_client, url):
        r = _review()
        orm.ReviewMediaModel.objects.create(review=r, media_type="image", url="reviews/a.webp", uploaded_at=timezone.now())
        assert admin_client.get(url).status_code == 200

    def test_card_shows_text_and_moderation(self, admin_client):
        r = _review(title="Zo'r kreatin")
        html = admin_client.get(f"/django-admin/reviews/reviewmodel/{r.pk}/change/").content.decode()
        assert "Juda sifatli mahsulot" in html and "Tasdiqlash va saytga chiqarish" in html and "Rad etish" in html

    def test_no_manual_add_or_delete(self, admin_client):
        r = _review()
        assert admin_client.get("/django-admin/reviews/reviewmodel/add/").status_code == 403
        assert admin_client.get(f"/django-admin/reviews/reviewmodel/{r.pk}/delete/").status_code == 403


class TestModeration:
    def test_approve_publishes_a_pending_review(self, admin_client):
        r = _review()
        admin_client.post(f"/django-admin/reviews/reviewmodel/{r.pk}/nz/approve/")
        r.refresh_from_db()
        assert r.status == "published" and r.published_at is not None

    def test_approve_republishes_an_approved_review(self, admin_client):
        r = _review(status="approved")
        admin_client.post("/django-admin/reviews/reviewmodel/", {"action": "approve_selected", "_selected_action": [r.pk], "index": 0})
        r.refresh_from_db()
        assert r.status == "published"

    def test_reject_with_reason_and_hide(self, admin_client):
        pending, live = _review(), _review(status="published")
        admin_client.post(f"/django-admin/reviews/reviewmodel/{pending.pk}/nz/reject/", {"nz_reason_reject": "spam"})
        admin_client.post(f"/django-admin/reviews/reviewmodel/{live.pk}/nz/hide/", {"nz_reason_hide": "customer_complaint"})
        pending.refresh_from_db(), live.refresh_from_db()
        assert (pending.status, live.status) == ("rejected", "hidden")

    def test_an_impossible_transition_is_reported_not_crashing(self, admin_client):
        draft = _review(status="draft")
        r = admin_client.post(f"/django-admin/reviews/reviewmodel/{draft.pk}/nz/reject/", {"nz_reason_reject": "spam"}, follow=True)
        assert r.status_code == 200 and "Bajarib bo" in r.content.decode()
        draft.refresh_from_db()
        assert draft.status == "draft"

    def test_moderation_needs_post(self, admin_client):
        r = _review()
        assert admin_client.get(f"/django-admin/reviews/reviewmodel/{r.pk}/nz/approve/").status_code == 403
