"""Schedules ordering.replenish_reminders daily at 11:00 Tashkent: "your protein is running low" reminders."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Orders: replenishment reminders"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="0", hour="11", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "ordering.replenish_reminders", "crontab": schedule, "interval": None, "enabled": True, "description": "apps/ordering/infrastructure/replenishment.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("ordering", "0007_fulfilment_store"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
