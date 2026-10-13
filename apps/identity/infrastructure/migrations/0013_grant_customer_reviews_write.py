"""
Real, live-verified RBAC gap found while wiring Reviews' Application
Services (this build's own current phase): a real customer, calling
the now-real `POST /api/v1/reviews/` (CreateReviewView), received a
live 403 PERMISSION_DENIED.

Root cause, confirmed by direct migration history inspection: 0011
granted only `reviews.review.view_own` to the "customer" role,
explicitly reasoning at the time that "CreateReviewView's own POST
handler is an honest 501 regardless" -- true when 0011 was written,
no longer true now that CreateReview/EditReview are real Application
Services (this phase's own work). The permission grant was never
revisited when the 501s were closed.

Grants exactly 3 codes, confirmed directly from the real permission
class source (apps/reviews/interfaces/api/v1/permissions.py):

- reviews.review.create (CreateReview -- POST /api/v1/reviews/)
- reviews.review.edit (EditReview -- covers submit/edit/withdraw, the
  customer-controlled lifecycle actions on their own review)
- reviews.media.manage (ManageReviewMedia -- POST .../media, attaching
  a photo to one's own draft review before submitting it for
  moderation; found live-missing in the same verification pass as the
  two codes above)

Deliberately does NOT grant `reviews.review.moderate` (ModerateReview
-- approve/reject/publish/hide) or `reviews.review.view_statistics` --
both are staff-only moderation/reporting capabilities, matching this
build's own minimum-required-privilege convention exactly (0010/0011/
0012's identical scoping decision).
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"

NEW_CUSTOMER_PERMISSION_CODES = [
    "reviews.review.create",
    "reviews.review.edit",
    "reviews.media.manage",
]


def grant_reviews_write_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return  # Fails open on missing seed data, matching 0010/0011/0012's own established convention.

    for code in NEW_CUSTOMER_PERMISSION_CODES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"id": uuid.uuid4(), "description": code})
        RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def revoke_reviews_write_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return

    RolePermission.objects.filter(role=role, permission__code__in=NEW_CUSTOMER_PERMISSION_CODES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0012_grant_customer_notifications_chat_read_own"),
    ]

    operations = [
        migrations.RunPython(grant_reviews_write_own, revoke_reviews_write_own),
    ]
