"""
Seeds the launch tier ladder and schedules the reconcile safety-net task.

Tiers (lifetime delivered/completed spend, UZS; min inclusive, max exclusive):
    Bronza   0          – 1 000 000    1%
    Kumush   1 000 000  – 5 000 000    2%
    VIP      5 000 000  – 15 000 000   3%
    Diamond  15 000 000 – ∞            5%
All editable afterwards in the dashboard (Loyalty & Wallet → Loyalty tiers).
Uses update_or_create by slug, so re-running never duplicates or overwrites
an existing tier's edited values beyond these defaults on first creation.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import migrations

TASK_NAME = "Loyalty: reconcile order rewards"

TIERS = [
    {"slug": "bronze", "name": "Bronza", "min_spend": Decimal("0"), "max_spend": Decimal("1000000"), "percent": Decimal("1"), "icon": "bronze", "color": "#cd7f32", "description": "Birinchi xariddan boshlab har bir buyurtmaga 1% coin."},
    {"slug": "silver", "name": "Kumush", "min_spend": Decimal("1000000"), "max_spend": Decimal("5000000"), "percent": Decimal("2"), "icon": "silver", "color": "#9aa7b8", "description": "1 mln so'mdan ortiq xarid qilgan mijozlar uchun 2% coin."},
    {"slug": "vip", "name": "VIP", "min_spend": Decimal("5000000"), "max_spend": Decimal("15000000"), "percent": Decimal("3"), "icon": "vip", "color": "#d4a017", "description": "Doimiy mijozlarimiz uchun 3% coin."},
    {"slug": "diamond", "name": "Diamond", "min_spend": Decimal("15000000"), "max_spend": None, "percent": Decimal("5"), "icon": "diamond", "color": "#38bdf8", "description": "Eng sodiq mijozlarimiz uchun maksimal 5% coin."},
]


def forwards(apps, schema_editor):
    Tier = apps.get_model("loyalty", "LoyaltyTier")
    for tier in TIERS:
        Tier.objects.get_or_create(slug=tier["slug"], defaults=tier)

    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=10, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": "loyalty.reconcile_order_rewards",
            "interval": schedule,
            "enabled": True,
            "description": "Safety net: awards/reverses coins for any order whose reward is out of step with its status (apps/loyalty/infrastructure/services.py::reconcile).",
        },
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()
    apps.get_model("loyalty", "LoyaltyTier").objects.filter(slug__in=[t["slug"] for t in TIERS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("loyalty", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
