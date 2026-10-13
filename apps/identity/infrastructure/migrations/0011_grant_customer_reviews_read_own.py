"""
Extends Phase 16's fix pattern to Reviews: a real, live-verified
customer received 403 PERMISSION_DENIED viewing a product's reviews
(ProductReviewListView) -- the exact same root cause as Wallet/
Loyalty before migration 0010: the "customer" role was never granted
the relevant permission code after the Reviews domain was built.

Grants exactly 1 read-only code, confirmed directly from the real
permission class source (apps/reviews/interfaces/api/v1/permissions.py):

- reviews.review.view_own (ViewOwnReviews -- used by BOTH
  ProductReviewListView, whose own docstring documents it as a public,
  no-ownership-check read for any authenticated user, AND
  CustomerReviewListView, which adds its own separate object-level
  ownership check for "my own reviews")

Deliberately does NOT grant any write/moderation permission
(CreateReview, EditReview, ApproveReview/RejectReview/PublishReview/
HideReview/WithdrawReview, ViewStatistics) -- CreateReviewView's own
POST handler is an honest 501 regardless, matching this phase's own
minimum-required-privilege rule.
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"

NEW_CUSTOMER_PERMISSION_CODES = [
    "reviews.review.view_own",
]


def grant_reviews_read_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return  # Fails open on missing seed data, matching 0002/0010's own established convention.

    for code in NEW_CUSTOMER_PERMISSION_CODES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"id": uuid.uuid4(), "description": code})
        RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def revoke_reviews_read_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return

    RolePermission.objects.filter(role=role, permission__code__in=NEW_CUSTOMER_PERMISSION_CODES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0010_grant_customer_wallet_loyalty_read_own"),
    ]

    operations = [
        migrations.RunPython(grant_reviews_read_own, revoke_reviews_read_own),
    ]
