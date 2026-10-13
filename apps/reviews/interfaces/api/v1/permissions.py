"""
Reviews API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern -- every class below is a
thin, named wrapper calling `common.permissions.HasPermissionCode.
resolver` with a Reviews-specific permission code. Every class fails
closed by default (no code, no resolver, no auth -> denied).

Every permission below has a real endpoint usage in `views.py` --
verified by direct grep after this file and `views.py` were both
written, not just declared as an intention. None are speculative.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from common.permissions import HasPermissionCode


class BaseReviewPermission(BasePermission):
    """Base class -- subclasses set `permission_code`. Fails closed if no code is set."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class ViewOwnReviews(BaseReviewPermission):
    """A customer viewing their own submitted reviews -- distinct from viewing any review of a product (which is a public/anonymous-readable capability, see `views.py`'s product-review-list endpoint)."""

    permission_code = "reviews.review.view_own"


class CreateReview(BaseReviewPermission):
    permission_code = "reviews.review.create"


class EditReview(BaseReviewPermission):
    """Covers submit/edit/withdraw -- the customer-controlled lifecycle actions on their own review, distinct from moderation."""

    permission_code = "reviews.review.edit"


class ModerateReview(BaseReviewPermission):
    """Covers approve/reject/publish/hide -- the staff-controlled moderation lifecycle."""

    permission_code = "reviews.review.moderate"


class ManageReviewMedia(BaseReviewPermission):
    permission_code = "reviews.media.manage"


class ViewStatistics(BaseReviewPermission):
    permission_code = "reviews.statistics.view"


class AdminReviews(BaseReviewPermission):
    """Umbrella admin permission -- used for the admin listing endpoint, same role as every other module's Admin* permission."""

    permission_code = "reviews.admin.manage"
