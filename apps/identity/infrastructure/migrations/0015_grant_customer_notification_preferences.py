"""
Customers can now manage their own notification preferences from the
storefront settings page (e.g. turn off promotional Telegram messages).
The "customer" role never had `notifications.preference.manage_own`, so
`/notifications/preferences*` answered 403 for every customer.
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"
CODES = ["notifications.preference.manage_own"]


def grant(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")
    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return
    for code in CODES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"id": uuid.uuid4(), "description": code})
        RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def revoke(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")
    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is not None:
        RolePermission.objects.filter(role=role, permission__code__in=CODES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0014_grant_customer_cart_item_update"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
