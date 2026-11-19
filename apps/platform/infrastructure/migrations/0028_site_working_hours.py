"""The site-wide "Ish vaqti" line (footer, contact page) follows the branches' new standard week (owner, 2026-11-19).
Only the old default ("10:00-21:00") or an empty value is replaced -- a line the staff wrote themselves is kept."""
from django.db import migrations

NEW = "Du–Ju 10:00–20:00 · Sh 10:00–19:00 · Ya 10:00–17:00"
OLD = {"", "10:00-21:00", "10:00–21:00"}


def forwards(apps, schema_editor):
    SiteSettings = apps.get_model("platform", "SiteSettings")
    for s in SiteSettings.objects.all():
        if (s.working_hours or "").strip() in OLD:
            s.working_hours = NEW
            s.save(update_fields=["working_hours"])


class Migration(migrations.Migration):
    dependencies = [("platform", "0027_banner_schedule_clicks")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
