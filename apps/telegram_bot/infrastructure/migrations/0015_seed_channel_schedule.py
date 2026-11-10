"""The shop channel's daily schedule: 10:00 / 15:00 / 20:00 product posts + the every-minute runner (daily_posts.py)."""
from __future__ import annotations

import datetime

from django.db import migrations

TASK_NAME = "Telegram: kanal jadvali va rejalashtirilgan postlar"
SLOTS = [(datetime.time(10, 0), "top", "☀️ Kun mahsuloti"), (datetime.time(15, 0), "sale", "🔥 Kun taklifi"), (datetime.time(20, 0), "pick", "🌙 Kechki tavsiya")]


def forwards(apps, schema_editor):
    Settings = apps.get_model("telegram_bot", "ChannelAutoPostSettings")
    Slot = apps.get_model("telegram_bot", "ChannelPostSlot")
    row, _ = Settings.objects.get_or_create(pk=1)
    if not Slot.objects.exists():
        for time, kind, heading in SLOTS:
            Slot.objects.create(settings=row, time=time, kind=kind, heading=heading)
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=1, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "telegram_bot.channel_schedule", "interval": schedule, "crontab": None, "enabled": True, "queue": "default",
                  "description": "apps/telegram_bot/infrastructure/daily_posts.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("telegram_bot", "0014_channel_daily_schedule"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
