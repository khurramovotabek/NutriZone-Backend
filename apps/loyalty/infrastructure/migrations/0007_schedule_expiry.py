"""Schedules loyalty.expire_coins hourly: burns expired lots and sends expiry reminders (each lot reminded once)."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Loyalty: expire coins & reminders"


def forwards(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=1, period="hours")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "loyalty.expire_coins", "interval": schedule, "enabled": True, "description": "apps/loyalty/infrastructure/tasks.py::expire_coins"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0006_backfill_lots"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
