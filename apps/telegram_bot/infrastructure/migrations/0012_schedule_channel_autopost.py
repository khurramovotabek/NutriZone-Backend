"""Schedules telegram_bot.channel_autopost every 15 minutes (it does nothing until enabled in the dashboard)."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Telegram: kanal avtopostlari (yangi / chegirma / yana sotuvda)"


def forwards(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=15, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "telegram_bot.channel_autopost", "interval": schedule, "crontab": None, "enabled": True, "queue": "default",
                  "description": "apps/telegram_bot/infrastructure/channel_autopost.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("telegram_bot", "0011_channel_autopost"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
