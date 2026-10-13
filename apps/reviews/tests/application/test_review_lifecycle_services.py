"""
Real, live-verified regression test for Reviews' first-ever
Application Service layer (CreateReview/SubmitReview/EditReview/
ApproveReview/RejectReview/PublishReview/HideReview/WithdrawReview/
AttachReviewMedia). Every scenario here was proven live -- via a raw
`manage.py shell` composition call AND a full, real HTTP request
through the actual REST endpoints (including a genuine RBAC gap found
and fixed via migration 0013) -- before being formalized.
"""
from __future__ import annotations

import io
import json
import uuid

import pytest
from django.test import Client
from django.utils import timezone
from PIL import Image

from apps.identity.infrastructure import models as identity_orm
from apps.identity.infrastructure.security import hash_otp_code
from apps.ordering.infrastructure import models as o_models
from apps.products.infrastructure import models as p_models
from apps.reviews.infrastructure import composition

pytestmark = pytest.mark.django_db


def _make_product() -> p_models.Product:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Test Product", slug=f"tp-{uuid.uuid4().hex[:6]}")
    return product


class TestVerifiedPurchase:
    def test_customer_without_order_is_not_verified(self):
        product = _make_product()
        review = composition.build_create_review().execute(customer_id=uuid.uuid4(), product_id=product.id, rating=5, body="Nice", title=None, at=timezone.now())
        assert review.verified_purchase is False

    def test_customer_with_delivered_order_is_verified(self):
        product = _make_product()
        customer_id = uuid.uuid4()
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active")
        order = o_models.OrderModel.objects.create(id=uuid.uuid4(), order_number=f"NZ-{uuid.uuid4().hex[:8]}", status="delivered", customer_id=customer_id, currency="UZS")
        o_models.OrderLineItemModel.objects.create(id=uuid.uuid4(), order=order, product_variant_id=variant.id, quantity=1, unit_price_amount=100000, status="active")

        review = composition.build_create_review().execute(customer_id=customer_id, product_id=product.id, rating=4, body="Good", title=None, at=timezone.now())
        assert review.verified_purchase is True


class TestReviewLifecycle:
    def test_full_lifecycle_create_media_submit_publishes_immediately(self):
        """Real, explicit product decision: SubmitReview now carries a review straight through approve()/publish() itself (see its own docstring) -- no separate admin action needed. Calling the standalone admin ApproveReview afterward correctly rejects it (already PUBLISHED, not PENDING_MODERATION), proving the real state machine ran rather than being bypassed."""
        product = _make_product()
        review = composition.build_create_review().execute(customer_id=uuid.uuid4(), product_id=product.id, rating=5, body="Excellent", title="Great", at=timezone.now())
        assert review.status.value == "draft"

        buf = io.BytesIO()
        Image.new("RGB", (100, 100), color="blue").save(buf, format="JPEG")
        with_media = composition.build_attach_review_media().execute(review.id, media_type="image", filename="photo.jpg", content=buf.getvalue(), mime_type="image/jpeg", at=timezone.now())
        assert with_media is not None

        submitted = composition.build_submit_review().execute(review.id, timezone.now())
        assert submitted.status.value == "published"

        from apps.reviews.domain.exceptions import InvalidReviewLifecycleTransition

        with pytest.raises(InvalidReviewLifecycleTransition):
            composition.build_approve_review().execute(review.id, timezone.now())

    def test_reject_flow(self):
        """RejectReview itself is unchanged and still a real, callable admin action on a genuinely PENDING_MODERATION review -- the fixture drives the aggregate there directly (mirroring test_api_integration.py's own established pattern) since the real customer-facing SubmitReview no longer leaves a review in that state (see its own docstring)."""
        from apps.reviews.infrastructure.repositories import DjangoReviewRepository

        product = _make_product()
        review = composition.build_create_review().execute(customer_id=uuid.uuid4(), product_id=product.id, rating=1, body="Bad", title=None, at=timezone.now())
        review.submit(timezone.now())
        DjangoReviewRepository().save(review)

        rejected = composition.build_reject_review().execute(review.id, reason="spam", at=timezone.now())
        assert rejected.status.value == "rejected"

    def test_editing_a_published_review_re_publishes_immediately(self):
        """Real, explicit product decision, same as SubmitReview: `edit_content()`'s own unmodified rule still resets a PUBLISHED review to PENDING_MODERATION on edit, but EditReview now immediately carries it back through approve()/publish() too -- an edited review is never left stuck waiting on an admin action this product decision says isn't required."""
        product = _make_product()
        review = composition.build_create_review().execute(customer_id=uuid.uuid4(), product_id=product.id, rating=4, body="Good", title=None, at=timezone.now())
        published = composition.build_submit_review().execute(review.id, timezone.now())
        assert published.status.value == "published"

        edited = composition.build_edit_review().execute(review.id, body="Even better, actually.", at=timezone.now())
        assert edited.status.value == "published"
        assert edited.body.value == "Even better, actually."

    def test_rejected_review_still_never_shows_up_publicly(self):
        """Sanity check: the auto-publish decision only ever applies to the real, unmodified submit()/edit_content() transitions above -- a rejected review is still exactly as invisible as before."""
        from apps.reviews.infrastructure.repositories import DjangoReviewRepository

        product = _make_product()
        review = composition.build_create_review().execute(customer_id=uuid.uuid4(), product_id=product.id, rating=1, body="Bad", title=None, at=timezone.now())
        review.submit(timezone.now())
        DjangoReviewRepository().save(review)
        composition.build_reject_review().execute(review.id, reason="spam", at=timezone.now())

        from apps.reviews.infrastructure.selectors import ReviewSelector

        public_reviews, _total = ReviewSelector().list_published_for_product(product.id, page=1, page_size=50)
        assert all(r["id"] != str(review.id) for r in public_reviews)


class TestReviewsRealHttpFlow:
    def _real_authenticated_client(self) -> tuple[Client, dict]:
        client = Client()
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        client.post("/api/v1/identity/auth/request-otp", data=json.dumps({"phone_number": phone}), content_type="application/json")
        challenge = identity_orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
        challenge.code_hash = hash_otp_code("999999")
        challenge.save(update_fields=["code_hash"])
        response = client.post("/api/v1/identity/auth/verify-otp", data=json.dumps({"phone_number": phone, "code": "999999"}), content_type="application/json")
        access_token = json.loads(response.content)["data"]["access_token"]
        return client, {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

    def test_real_customer_can_create_attach_media_and_submit_a_review(self):
        """Regression for migration 0013: customer role previously lacked reviews.review.create/edit and reviews.media.manage, causing a real 403."""
        client, auth = self._real_authenticated_client()
        product = _make_product()

        create_response = client.post("/api/v1/reviews/", data=json.dumps({"product_id": str(product.id), "rating": 5, "body": "Great!", "title": "Nice"}), content_type="application/json", **auth)
        assert create_response.status_code == 201
        review_id = json.loads(create_response.content)["data"]["id"]

        buf = io.BytesIO()
        Image.new("RGB", (100, 100), color="red").save(buf, format="JPEG")
        from django.core.files.uploadedfile import SimpleUploadedFile

        media_response = client.post(f"/api/v1/reviews/{review_id}/media", data={"media_type": "image", "file_upload": SimpleUploadedFile("my-photo.jpg", buf.getvalue(), content_type="image/jpeg")}, **auth)
        assert media_response.status_code == 200

        submit_response = client.post(f"/api/v1/reviews/{review_id}/submit", data=json.dumps({}), content_type="application/json", **auth)
        assert submit_response.status_code == 200
        assert json.loads(submit_response.content)["data"]["status"] == "published"  # real product decision: no admin approval required (see SubmitReview's own docstring)

        media_list_response = client.get(f"/api/v1/reviews/{review_id}/media", **auth)
        assert media_list_response.status_code == 200
        assert len(json.loads(media_list_response.content)["data"]) == 1
