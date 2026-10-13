"""One settings row per payment method: cash on (it's how the shop works today), every online method off until configured."""
from __future__ import annotations

from django.db import migrations

ROWS = [("cash", True, 0), ("payme", False, 10), ("click", False, 20), ("uzum", False, 30), ("uzcard", False, 40), ("humo", False, 50)]


def forwards(apps, schema_editor):
    Config = apps.get_model("payment", "PaymentProviderConfig")
    for provider, enabled, order in ROWS:
        defaults = {"is_enabled": enabled, "sort_order": order, "is_test_mode": provider != "cash"}
        if provider in ("uzcard", "humo"):
            defaults["settings_public"] = {"route": "payme"}
        Config.objects.get_or_create(provider=provider, defaults=defaults)


def backwards(apps, schema_editor):
    apps.get_model("payment", "PaymentProviderConfig").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("payment", "0002_online_acquiring")]
    operations = [migrations.RunPython(forwards, backwards)]
