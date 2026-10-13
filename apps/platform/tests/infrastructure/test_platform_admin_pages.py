"""
Premium Platform admin pages: the banner gallery (toggle / drag-reorder endpoints, bulk show/hide)
and the contact-message inbox (status tabs, auto-read on open, bulk triage).
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.test import Client

from apps.platform.infrastructure.models import Banner, ContactMessage, ContactMessageStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def banners():
    return [
        Banner.objects.create(title="First", sort_order=1, is_active=True),
        Banner.objects.create(title="Second", sort_order=2, is_active=True),
        Banner.objects.create(title="Third", sort_order=3, is_active=False),
    ]


class TestBannerGallery:
    def test_changelist_renders_gallery_with_stats(self, admin_client, banners):
        response = admin_client.get("/django-admin/platform/banner/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "data-nzp-banners" in body
        assert body.count('<article class="nzp-banner') == 3
        assert response.context["nz_banner_stats"] == {"total": 3, "active": 2, "no_image": 3, "cycle": 90, "hidden": 1}

    def test_drag_reorder_is_disabled_while_filtering(self, admin_client, banners):
        body = admin_client.get("/django-admin/platform/banner/?is_active__exact=1").content.decode()
        assert "data-sortable" not in body

    def test_toggle_flips_visibility_and_logs_it(self, admin_client, banners):
        third = banners[2]
        response = admin_client.post(f"/django-admin/platform/banner/{third.pk}/toggle/")
        assert response.status_code == 200
        assert response.json() == {"ok": True, "is_active": True, "active_count": 3}
        third.refresh_from_db()
        assert third.is_active is True
        assert LogEntry.objects.filter(object_id=str(third.pk)).exists()

    def test_toggle_requires_post(self, admin_client, banners):
        assert admin_client.get(f"/django-admin/platform/banner/{banners[0].pk}/toggle/").status_code == 405

    def test_reorder_rewrites_sort_order_in_steps_of_ten(self, admin_client, banners):
        ids = [str(banners[2].pk), str(banners[0].pk), str(banners[1].pk)]
        response = admin_client.post("/django-admin/platform/banner/reorder/", data=json.dumps({"ids": ids}), content_type="application/json")
        assert response.status_code == 200
        assert [b.title for b in Banner.objects.order_by("sort_order")] == ["Third", "First", "Second"]
        assert sorted(Banner.objects.values_list("sort_order", flat=True)) == [10, 20, 30]

    def test_reorder_rejects_a_malformed_body(self, admin_client, banners):
        response = admin_client.post("/django-admin/platform/banner/reorder/", data="not json", content_type="application/json")
        assert response.status_code == 400

    def test_bulk_hide_action(self, admin_client, banners):
        response = admin_client.post("/django-admin/platform/banner/", {
            "action": "deactivate_selected", "index": "0", "select_across": "0",
            "_selected_action": [str(banners[0].pk), str(banners[1].pk)],
        })
        assert response.status_code == 302
        assert Banner.objects.filter(is_active=True).count() == 0

    def test_editor_renders_live_preview(self, admin_client, banners):
        response = admin_client.get(f"/django-admin/platform/banner/{banners[0].pk}/change/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "data-nzp-banner-editor" in body
        assert 'data-nzp-prev-title>First<' in body

    def test_editor_save_keeps_working(self, admin_client, banners):
        response = admin_client.post(f"/django-admin/platform/banner/{banners[0].pk}/change/", {
            "title": "Renamed", "subtitle": "", "cta_text": "", "cta_url": "", "duration_seconds": "9", "sort_order": "5", "is_active": "on", "_save": "1",
        })
        assert response.status_code == 302
        banners[0].refresh_from_db()
        assert (banners[0].title, banners[0].duration_seconds, banners[0].sort_order) == ("Renamed", 9, 5)


class TestContactInbox:
    @pytest.fixture
    def messages(self):
        return [
            ContactMessage.objects.create(name="Ali Valiyev", email="ali@example.com", subject="Delivery", message="Where is my order?"),
            ContactMessage.objects.create(name="Ali Valiyev", email="ali@example.com", subject="Earlier", message="Old question", status=ContactMessageStatus.REPLIED),
        ]

    def test_inbox_renders_tabs_with_counts(self, admin_client, messages):
        response = admin_client.get("/django-admin/platform/contactmessage/")
        assert response.status_code == 200
        tabs = {t["key"]: t["n"] for t in response.context["nz_inbox_tabs"]}
        assert tabs == {"": 2, "new": 1, "read": 0, "replied": 1}
        assert ">AV<" in response.content.decode()  # initials avatar

    def test_opening_a_new_message_marks_it_read(self, admin_client, messages):
        new = messages[0]
        response = admin_client.get(f"/django-admin/platform/contactmessage/{new.pk}/change/")
        assert response.status_code == 200
        assert response.context["nz_auto_read"] is True
        new.refresh_from_db()
        assert new.status == ContactMessageStatus.READ
        # the reader lists the sender's other message and offers a mailto reply
        assert [h["subject"] for h in response.context["nz_history"]] == ["Earlier"]
        assert response.context["nz_reply_href"].startswith("mailto:ali@example.com?subject=Re%3A%20Delivery")

    def test_status_can_be_saved_from_the_reader(self, admin_client, messages):
        msg = messages[0]
        response = admin_client.post(f"/django-admin/platform/contactmessage/{msg.pk}/change/", {"status": "replied", "_save": "1"})
        assert response.status_code == 302
        msg.refresh_from_db()
        assert msg.status == ContactMessageStatus.REPLIED

    def test_bulk_mark_as_new(self, admin_client, messages):
        response = admin_client.post("/django-admin/platform/contactmessage/", {
            "action": "mark_new", "index": "0", "select_across": "0", "_selected_action": [str(m.pk) for m in messages],
        })
        assert response.status_code == 302
        assert ContactMessage.objects.filter(status=ContactMessageStatus.NEW).count() == 2

    def test_inbox_is_translated(self, admin_client, messages):
        admin_client.post("/i18n/setlang/", {"language": "uz", "next": "/django-admin/"})
        body = admin_client.get("/django-admin/platform/contactmessage/").content.decode()
        assert "Ism, email yoki matn bo'yicha qidirish…" in body
        assert "Javob berilgan" in body  # status pill label
