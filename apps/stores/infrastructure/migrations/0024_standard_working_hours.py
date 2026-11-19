"""The owner's standard week for every branch (2026-11-19): open 10:00 daily; Mon-Fri until 20:00, Saturday 19:00,
Sunday 17:00. 12 of 13 live branches had no hours at all, so the storefront showed them "closed" all day.
Warehouses keep theirs (not customer facing); date-specific special days are left untouched."""
from django.db import migrations

HOURS = {
    **{d: {"open": "10:00", "close": "20:00", "closed": False} for d in ("mon", "tue", "wed", "thu", "fri")},
    "sat": {"open": "10:00", "close": "19:00", "closed": False},
    "sun": {"open": "10:00", "close": "17:00", "closed": False},
}


def forwards(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.exclude(kind="warehouse").update(working_hours=HOURS)


class Migration(migrations.Migration):
    dependencies = [("stores", "0023_branch_locations_from_channel")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
