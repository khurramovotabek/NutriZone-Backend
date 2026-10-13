"""
Replaces the 4-tier launch ladder with the 8-tier programme.

    Tier       Lifetime spend (UZS, min incl. / max excl.)   Cashback
    Bronza     0           – 1 000 000                       1%
    Silver     1 000 000   – 3 000 000                       2%
    Gold       3 000 000   – 6 000 000                       3%
    Platinum   6 000 000   – 10 000 000                      4%
    Diamond    10 000 000  – 20 000 000                      5%
    Elite      20 000 000  – 35 000 000                      6%
    Legend     35 000 000  – 50 000 000                      7%
    VIP        50 000 000  – ∞                               8%

Percentages are the product decision; the spend thresholds are launch
defaults -- both are edited from the dashboard (Loyalty tiers). Existing
slugs are updated in place (never deleted), so past ledger rows keep
pointing at a real tier; ledger rows carry their own tier snapshot anyway.
"""
from __future__ import annotations

from decimal import Decimal as D

from django.db import migrations

LADDER = [
    ("bronze", "Bronze", "0", "1000000", "1", "bronze", "#c07a45", "Birinchi xariddan boshlab har bir buyurtmaga 1% coin."),
    ("silver", "Silver", "1000000", "3000000", "2", "silver", "#9fb0c3", "1 mln so'mdan ortiq xarid qilganlar uchun 2% coin."),
    ("gold", "Gold", "3000000", "6000000", "3", "gold", "#e0a91b", "Doimiy xaridorlar uchun 3% coin."),
    ("platinum", "Platinum", "6000000", "10000000", "4", "platinum", "#8fb4c9", "Faol mijozlar uchun 4% coin."),
    ("diamond", "Diamond", "10000000", "20000000", "5", "diamond", "#3fb6f5", "10 mln so'mdan ortiq xarid — 5% coin."),
    ("elite", "Elite", "20000000", "35000000", "6", "elite", "#8b5cf6", "Tanlangan mijozlar uchun 6% coin."),
    ("legend", "Legend", "35000000", "50000000", "7", "legend", "#ef4444", "Afsonaviy xaridorlar uchun 7% coin."),
    ("vip", "VIP", "50000000", None, "8", "vip", "#f5c542", "Eng oliy daraja — har bir xariddan 8% coin."),
]


def forwards(apps, schema_editor):
    Tier = apps.get_model("loyalty", "LoyaltyTier")
    for slug, name, lo, hi, pct, icon, color, desc in LADDER:
        Tier.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "min_spend": D(lo), "max_spend": D(hi) if hi else None, "percent": D(pct), "icon": icon, "color": color, "description": desc, "is_active": True},
        )


def backwards(apps, schema_editor):
    apps.get_model("loyalty", "LoyaltyTier").objects.filter(slug__in=["gold", "platinum", "elite", "legend"]).delete()


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0003_tier_icons_eight")]
    operations = [migrations.RunPython(forwards, backwards)]
