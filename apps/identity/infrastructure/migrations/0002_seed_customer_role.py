"""
Phase 09.4b: seeds a least-privilege "customer" Role.

Permission codes match exactly what real, live end-to-end testing in
Phases 09.2/09.4 confirmed necessary for a customer to create and use
their own cart and receive a server-authoritative price -- no more,
no less. No staff/admin permission is included.
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"

CUSTOMER_PERMISSION_CODES = [
    "cart.item.create",
    "cart.item.view",
    "cart.line_item.manage",
    "cart.price_reference.manage",
    "pricing.snapshot.issue",
]


def seed_customer_role(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role, _ = Role.objects.get_or_create(code=CUSTOMER_ROLE_CODE, defaults={"id": uuid.uuid4(), "name": "Customer", "is_system_role": True})

    for code in CUSTOMER_PERMISSION_CODES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"id": uuid.uuid4(), "description": code})
        RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def unseed_customer_role(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Role.objects.filter(code=CUSTOMER_ROLE_CODE, is_system_role=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_customer_role, unseed_customer_role),
    ]
