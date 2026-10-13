"""
Activates `telegram_bot.sync_pos_sales_channel` (see
pos_sales_channel_subscriber.py): POS terminal sales are posted to the
same Telegram Orders Channel as online orders.

Two steps, both needed:

1. The Celery Beat row, on the same 30-second interval as the online
   Orders Channel sync (0004).
2. The POS cursor (row id=2 of TelegramOrdersChannelCursor -- a distinct
   singleton from the online-orders cursor, id=1) starts at the newest
   POS sale event that already exists. Without this, the first run would
   replay every historical POS sale into the live channel at once.
"""
from __future__ import annotations

from django.db import migrations

POS_CURSOR_ID = 2
TASK_NAME = "Telegram Orders Channel sync (POS Terminal)"


def forwards(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    Cursor = apps.get_model("telegram_bot", "TelegramOrdersChannelCursor")
    PosOutboxEvent = apps.get_model("pos", "PosOutboxEvent")

    latest = PosOutboxEvent.objects.filter(event_type__in=["SaleCompleted", "SaleRefunded"]).order_by("-created_at", "-id").first()
    Cursor.objects.update_or_create(
        id=POS_CURSOR_ID,
        defaults={
            "last_processed_created_at": latest.created_at if latest else None,
            "last_processed_id": latest.id if latest else None,
        },
    )

    schedule, _created = IntervalSchedule.objects.get_or_create(every=30, period="seconds")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": "telegram_bot.sync_pos_sales_channel",
            "interval": schedule,
            "enabled": True,
            "description": "Posts completed and refunded POS Terminal sales to the Telegram Orders Channel (see apps/telegram_bot/infrastructure/pos_sales_channel_subscriber.py).",
        },
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()
    apps.get_model("telegram_bot", "TelegramOrdersChannelCursor").objects.filter(id=POS_CURSOR_ID).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("telegram_bot", "0005_telegrampossalechannelmessage"),
        ("pos", "0004_sale_refund"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
