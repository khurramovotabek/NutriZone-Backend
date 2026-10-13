"""Seeds the support desk: the settings row, the starter quick replies, and the every-2-minutes unanswered-chat alert task."""
from __future__ import annotations

from django.db import migrations

TASK_NAME = "Chat: alert staff about unanswered chats"
QUICK = [
    ("Salomlashish", "Assalomu alaykum! NutriZone qo'llab-quvvatlash xizmati. Sizga qanday yordam bera olaman?"),
    ("Tekshiryapman", "Bir daqiqa, ma'lumotni tekshirib chiqaman."),
    ("Buyurtma raqami", "Buyurtma raqamingizni yozib yuborsangiz, holatini aytib beraman."),
    ("Buyurtma yo'lda", "Buyurtmangiz yo'lda, kuryer tez orada siz bilan bog'lanadi."),
    ("Mahsulot mavjud", "Bu mahsulot hozir mavjud. Saytdan buyurtma berishingiz mumkin."),
    ("Original", "Barcha mahsulotlarimiz 100% original va sertifikatlangan."),
    ("Xayrlashish", "Murojaatingiz uchun rahmat! Yana savollar bo'lsa, yozing."),
]


def forwards(apps, schema_editor):
    apps.get_model("chat", "ChatSettings").objects.get_or_create(pk=1)
    QuickReply = apps.get_model("chat", "ChatQuickReply")
    if not QuickReply.objects.exists():
        QuickReply.objects.bulk_create([QuickReply(title=t, text=x, sort_order=i) for i, (t, x) in enumerate(QUICK)])
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    every, _ = IntervalSchedule.objects.get_or_create(every=2, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={"task": "chat.alert_waiting", "interval": every, "crontab": None, "enabled": True, "description": "apps/chat/infrastructure/automation.py::alert_waiting"},
    )


def backwards(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("chat", "0005_support_desk"), ("django_celery_beat", "0019_alter_periodictasks_options")]
    operations = [migrations.RunPython(forwards, backwards)]
