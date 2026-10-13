"""
Reviews repositories.

Concrete implementation of application/ports.py's `ReviewRepository`
Protocol -- maps ORM rows to domain dataclasses only, never leaks ORM
objects outside this module, matching the pattern established by
every prior module.
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError

from apps.reviews.domain.aggregates import Review
from apps.reviews.domain.entities import ReviewMedia
from apps.reviews.domain.enums import ReviewMediaType, ReviewStatus
from apps.reviews.domain.value_objects import Rating, ReviewBody, ReviewTitle, ReviewVersion
from apps.reviews.infrastructure import models as orm
from common.exceptions import ConflictError


class DjangoReviewRepository:
    def get_by_id(self, review_id: uuid.UUID) -> Review | None:
        row = orm.ReviewModel.objects.filter(id=review_id).prefetch_related("media_items").first()
        return self._to_domain(row) if row else None

    def list_for_product(self, product_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Review], int]:
        qs = orm.ReviewModel.objects.filter(product_id=product_id)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def list_for_customer(self, customer_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Review], int]:
        qs = orm.ReviewModel.objects.filter(customer_id=customer_id)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def save(self, review: Review) -> Review:
        try:
            row, _ = orm.ReviewModel.objects.update_or_create(
                id=review.id,
                defaults={
                    "product_id": review.product_id, "customer_id": review.customer_id, "rating": review.rating.value,
                    "title": review.title.value if review.title else None, "body": review.body.value,
                    "verified_purchase": review.verified_purchase, "status": review.status.value, "version": review.version.value,
                    "submitted_at": review.submitted_at, "moderated_at": review.moderated_at, "published_at": review.published_at,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A review with conflicting unique fields already exists.") from exc

        existing_media_ids = set(row.media_items.values_list("id", flat=True))
        for item in review.media.values():
            if item.id not in existing_media_ids:
                orm.ReviewMediaModel.objects.create(id=item.id, review=row, media_type=item.media_type.value, url=item.url, uploaded_at=item.uploaded_at)
        return review

    def list_for_admin(self, status: str | None, page: int, page_size: int) -> tuple[list[Review], int]:
        qs = orm.ReviewModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.ReviewModel) -> Review:
        media = {}
        for m in row.media_items.all():
            item = ReviewMedia(id=m.id, media_type=ReviewMediaType(m.media_type), url=m.url, uploaded_at=m.uploaded_at)
            media[item.id] = item

        return Review(
            id=row.id, product_id=row.product_id, customer_id=row.customer_id, rating=Rating(row.rating),
            body=ReviewBody(row.body), verified_purchase=row.verified_purchase, title=ReviewTitle(row.title) if row.title else None,
            status=ReviewStatus(row.status), version=ReviewVersion(row.version), media=media,
            created_at=row.created_at, submitted_at=row.submitted_at, moderated_at=row.moderated_at, published_at=row.published_at,
        )
