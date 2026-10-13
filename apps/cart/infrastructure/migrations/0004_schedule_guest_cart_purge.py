"""Schedules cart.purge_empty_guest_carts weekly (Sunday 04:00 Tashkent): empty guest carts idle for 30+ days are deleted."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Cart: purge empty guest carts (weekly)"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="0", hour="4", day_of_week="0", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "cart.purge_empty_guest_carts", "crontab": schedule, "interval": None, "enabled": True,
                  "description": "apps/cart/infrastructure/tasks.py::purge_empty_guest_carts -- empty guest carts idle 30+ days"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("cart", "0003_alter_attachedreservationmodel_options_and_more"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
