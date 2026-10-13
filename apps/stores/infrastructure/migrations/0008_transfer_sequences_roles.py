from django.db import migrations

ROLES = {
    # Warehouse operator: prepares transfers (create, add products, scan-pick) and posts goods receipts.
    "Sklad operatori": ["view_stocktransfer", "add_stocktransfer", "change_stocktransfer", "view_stockreceipt", "add_stockreceipt", "view_stockmovement"],
    # Warehouse manager: everything the operator does, plus dispatch, cancel and approve discrepancies.
    "Sklad menejeri": [
        "view_stocktransfer", "add_stocktransfer", "change_stocktransfer", "send_stocktransfer", "cancel_stocktransfer", "approve_discrepancy",
        "view_stockreceipt", "add_stockreceipt", "view_stockmovement",
    ],
    # Branch receiver: sees transfers and receives shipments at the branch.
    "Filial qabul qiluvchi": ["view_stocktransfer", "receive_stocktransfer", "view_stockmovement"],
    # Inventory manager: full inventory control.
    "Inventar menejeri": [
        "view_stocktransfer", "add_stocktransfer", "change_stocktransfer", "send_stocktransfer", "receive_stocktransfer", "cancel_stocktransfer",
        "approve_discrepancy", "view_stockreceipt", "add_stockreceipt", "view_stockmovement",
    ],
}


def roles(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    for config in apps.get_app_configs():
        config.models_module = True
        create_permissions(config, apps=apps, verbosity=0)
        config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, codenames in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.add(*Permission.objects.filter(content_type__app_label="stores", codename__in=codenames))


class Migration(migrations.Migration):
    dependencies = [("stores", "0007_warehouses_ledger_transfers"), ("auth", "0012_alter_user_first_name_max_length"), ("contenttypes", "0002_remove_content_type_name")]

    operations = [
        migrations.RunSQL(
            "CREATE SEQUENCE IF NOT EXISTS stores_transfer_number_seq START 1; CREATE SEQUENCE IF NOT EXISTS stores_receipt_number_seq START 1;",
            "DROP SEQUENCE IF EXISTS stores_transfer_number_seq; DROP SEQUENCE IF EXISTS stores_receipt_number_seq;",
        ),
        migrations.RunPython(roles, migrations.RunPython.noop),
    ]
