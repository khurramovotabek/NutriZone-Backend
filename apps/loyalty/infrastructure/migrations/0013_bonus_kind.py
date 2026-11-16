"""Gift coins (opening campaign) get their own ledger kind instead of "manual adjustment"; existing gift rows move over."""
from django.db import migrations, models


def forwards(apps, schema_editor):
    tx = apps.get_model("loyalty", "WalletTransaction")
    tx.objects.filter(kind="adjustment", note__startswith="Sign-up gift").update(kind="bonus")
    tx.objects.filter(kind="adjustment", note__startswith="Birinchi buyurtma sovg'asi").update(kind="bonus")


def backwards(apps, schema_editor):
    apps.get_model("loyalty", "WalletTransaction").objects.filter(kind="bonus").update(kind="adjustment")


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0012_signup_bonus")]

    operations = [
        migrations.AlterField(
            model_name="wallettransaction", name="kind",
            field=models.CharField(choices=[("earn", "Earned (order cashback)"), ("referral", "Referral bonus"), ("refund", "Refund (order with coin payment cancelled)"), ("adjustment", "Manual adjustment"), ("bonus", "Gift (campaign)"), ("spend", "Spent at checkout"), ("reversal", "Reversed (order cancelled/returned)"), ("expiry", "Expired")], db_index=True, max_length=16),
        ),
        migrations.RunPython(forwards, backwards),
    ]
