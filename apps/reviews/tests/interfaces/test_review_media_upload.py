"""
Real, live-verified regression test for review media file upload --
ReviewMediaModel.url previously required an external URL (URLField)
with no real file upload mechanism at all; AttachReviewMedia now runs
a real file through core.media.MediaPipeline, matching the direct-
file-storage convention established for Brand/Category/Banner/
BlogPost/Product. Images and videos have separate limits (4/3) per
explicit product decision.
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.infrastructure import models as r_models
from apps.reviews.tests.factories import make_review
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


@pytest.fixture
def authorized_client(monkeypatch) -> APIClient:
    original = HasPermissionCode.resolver
    HasPermissionCode.resolver = _AllowAllResolver()
    fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    yield client
    HasPermissionCode.resolver = original


def _real_image_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color="green").save(buf, format="JPEG")
    return buf.getvalue()


class TestReviewImageUploadLimit:
    def test_up_to_4_images_can_be_attached(self, authorized_client):
        review = make_review()
        DjangoReviewRepository().save(review)

        for i in range(4):
            response = authorized_client.post(
                f"/api/v1/reviews/{review.id}/media",
                {"media_type": "image", "file_upload": SimpleUploadedFile(f"img{i}.jpg", _real_image_bytes(), content_type="image/jpeg")},
                format="multipart",
            )
            assert response.status_code == 200, response.content

        assert r_models.ReviewMediaModel.objects.filter(review_id=review.id, media_type="image").count() == 4

    def test_5th_image_is_rejected_with_422(self, authorized_client):
        review = make_review()
        DjangoReviewRepository().save(review)

        for i in range(4):
            authorized_client.post(
                f"/api/v1/reviews/{review.id}/media",
                {"media_type": "image", "file_upload": SimpleUploadedFile(f"img{i}.jpg", _real_image_bytes(), content_type="image/jpeg")},
                format="multipart",
            )

        response = authorized_client.post(
            f"/api/v1/reviews/{review.id}/media",
            {"media_type": "image", "file_upload": SimpleUploadedFile("img5.jpg", _real_image_bytes(), content_type="image/jpeg")},
            format="multipart",
        )
        assert response.status_code == 422

    def test_attached_media_has_a_real_internal_storage_path_not_a_url(self, authorized_client):
        review = make_review()
        DjangoReviewRepository().save(review)

        authorized_client.post(
            f"/api/v1/reviews/{review.id}/media",
            {"media_type": "image", "file_upload": SimpleUploadedFile("real.jpg", _real_image_bytes(), content_type="image/jpeg")},
            format="multipart",
        )

        media = r_models.ReviewMediaModel.objects.filter(review_id=review.id).first()
        assert media is not None
        assert not media.url.startswith("http")
        assert media.url  # a real, non-empty storage path

    def test_public_media_list_returns_a_full_usable_url(self, authorized_client):
        review = make_review()
        DjangoReviewRepository().save(review)
        authorized_client.post(
            f"/api/v1/reviews/{review.id}/media",
            {"media_type": "image", "file_upload": SimpleUploadedFile("real.jpg", _real_image_bytes(), content_type="image/jpeg")},
            format="multipart",
        )

        response = authorized_client.get(f"/api/v1/reviews/{review.id}/media")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["url"].startswith("/media/")


class TestReviewVideoUploadLimit:
    def test_up_to_3_videos_can_be_attached_but_a_4th_is_rejected(self, authorized_client):
        review = make_review()
        DjangoReviewRepository().save(review)
        fake_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100

        for i in range(3):
            response = authorized_client.post(
                f"/api/v1/reviews/{review.id}/media",
                {"media_type": "video", "file_upload": SimpleUploadedFile(f"clip{i}.mp4", fake_video, content_type="video/mp4")},
                format="multipart",
            )
            assert response.status_code == 200, response.content

        response = authorized_client.post(
            f"/api/v1/reviews/{review.id}/media",
            {"media_type": "video", "file_upload": SimpleUploadedFile("clip4.mp4", fake_video, content_type="video/mp4")},
            format="multipart",
        )
        assert response.status_code == 422

    def test_image_limit_and_video_limit_are_independent(self, authorized_client):
        """4 images + 3 videos on the same review should both succeed -- separate limits, not one shared cap."""
        review = make_review()
        DjangoReviewRepository().save(review)
        fake_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100

        for i in range(4):
            r = authorized_client.post(f"/api/v1/reviews/{review.id}/media", {"media_type": "image", "file_upload": SimpleUploadedFile(f"i{i}.jpg", _real_image_bytes(), content_type="image/jpeg")}, format="multipart")
            assert r.status_code == 200
        for i in range(3):
            r = authorized_client.post(f"/api/v1/reviews/{review.id}/media", {"media_type": "video", "file_upload": SimpleUploadedFile(f"v{i}.mp4", fake_video, content_type="video/mp4")}, format="multipart")
            assert r.status_code == 200

        assert r_models.ReviewMediaModel.objects.filter(review_id=review.id).count() == 7
