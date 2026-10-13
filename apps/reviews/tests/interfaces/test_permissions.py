from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.reviews.interfaces.api.v1.permissions import (
    AdminReviews, BaseReviewPermission, CreateReview, EditReview, ManageReviewMedia, ModerateReview, ViewOwnReviews,
    ViewStatistics,
)
from common.permissions import HasPermissionCode

pytestmark = pytest.mark.unit


class _FakeResolver:
    def __init__(self, granted_codes: set[str]) -> None:
        self.granted_codes = granted_codes

    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code in self.granted_codes


@pytest.fixture(autouse=True)
def _reset_resolver():
    original = HasPermissionCode.resolver
    yield
    HasPermissionCode.resolver = original


@pytest.mark.parametrize(
    "permission_cls,expected_code",
    [
        (ViewOwnReviews, "reviews.review.view_own"), (CreateReview, "reviews.review.create"),
        (EditReview, "reviews.review.edit"), (ModerateReview, "reviews.review.moderate"),
        (ManageReviewMedia, "reviews.media.manage"), (ViewStatistics, "reviews.statistics.view"),
        (AdminReviews, "reviews.admin.manage"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_7_permission_codes_are_unique():
    codes = {
        ViewOwnReviews.permission_code, CreateReview.permission_code, EditReview.permission_code,
        ModerateReview.permission_code, ManageReviewMedia.permission_code, ViewStatistics.permission_code,
        AdminReviews.permission_code,
    }
    assert len(codes) == 7


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"reviews.review.create"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CreateReview().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"reviews.review.moderate"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert ModerateReview().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert AdminReviews().has_permission(request, view=None) is False


def test_base_permission_fails_closed_with_no_code():
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert BaseReviewPermission().has_permission(request, view=None) is False
