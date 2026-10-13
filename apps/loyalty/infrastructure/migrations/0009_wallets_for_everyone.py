from django.db import migrations


def wallets_for_everyone(apps, schema_editor):
    """Loyalty Management lists every customer with their tier and coins -- give each existing account its (empty) wallet."""
    User = apps.get_model("identity", "User")
    Wallet = apps.get_model("loyalty", "Wallet")
    users = User.objects.all()
    if any(f.name == "is_deleted" for f in User._meta.get_fields()):
        users = users.filter(is_deleted=False)
    have = set(Wallet.objects.values_list("user_id", flat=True))
    Wallet.objects.bulk_create([Wallet(user_id=uid) for uid in users.values_list("id", flat=True) if uid not in have], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("loyalty", "0008_tier_override_history_actor"),
        ("identity", "__first__"),
    ]

    operations = [migrations.RunPython(wallets_for_everyone, migrations.RunPython.noop)]
