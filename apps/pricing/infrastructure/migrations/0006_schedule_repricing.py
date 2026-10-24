"""Every 5 minutes: applies repricing documents whose scheduled time has come (pricing.apply_scheduled_repricings)."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Pricing: apply scheduled repricings"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="*/5", hour="*", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "pricing.apply_scheduled_repricings", "crontab": schedule, "interval": None, "enabled": True, "queue": "default",
                  "description": "apps/pricing/infrastructure/repricing.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("pricing", "0005_repricing"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
