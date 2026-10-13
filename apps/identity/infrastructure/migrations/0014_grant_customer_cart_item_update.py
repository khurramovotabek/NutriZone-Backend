"""
Real, live-verified RBAC gap found while checking the storefront's
Checkout "additional note" field end to end: a real customer calling
`PATCH /api/v1/cart/{code}/` (UpdateCartView, the only way to save the
Cart.note/gift_message a Checkout comment field writes to) received a
live 403 PERMISSION_DENIED.

Root cause, confirmed by direct migration history inspection: the
"customer" role was granted `cart.item.create`, `cart.item.view`,
`cart.line_item.manage`, `cart.price_reference.manage`,
`cart.validation.execute`, and `cart.checkout.execute` (0002/0004) --
but never `cart.item.update`, the exact code `CanUpdateCart` requires
(apps/cart/interfaces/api/v1/permissions.py). Every other cart
permission a normal shopper needs was granted; this one was simply
missed when the note/gift_message PATCH endpoint was built.

Grants exactly the 1 missing code, confirmed directly against
`CanUpdateCart.permission_code`. Deliberately does NOT touch any
other permission -- matching 0004/0010/0011/0012/0013's identical
minimum-required-privilege convention.
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"
NEW_PERMISSION_CODE = "cart.item.update"


def grant_cart_item_update(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return  # Fails open on missing seed data, matching 0004/0010/0011/0012/0013's own established convention.

    permission, _ = Permission.objects.get_or_create(code=NEW_PERMISSION_CODE, defaults={"id": uuid.uuid4(), "description": NEW_PERMISSION_CODE})
    RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def revoke_cart_item_update(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return
    RolePermission.objects.filter(role=role, permission__code=NEW_PERMISSION_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0013_grant_customer_reviews_write"),
    ]

    operations = [
        migrations.RunPython(grant_cart_item_update, revoke_cart_item_update),
    ]
