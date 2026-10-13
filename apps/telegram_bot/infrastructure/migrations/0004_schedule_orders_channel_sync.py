"""
Real, closed gap: `telegram_bot.sync_orders_channel` (Phase 15E --
see orders_channel_subscriber.py's own module docstring) was fully
implemented -- posts every new order to the real, configured Telegram
Orders Channel (`TELEGRAM_ORDERS_CHAT_ID`) with product lines, total,
customer phone, delivery address, GPS location, and product image, and
its own Confirm/Cancel inline buttons already drive the real
ConfirmOrder/CancelOrder application services (see
callback_router.py::_handle_manager_action) -- but the Celery Beat
schedule (django_celery_beat's own DB-backed scheduler, per Django
Implementation Blueprint §8) never had a `PeriodicTask` row created
for it, so the task never actually ran. This is that one missing
activation step, not a new feature: a real, existing, already-tested
task, scheduled every 30 seconds (fast enough for a manager to see a
new order arrive within moments, without hammering the Telegram API).
"""
from __future__ import annotations

from django.db import migrations


def schedule_orders_channel_sync(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _created = IntervalSchedule.objects.get_or_create(every=30, period="seconds")

    PeriodicTask.objects.update_or_create(
        name="Telegram Orders Channel sync",
        defaults={
            "task": "telegram_bot.sync_orders_channel",
            "interval": schedule,
            "enabled": True,
            "description": "Posts newly-created orders to the Telegram Orders Channel and keeps it in sync (see apps/telegram_bot/infrastructure/orders_channel_subscriber.py).",
        },
    )


def unschedule_orders_channel_sync(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="Telegram Orders Channel sync").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("telegram_bot", "0003_telegramorderchannelmessage_and_more"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(schedule_orders_channel_sync, unschedule_orders_channel_sync),
    ]
