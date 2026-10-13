"""
Composition root for the `reviews` module.

**Application Services now real, per this phase's own work**: the
prior disclosed gap (`apps/reviews/application/services/` containing
only an empty `__init__.py`) is closed -- CreateReview, SubmitReview,
EditReview, ApproveReview, RejectReview, PublishReview, HideReview,
WithdrawReview, and AttachReviewMedia are now real, wired here exactly
like every other module's composition root.
"""
from __future__ import annotations

import uuid

from apps.reviews.application.services._shared import ReviewsServiceContext
from apps.reviews.application.services.lifecycle import (
    ApproveReview, CreateReview, EditReview, HideReview, PublishReview, RejectReview, SubmitReview, WithdrawReview,
)
from apps.reviews.application.services.media import AttachReviewMedia
from apps.reviews.infrastructure.gateways import NotImplementedMediaStorageGateway, NotImplementedNotificationGateway
from apps.reviews.infrastructure.models import ReviewOutboxEvent
from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.infrastructure.selectors import ReviewMediaSelector, ReviewSelector, ReviewStatisticsSelector
from common.middleware.audit_context import get_current_actor_id
from core.outbox import stage_event


def _stage_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(ReviewOutboxEvent, event_type, payload)


def _build_ctx(actor_id: uuid.UUID | None = None) -> ReviewsServiceContext:
    return ReviewsServiceContext(stage_events=_stage_events, actor_id=actor_id or get_current_actor_id())


def build_review_repository() -> DjangoReviewRepository:
    return DjangoReviewRepository()


def build_review_selector() -> ReviewSelector:
    return ReviewSelector()


def build_review_media_selector() -> ReviewMediaSelector:
    return ReviewMediaSelector()


def build_review_statistics_selector() -> ReviewStatisticsSelector:
    return ReviewStatisticsSelector()


def build_notification_gateway() -> NotImplementedNotificationGateway:
    return NotImplementedNotificationGateway()


def build_create_review(actor_id: uuid.UUID | None = None) -> CreateReview:
    return CreateReview(build_review_repository(), _build_ctx(actor_id))


def build_submit_review(actor_id: uuid.UUID | None = None) -> SubmitReview:
    return SubmitReview(build_review_repository(), _build_ctx(actor_id))


def build_edit_review(actor_id: uuid.UUID | None = None) -> EditReview:
    return EditReview(build_review_repository(), _build_ctx(actor_id))


def build_approve_review(actor_id: uuid.UUID | None = None) -> ApproveReview:
    return ApproveReview(build_review_repository(), _build_ctx(actor_id))


def build_reject_review(actor_id: uuid.UUID | None = None) -> RejectReview:
    return RejectReview(build_review_repository(), _build_ctx(actor_id))


def build_publish_review(actor_id: uuid.UUID | None = None) -> PublishReview:
    return PublishReview(build_review_repository(), _build_ctx(actor_id))


def build_hide_review(actor_id: uuid.UUID | None = None) -> HideReview:
    return HideReview(build_review_repository(), _build_ctx(actor_id))


def build_withdraw_review(actor_id: uuid.UUID | None = None) -> WithdrawReview:
    return WithdrawReview(build_review_repository(), _build_ctx(actor_id))


def build_attach_review_media(actor_id: uuid.UUID | None = None) -> AttachReviewMedia:
    from apps.products.infrastructure.composition import build_media_pipeline

    return AttachReviewMedia(build_review_repository(), build_media_pipeline(), _build_ctx(actor_id))


def build_media_storage_gateway() -> NotImplementedMediaStorageGateway:
    return NotImplementedMediaStorageGateway()
