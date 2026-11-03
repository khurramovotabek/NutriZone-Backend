"""
A customer the POS kassa registered by phone (stores/pos_service.set_customer) was created without the "customer"
role, and signing in later does not add it (only a brand-new account gets it) -- so their orders, cart and
checkout answered 403 on the website. The POS now assigns the role; this gives it to every account that has no
role at all. Accounts with any role (staff, managers) are left exactly as they are.
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"


def grant(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    User = apps.get_model("identity", "User")
    UserRole = apps.get_model("identity", "UserRole")
    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return
    roleless = User._base_manager.exclude(id__in=UserRole._base_manager.values("user_id")).values_list("id", flat=True)
    UserRole._base_manager.bulk_create([UserRole(id=uuid.uuid4(), user_id=user_id, role_id=role.id, store_id=None) for user_id in roleless], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0016_user_language_default_uz"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
