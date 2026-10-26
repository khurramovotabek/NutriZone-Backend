"""Every minute: each module's Outbox relay (<module>.relay_outbox_events) -- written since launch, never scheduled.

The backlog staged before this migration is marked published without replaying it: the handlers only bump cache versions and
metrics, except chat's, which would Telegram customers operator replies that are days old by now.
"""
from __future__ import annotations

from django.db import migrations
from django.utils import timezone

# app label -> concrete Outbox model
RELAYS = {
    "identity": "IdentityOutboxEvent",
    "products": "ProductsOutboxEvent",
    "geo": "GeoOutboxEvent",
    "pricing": "PricingOutboxEvent",
    "inventory": "InventoryOutboxEvent",
    "cart": "CartOutboxEvent",
    "ordering": "OrderingOutboxEvent",
    "chat": "ChatOutboxEvent",
    "pos": "PosOutboxEvent",
    "reviews": "ReviewOutboxEvent",
    "notifications": "NotificationOutboxEvent",
}


def _task_name(app_label):
    return f"Outbox relay: {app_label}"


def forwards(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="*", hour="*", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Tashkent")
    now = timezone.now()
    for app_label, model_name in RELAYS.items():
        apps.get_model(app_label, model_name).objects.filter(published_at__isnull=True).update(published_at=now)
        PeriodicTask.objects.update_or_create(
            name=_task_name(app_label),
            defaults={"task": f"{app_label}.relay_outbox_events", "crontab": schedule, "interval": None, "enabled": True, "queue": "transactional",
                      "description": f"apps/{app_label}/infrastructure/tasks.py"},
        )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name__in=[_task_name(a) for a in RELAYS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform", "0022_site_settings_search_engine_codes"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("identity", "0016_user_language_default_uz"),
        ("products", "0034_variant_flavour_and_product_grouping"),
        ("geo", "0009_region_districts"),
        ("pricing", "0006_schedule_repricing"),
        ("inventory", "0004_stock_transfers"),
        ("cart", "0004_schedule_guest_cart_purge"),
        ("ordering", "0009_delivery_desk"),
        ("chat", "0009_quick_reply_variables_and_closings"),
        ("pos", "0012_repair_sale_status_log_entries"),
        ("reviews", "0004_alter_reviewmediamodel_options"),
        ("notifications", "0008_broadcast_segment_audience"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
