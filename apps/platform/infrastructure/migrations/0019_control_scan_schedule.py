"""Schedules platform.control_scan every 2 minutes: the control centre's rules + Telegram alerts (control_center.py)."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Nazorat markazi: shubhali operatsiyalar va favqulodda holatlar"


def forwards(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=2, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "platform.control_scan", "interval": schedule, "crontab": None, "enabled": True, "queue": "default",
                  "description": "apps/platform/infrastructure/control_center.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("platform", "0018_control_center"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
