"""Schedules cart.auto_remind_abandoned hourly at :07, 10:00-21:59 Tashkent (no reminders at night)."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Cart: abandoned cart reminders (hourly, daytime)"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="7", hour="10-21", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "cart.auto_remind_abandoned", "crontab": schedule, "interval": None, "enabled": True,
                  "description": "apps/cart/infrastructure/cart_reminders.py -- 2 h / 24 h / 72 h reminders for signed-in customers' abandoned carts"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("cart", "0004_schedule_guest_cart_purge"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
