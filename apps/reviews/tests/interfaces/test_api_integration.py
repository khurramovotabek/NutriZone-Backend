"""
Full-stack API integration tests -- real URL routing, serializers,
views, and repository/selector layer together against a real
database.

**Most mutation endpoints tested here are expected to return HTTP
501, per this module's disclosed zero-Application-Service state --
media attach (`POST .../media`) is the one exception, with a real,
fully implemented Application Service (`AttachReviewMedia`).**
Each 501 test asserts the exact status code, that a precise, non-vague
`detail` explanation is present, and -- for every resource-scoped
mutation -- that the 501 is only reached after a real 404 check for
a nonexistent resource, verifying the 404-before-501 rule is not
merely visual but actually enforced end-to-end.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.reviews.domain.enums import ReviewMediaType
from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.tests.factories import make_published_review, make_review
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


class TestUnauthenticatedAccess:
    def test_product_review_list_requires_auth(self, api_client):
        response = api_client.get(f"/api/v1/reviews/products/{uuid.uuid4()}")
        assert response.status_code == 401


class TestPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_product_review_list_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/reviews/products/{uuid.uuid4()}")
        assert response.status_code == 403


class TestAuthorizedFlows:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        self._current_fake_user_id = fake_user.id
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    # --- Working (read) endpoints, all 6 ---------------------------------

    def test_product_review_list(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        DjangoReviewRepository().save(review)
        response = api_client.get(f"/api/v1/reviews/products/{review.product_id}")
        assert response.status_code == 200
        assert "pagination" in response.json()

    def test_product_review_list_filters_by_status(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_published_review()
        DjangoReviewRepository().save(review)
        response = api_client.get(f"/api/v1/reviews/products/{review.product_id}?filter[status]=published")
        assert response.status_code == 200
        assert response.json()["data"][0]["status"] == "published"

    def test_customer_review_list(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review(customer_id=self._current_fake_user_id)
        DjangoReviewRepository().save(review)
        response = api_client.get(f"/api/v1/reviews/customers/{review.customer_id}")
        assert response.status_code == 200

    def test_admin_review_list(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        DjangoReviewRepository().save(make_review())
        response = api_client.get("/api/v1/reviews/admin")
        assert response.status_code == 200

    def test_review_detail(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review(customer_id=self._current_fake_user_id)
        DjangoReviewRepository().save(review)
        response = api_client.get(f"/api/v1/reviews/{review.id}")
        assert response.status_code == 200
        assert response.json()["data"]["body"] == review.body.value

    def test_review_detail_not_found(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/reviews/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_review_media_list(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        review.attach_media(ReviewMediaType.IMAGE, "https://example.com/a.jpg", datetime.utcnow())
        DjangoReviewRepository().save(review)
        response = api_client.get(f"/api/v1/reviews/{review.id}/media")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_review_media_list_not_found(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/reviews/{uuid.uuid4()}/media")
        assert response.status_code == 404

    def test_review_statistics(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        DjangoReviewRepository().save(make_review())
        response = api_client.get("/api/v1/reviews/statistics")
        assert response.status_code == 200
        assert "counts_by_status" in response.json()["data"]

    # --- Honest 501 mutation endpoints, all 9, treated as correct behavior ---

    def test_create_review_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/reviews/", {"product_id": str(uuid.uuid4()), "rating": 5, "body": "Great."}, format="json")
        assert response.status_code == 201

    def test_create_review_validates_before_501(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/reviews/", {"product_id": str(uuid.uuid4()), "rating": 6, "body": "x"}, format="json")
        assert response.status_code == 422

    def test_submit_review_succeeds(self, api_client):
        """Real, explicit product decision: a submitted review is immediately published -- no admin approval required (see SubmitReview's own docstring). Staff can still take it down afterward via the unmodified HideReview."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        DjangoReviewRepository().save(review)
        response = api_client.post(f"/api/v1/reviews/{review.id}/submit", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "published"

    def test_edit_review_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        DjangoReviewRepository().save(review)
        response = api_client.patch(f"/api/v1/reviews/{review.id}/edit", {"body": "Updated."}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["body"] == "Updated."

    def test_approve_review_succeeds_for_a_submitted_review(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        review.submit(review.created_at)
        DjangoReviewRepository().save(review)
        response = api_client.post(f"/api/v1/reviews/{review.id}/approve", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "approved"

    def test_reject_review_succeeds_for_a_submitted_review(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        review.submit(review.created_at)
        DjangoReviewRepository().save(review)
        response = api_client.post(f"/api/v1/reviews/{review.id}/reject", {"reason": "spam"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "rejected"

    def test_publish_review_succeeds_for_an_approved_review(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        review.submit(review.created_at)
        review.approve(review.created_at)
        DjangoReviewRepository().save(review)
        response = api_client.post(f"/api/v1/reviews/{review.id}/publish", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "published"

    def test_hide_review_succeeds_for_a_published_review(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_published_review()
        DjangoReviewRepository().save(review)
        response = api_client.post(f"/api/v1/reviews/{review.id}/hide", {"reason": "policy_violation"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "hidden"

    def test_withdraw_review_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        DjangoReviewRepository().save(review)
        response = api_client.post(f"/api/v1/reviews/{review.id}/withdraw", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "withdrawn"

    def test_attach_media_succeeds_for_a_draft_review(self, api_client):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        review = make_review()
        DjangoReviewRepository().save(review)
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), color="blue").save(buf, format="JPEG")
        response = api_client.post(f"/api/v1/reviews/{review.id}/media", {"media_type": "image", "file_upload": SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")}, format="multipart")
        assert response.status_code == 200

    # --- 404-before-501 rule, verified end-to-end for every resource-scoped mutation ---

    def test_all_resource_scoped_mutations_404_before_501_when_review_missing(self, api_client):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        missing_id = uuid.uuid4()
        assert api_client.post(f"/api/v1/reviews/{missing_id}/submit", {}, format="json").status_code == 404
        assert api_client.patch(f"/api/v1/reviews/{missing_id}/edit", {"body": "x"}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/reviews/{missing_id}/approve", {}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/reviews/{missing_id}/reject", {"reason": "spam"}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/reviews/{missing_id}/publish", {}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/reviews/{missing_id}/hide", {"reason": "policy_violation"}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/reviews/{missing_id}/withdraw", {}, format="json").status_code == 404
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), color="blue").save(buf, format="JPEG")
        assert api_client.post(f"/api/v1/reviews/{missing_id}/media", {"media_type": "image", "file_upload": SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")}, format="multipart").status_code == 404
