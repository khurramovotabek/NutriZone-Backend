"""The shop channel's daily schedule gets a «💡 Kun maslahati» slot at 12:30: one AI knowledge-base topic a day, with a
matching in-stock product (daily_posts.pick_tip / build_tip_post)."""
from __future__ import annotations

import datetime

from django.db import migrations, models


def forwards(apps, schema_editor):
    Settings = apps.get_model("telegram_bot", "ChannelAutoPostSettings")
    Slot = apps.get_model("telegram_bot", "ChannelPostSlot")
    row, _ = Settings.objects.get_or_create(pk=1)
    if not Slot.objects.filter(kind="tip").exists():
        Slot.objects.create(settings=row, time=datetime.time(12, 30), kind="tip", heading="💡 Kun maslahati")


def backwards(apps, schema_editor):
    apps.get_model("telegram_bot", "ChannelPostSlot").objects.filter(kind="tip").delete()


class Migration(migrations.Migration):
    dependencies = [("telegram_bot", "0016_channel_schedule_name")]
    operations = [
        migrations.AlterField(
            model_name="channelpostslot", name="kind",
            field=models.CharField("Nima post qilinadi", max_length=8, default="top", choices=[
                ("top", "Kun mahsuloti (eng ko'p sotilgan / yuqori baho)"), ("sale", "Chegirmadagi mahsulot"), ("new", "Yangi kelgan mahsulot"),
                ("pick", "Tasodifiy tavsiya"), ("tip", "Kun maslahati (AI bilimlar bazasidan + mos mahsulot)")]),
        ),
        migrations.RunPython(forwards, backwards),
    ]
