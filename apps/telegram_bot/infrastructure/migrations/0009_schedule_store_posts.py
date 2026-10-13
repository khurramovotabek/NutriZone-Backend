"""Schedules telegram_bot.store_posts every 30 s: branch owners' own Orders / Analytics bot feeds."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Telegram: filial egalari lentasi (Orders / Analytics bot)"


def forwards(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=30, period="seconds")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "telegram_bot.store_posts", "interval": schedule, "crontab": None, "enabled": True, "queue": "default",
                  "description": "apps/telegram_bot/infrastructure/store_posts.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("telegram_bot", "0008_bot_subscribers"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
