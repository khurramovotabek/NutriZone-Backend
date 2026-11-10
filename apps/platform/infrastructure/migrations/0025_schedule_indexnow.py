"""Schedules platform.indexnow_submit daily at 05:30 Tashkent: changed storefront pages → IndexNow (indexnow.py)."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "SEO: IndexNow — yangilangan sahifalarni Bing va Yandex'ga yuborish"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="30", hour="5", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "platform.indexnow_submit", "crontab": schedule, "interval": None, "enabled": True, "queue": "default",
                  "description": "apps/platform/infrastructure/indexnow.py"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("platform", "0024_site_map_listings"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
