"""Phase 11: extends the "customer" Role with ordering.order.view_own -- required for customers to view their own orders/payment status."""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"
NEW_PERMISSION_CODE = "ordering.order.view_own"


def add_permission(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return

    permission, _ = Permission.objects.get_or_create(code=NEW_PERMISSION_CODE, defaults={"id": uuid.uuid4(), "description": NEW_PERMISSION_CODE})
    RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def remove_permission(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return
    RolePermission.objects.filter(role=role, permission__code=NEW_PERMISSION_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0004_add_cart_checkout_permission"),
    ]

    operations = [
        migrations.RunPython(add_permission, remove_permission),
    ]
