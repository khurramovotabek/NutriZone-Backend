"""Schedules payment.unpaid_orders (every 5 min) and payment.reconcile (daily 06:00 Tashkent); seeds PaymentSettings."""
from __future__ import annotations

from django.db import migrations

UNPAID, RECONCILE = "Payments: unpaid online orders", "Payments: daily reconciliation"


def forwards(apps, schema_editor):
    Interval = apps.get_model("django_celery_beat", "IntervalSchedule")
    Crontab = apps.get_model("django_celery_beat", "CrontabSchedule")
    Task = apps.get_model("django_celery_beat", "PeriodicTask")
    every5, _ = Interval.objects.get_or_create(every=5, period="minutes")
    Task.objects.update_or_create(name=UNPAID, defaults={"task": "payment.unpaid_orders", "interval": every5, "crontab": None, "enabled": True,
                                                         "description": "apps/payment/infrastructure/tasks.py::unpaid_orders"})
    six, _ = Crontab.objects.get_or_create(minute="0", hour="6", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    Task.objects.update_or_create(name=RECONCILE, defaults={"task": "payment.reconcile", "crontab": six, "interval": None, "enabled": True,
                                                            "description": "apps/payment/infrastructure/tasks.py::reconcile"})
    apps.get_model("payment", "PaymentSettings").objects.get_or_create(pk=1)


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name__in=[UNPAID, RECONCILE]).delete()


class Migration(migrations.Migration):
    dependencies = [("payment", "0004_automation_reconciliation"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
