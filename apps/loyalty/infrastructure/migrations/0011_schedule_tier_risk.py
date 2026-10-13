"""Schedules loyalty.tier_risk_reminders daily at 10:00 Tashkent: warns customers whose tier is about to lapse."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Loyalty: tier-at-risk reminders"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="0", hour="10", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "loyalty.tier_risk_reminders", "crontab": schedule, "interval": None, "enabled": True, "description": "apps/loyalty/infrastructure/tasks.py::tier_risk_reminders"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0010_loyaltysettings_subscribe_gift_coins"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
