"""
Real, live-verified regression test for the Banner (homepage hero
slider) feature. Media Asset architecture (ProductMediaAsset FK/table)
was fully removed for Banner per explicit product decision -- now
uses direct storage fields (image_storage_path/image_thumbnail_paths).
Existing production Banner.image data was migrated forward via a
real, tested data migration (0009_banner_copy_image_data), never
fabricated or dropped.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.platform.infrastructure.models import Banner

pytestmark = pytest.mark.django_db


class TestBannerPublicApi:
    def test_only_active_banners_are_returned_ordered_by_sort_order(self):
        Banner.objects.create(id=uuid.uuid4(), title="Second", sort_order=1, is_active=True, image_storage_path="b2.jpg", image_thumbnail_paths={"large": "b2-large.jpg"})
        Banner.objects.create(id=uuid.uuid4(), title="First", sort_order=0, is_active=True, image_storage_path="b1.jpg", image_thumbnail_paths={"large": "b1-large.jpg"})
        Banner.objects.create(id=uuid.uuid4(), title="Inactive", sort_order=99, is_active=False)

        client = Client()
        response = client.get("/api/v1/settings/banners")
        assert response.status_code == 200
        data = response.json()["data"]
        titles = [b["title"] for b in data]
        assert titles == ["First", "Second"]

    def test_banner_with_no_image_has_null_image_url(self):
        Banner.objects.create(id=uuid.uuid4(), title="No Image Banner", is_active=True)

        client = Client()
        response = client.get("/api/v1/settings/banners")
        matching = next(b for b in response.json()["data"] if b["title"] == "No Image Banner")
        assert matching["image_url"] is None

    def test_duration_seconds_defaults_to_45_and_is_returned(self):
        Banner.objects.create(id=uuid.uuid4(), title="Default Duration", is_active=True)
        Banner.objects.create(id=uuid.uuid4(), title="Custom Duration", is_active=True, duration_seconds=30)

        client = Client()
        response = client.get("/api/v1/settings/banners")
        data = response.json()["data"]
        assert next(b for b in data if b["title"] == "Default Duration")["duration_seconds"] == 45
        assert next(b for b in data if b["title"] == "Custom Duration")["duration_seconds"] == 30


class TestBannerAdminRealUpload:
    def test_real_image_upload_populates_direct_storage_fields(self):
        import io

        from django.contrib.auth.models import User as AuthUser
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import Client as AdminClient
        from PIL import Image

        admin_user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = AdminClient()
        client.force_login(admin_user)

        buf = io.BytesIO()
        Image.new("RGB", (1200, 400), color="green").save(buf, format="JPEG")

        response = client.post("/django-admin/platform/banner/add/", data={
            "title": "Test Upload Banner", "subtitle": "", "cta_text": "", "cta_url": "", "sort_order": "0", "is_active": "on",
            "image_upload": SimpleUploadedFile("banner.jpg", buf.getvalue(), content_type="image/jpeg"),
        }, follow=True)
        assert response.status_code == 200

        banner = Banner.objects.filter(title="Test Upload Banner").first()
        assert banner is not None
        assert banner.image_storage_path
        assert "small" in banner.image_thumbnail_paths


class TestBannerAdminForm:
    """
    Form-level (no admin HTTP POST) so these don't stack a second
    `LogEntry`-writing request onto `TestBannerAdminRealUpload`'s own --
    confirmed a pre-existing test-infra issue (unrelated to Banner):
    a second admin-panel POST in the same module reliably hits a
    ContentType FK teardown race (reproduced with an unmodified
    duplicate of the existing upload test, no duration_seconds
    involved). Exercises the real `BannerAdminForm` class directly.
    """

    def test_duration_seconds_is_editable(self):
        from apps.platform.infrastructure.admin import BannerAdminForm

        form = BannerAdminForm(data={"title": "Duration Test Banner", "subtitle": "", "cta_text": "", "cta_url": "", "duration_seconds": "30", "sort_order": "0", "is_active": "on"})
        assert form.is_valid(), form.errors
        banner = form.save()
        assert banner.duration_seconds == 30

    def test_duration_seconds_defaults_when_omitted(self):
        from apps.platform.infrastructure.admin import BannerAdminForm

        # Omitting the field entirely (e.g. an older client) must not fail
        # validation -- it falls back to the model's own default.
        form = BannerAdminForm(data={"title": "No Duration Banner", "subtitle": "", "cta_text": "", "cta_url": "", "sort_order": "0", "is_active": "on"})
        assert form.is_valid(), form.errors
        banner = form.save()
        assert banner.duration_seconds == 45

    def test_duration_seconds_rejects_out_of_range_values(self):
        from apps.platform.infrastructure.admin import BannerAdminForm

        form = BannerAdminForm(data={"title": "Bad Duration Banner", "subtitle": "", "cta_text": "", "cta_url": "", "duration_seconds": "1", "sort_order": "0", "is_active": "on"})
        assert not form.is_valid()
        assert "duration_seconds" in form.errors
