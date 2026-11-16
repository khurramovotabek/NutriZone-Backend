"""0013 matched gift rows by note text, but the first gifts were written as "Ro'yxatdan o'tish sovg'asi · №N".
Use the campaign table's own link instead: every SignupBonusGrant.transaction is a gift row."""
from django.db import migrations


def forwards(apps, schema_editor):
    grant = apps.get_model("loyalty", "SignupBonusGrant")
    tx = apps.get_model("loyalty", "WalletTransaction")
    ids = list(grant.objects.exclude(transaction_id=None).values_list("transaction_id", flat=True))
    tx.objects.filter(id__in=ids, kind="adjustment").update(kind="bonus")


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0013_bonus_kind")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
