"""
Real, live-verified regression test for Phase 3: real file upload
widgets replacing raw UUID/FK selection for Category.image,
Brand.logo, Product media (up to 8 images/videos), and User avatar.
Every scenario here was proven live via a real, real-sized (400x400,
matching the domain's own 200x200px minimum) test image through the
actual Django admin change_form before being formalized.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from apps.identity.infrastructure import models as identity_orm
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _real_test_image_bytes(size=(400, 400)) -> bytes:
    """A genuinely valid JPEG, large enough to pass the domain's own real 200x200px minimum (confirmed live via ValidationFailed before this fixture used a large-enough size)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color="green").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def staff_client():
    user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestUserAvatarUpload:
    def test_real_avatar_upload_creates_real_avatar_asset(self, staff_client):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        customer = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active")
        response = staff_client.post(f"/django-admin/identity/user/{customer.id}/change/", data={
            "phone_number": customer.phone_number, "status": "active", "language": "uz",
            "avatar_upload": SimpleUploadedFile("avatar.jpg", _real_test_image_bytes(), content_type="image/jpeg"),
        }, follow=True)
        assert response.status_code == 200
        customer.refresh_from_db()
        assert customer.profile_picture_media_id is not None
        avatar = identity_orm.UserAvatarAsset.objects.filter(user=customer).first()
        assert avatar is not None
        assert "small" in avatar.thumbnail_paths


class TestBrandLogoUpload:
    def test_real_logo_upload_attaches_real_media_asset(self, staff_client):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        brand = p_models.Brand.objects.create(id=uuid.uuid4())
        response = staff_client.post(f"/django-admin/products/brand/{brand.id}/change/", data={
            "is_manufacturer": "", "is_active": "on",
            "logo_upload": SimpleUploadedFile("logo.jpg", _real_test_image_bytes(), content_type="image/jpeg"),
            "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
        }, follow=True)
        assert response.status_code == 200
        brand.refresh_from_db()
        assert brand.logo_storage_path
        assert "small" in brand.logo_thumbnail_paths


class TestCategoryImageUpload:
    def test_real_image_upload_attaches_real_media_asset(self, staff_client):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        category = p_models.Category.objects.create(id=uuid.uuid4())
        response = staff_client.post(f"/django-admin/products/category/{category.id}/change/", data={
            "sort_order": "0", "is_active": "on",
            "image_upload": SimpleUploadedFile("cat.jpg", _real_test_image_bytes(), content_type="image/jpeg"),
            "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
        }, follow=True)
        assert response.status_code == 200
        category.refresh_from_db()
        assert category.image_storage_path
        assert "small" in category.image_thumbnail_paths


class TestProductMediaUpload:
    def test_real_image_upload_creates_real_product_media(self, staff_client):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        data = {
            "status": "draft",
            "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
            "variants-TOTAL_FORMS": "0", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
            # `ProductPricingInline` (a second inline over ProductVariant) is
            # auto-disambiguated to prefix "variants-2" by Django -- its empty
            # management form is still required on every add/change POST.
            "variants-2-TOTAL_FORMS": "0", "variants-2-INITIAL_FORMS": "0", "variants-2-MIN_NUM_FORMS": "0", "variants-2-MAX_NUM_FORMS": "1000",
            "flavour_links-TOTAL_FORMS": "0", "flavour_links-INITIAL_FORMS": "0", "flavour_links-MIN_NUM_FORMS": "0", "flavour_links-MAX_NUM_FORMS": "1000",
            "media-TOTAL_FORMS": "1", "media-INITIAL_FORMS": "0", "media-MIN_NUM_FORMS": "0", "media-MAX_NUM_FORMS": "8",
            "media-0-media_role": "primary", "media-0-sort_order": "0",
            "media-0-file_upload": SimpleUploadedFile("product.jpg", _real_test_image_bytes(), content_type="image/jpeg"),
        }
        response = staff_client.post(f"/django-admin/products/product/{product.id}/change/", data=data, follow=True)
        assert response.status_code == 200
        media = p_models.ProductMedia.objects.filter(product=product).first()
        assert media is not None
        assert media.media_role == "primary"
        assert "small" in media.thumbnail_paths

    def test_real_video_upload_creates_real_product_media_with_duration(self, staff_client):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()  # Same real Django test-infrastructure gap found and fixed in Phase C's transaction-boundary audit.

        product = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        fake_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
        data = {
            "status": "draft",
            "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
            "variants-TOTAL_FORMS": "0", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
            "variants-2-TOTAL_FORMS": "0", "variants-2-INITIAL_FORMS": "0", "variants-2-MIN_NUM_FORMS": "0", "variants-2-MAX_NUM_FORMS": "1000",
            "flavour_links-TOTAL_FORMS": "0", "flavour_links-INITIAL_FORMS": "0", "flavour_links-MIN_NUM_FORMS": "0", "flavour_links-MAX_NUM_FORMS": "1000",
            "media-TOTAL_FORMS": "1", "media-INITIAL_FORMS": "0", "media-MIN_NUM_FORMS": "0", "media-MAX_NUM_FORMS": "8",
            "media-0-media_role": "video", "media-0-sort_order": "0", "media-0-duration_seconds": "30",
            "media-0-file_upload": SimpleUploadedFile("clip.mp4", fake_video, content_type="video/mp4"),
        }
        response = staff_client.post(f"/django-admin/products/product/{product.id}/change/", data=data, follow=True)
        assert response.status_code == 200
        media = p_models.ProductMedia.objects.filter(product=product, media_role="video").first()
        assert media is not None
        assert media.duration_seconds == 30.0
