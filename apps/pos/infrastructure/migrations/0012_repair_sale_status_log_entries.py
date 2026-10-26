import json

from django.db import migrations


def repair(apps, schema_editor):
    """Status-change audit entries written as {"changed": {"fields", "name"}} without "object" crash the admin's recent actions; rewrite them as plain text."""
    LogEntry = apps.get_model("admin", "LogEntry")
    for entry in LogEntry.objects.filter(change_message__startswith="[", change_message__contains='"name"'):
        try:
            messages = json.loads(entry.change_message)
        except ValueError:
            continue
        broken = [m["changed"] for m in messages if isinstance(m, dict) and isinstance(m.get("changed"), dict) and "name" in m["changed"] and "object" not in m["changed"]]
        if broken:
            text = "; ".join(f"{m['name']}: {', '.join(m.get('fields') or [])}" for m in broken)
            LogEntry.objects.filter(pk=entry.pk).update(change_message=text)


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0011_sale_parked"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]

    operations = [migrations.RunPython(repair, migrations.RunPython.noop)]
