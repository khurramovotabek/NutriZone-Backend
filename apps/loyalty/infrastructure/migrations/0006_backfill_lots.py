"""
Turns pre-existing ledger rows into lots: every credit gets `remaining` and a
365-day `expires_at` from its own creation time, then every historical debit
is replayed first-to-expire-first so Σ remaining == Wallet.balance holds from
day one. Also creates the settings singleton with its defaults.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import migrations

CREDIT = {"earn", "referral", "refund", "adjustment"}


def forwards(apps, schema_editor):
    Wallet = apps.get_model("loyalty", "Wallet")
    Tx = apps.get_model("loyalty", "WalletTransaction")
    Settings = apps.get_model("loyalty", "LoyaltySettings")
    Settings.objects.get_or_create(pk=1)

    for wallet in Wallet.objects.all():
        rows = list(Tx.objects.filter(wallet=wallet).order_by("created_at"))
        lots = []
        for row in rows:
            if row.amount > 0 and row.kind in CREDIT:
                row.remaining = row.amount
                row.expires_at = row.created_at + timedelta(days=365)
                lots.append(row)
            else:
                need = -row.amount
                allocations = []
                for lot in sorted(lots, key=lambda r: (r.expires_at, r.created_at)):
                    if need <= 0:
                        break
                    take = min(lot.remaining, need)
                    if take:
                        lot.remaining -= take
                        need -= take
                        allocations.append({"lot": str(lot.id), "amount": take})
                row.allocations = allocations
        for row in rows:
            row.save(update_fields=["remaining", "expires_at", "allocations"])
        wallet.balance = sum(lot.remaining for lot in lots)
        wallet.save(update_fields=["balance"])


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0005_lots_settings_referrals")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
