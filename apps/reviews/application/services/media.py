"""
AttachReviewMedia Application Service.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction

from apps.reviews.application.ports import ReviewRepository
from apps.reviews.application.services._shared import ReviewsServiceContext
from apps.reviews.domain.aggregates import Review
from apps.reviews.domain.enums import ReviewMediaType
from common.exceptions import ResourceNotFound, ValidationFailed


class AttachReviewMedia:
    """
    Real file upload -- runs through the same core.media.MediaPipeline
    already established for Brand/Category/Banner/BlogPost/Product
    (validation, thumbnail generation), matching this build's own
    "direct storage fields, no shared Media Asset table" convention.
    The resulting real storage_path is stored in the domain/ORM `url`
    field (name kept as-is -- it now holds a real internal path
    rather than an external link, but renaming it is out of this
    phase's scope).
    """

    def __init__(self, repo: ReviewRepository, media_pipeline, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._media_pipeline = media_pipeline
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, media_type: str, filename: str, content: bytes, mime_type: str, at: datetime) -> Review:
        from core.media import MediaType, MediaUploadRequest

        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")

        pipeline_media_type = MediaType.VIDEO if media_type == ReviewMediaType.VIDEO.value else MediaType.IMAGE
        request = MediaUploadRequest(filename=filename, content=content, mime_type=mime_type, media_type=pipeline_media_type)
        result = self._media_pipeline.process(request)
        if result.is_failure:
            first_error = result.errors[0]
            raise ValidationFailed(first_error.message, details={"fields": [{"field": "file_upload", "code": first_error.code}]})

        processed = result.value
        event = review.attach_media(ReviewMediaType(media_type), processed.storage_path, at)
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewMediaAttached", event.to_payload())])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"media_type": media_type, "storage_path": processed.storage_path})
        self._ctx.metric("review_media_attached_total")
        return saved
