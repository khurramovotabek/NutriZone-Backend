"""
Real, live-verified regression test: internal implementation-detail
fields (*_storage_path, *_thumbnail_paths) must never appear as raw
editable fields in an admin add/change form -- they are populated
directly by save_model() from the real file upload, never meant to
be hand-edited by a staff user. Real file upload must still work
after removing them from the form's own `fields` list.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from apps.products.infrastructure.models import Brand

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    AuthUser = get_user_model()
    user = AuthUser.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


def _real_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


class TestStoragePathFieldsHiddenFromAdminForms:
    def test_brand_add_form_does_not_expose_storage_path_fields(self, staff_client):
        response = staff_client.get("/django-admin/products/brand/add/")
        content = response.content.decode()
        assert "logo_storage_path" not in content
        assert "logo_thumbnail_paths" not in content
        assert "logo_upload" in content

    def test_category_add_form_does_not_expose_storage_path_fields(self, staff_client):
        response = staff_client.get("/django-admin/products/category/add/")
        content = response.content.decode()
        assert "image_storage_path" not in content
        assert "image_thumbnail_paths" not in content
        assert "image_upload" in content

    def test_banner_add_form_does_not_expose_storage_path_fields(self, staff_client):
        response = staff_client.get("/django-admin/platform/banner/add/")
        content = response.content.decode()
        assert "image_storage_path" not in content
        assert "image_thumbnail_paths" not in content
        assert "image_upload" in content

    def test_blog_post_add_form_does_not_expose_storage_path_fields(self, staff_client):
        response = staff_client.get("/django-admin/content/blogpost/add/")
        content = response.content.decode()
        assert "cover_image_storage_path" not in content
        assert "cover_image_thumbnail_paths" not in content
        assert "cover_image_upload" in content

    def test_real_upload_still_works_after_removing_the_raw_field(self, staff_client):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        response = staff_client.post("/django-admin/products/brand/add/", data={
            "is_manufacturer": "", "is_active": "on",
            "logo_upload": SimpleUploadedFile("logo.jpg", _real_jpeg_bytes(), content_type="image/jpeg"),
            "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
        }, follow=True)
        assert response.status_code == 200
        brand = Brand.objects.exclude(logo_storage_path="").order_by("-created_at").first()
        assert brand is not None
        assert brand.logo_storage_path
        assert "small" in brand.logo_thumbnail_paths
