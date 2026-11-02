"""
The advisor's own teaching data, like the shop's: "Kreatin qanday ichiladi" also answers what to mix creatine with and
the daily amount asked in other words ("kreatin suv yoki sut bilan", "how much creatine per day") -- these went to the
protein entries before. Only the untouched seed entry is updated; an entry the shop edited stays theirs.
"""
from django.db import migrations

TITLE = "Kreatin qanday ichiladi"
OLD_QUESTIONS = "kreatin qanday ichiladi\nkreatin dozasi\nкак пить креатин\nдозировка креатина\nhow to take creatine"
NEW_QUESTIONS = OLD_QUESTIONS + (
    "\nkreatin kuniga qancha\nkreatinni nima bilan ichish kerak\nkreatin suv yoki sut bilan\nkreatinni sut bilan ichsa bo'ladimi"
    "\nсколько креатина в день\nкреатин с водой или молоком\nhow much creatine per day\ncreatine with milk or water"
)
OLD_UZ = ("Kreatin monohidrat: kuniga 3–5 g, har kuni (mashg'ulotsiz kunlari ham), istalgan vaqtda — suv yoki sharbat bilan. Tezroq to'yinish uchun 5–7 kun kuniga ~20 g (4×5 g) "
          "«yuklama» qilish mumkin, lekin shart emas. Ko'proq suv iching. Buyrak kasalligi bo'lsa — avval shifokor bilan maslahatlashing.")
MIX = {
    "answer_uz": " Nima bilan ichish farqi yo'q: suv, sharbat, sut yoki protein kokteyli — kreatin baribir so'riladi. Sut yoki shirin sharbat qo'shimcha kaloriya beradi (massa uchun qulay), suv — kaloriyasiz (ozishda).",
    "answer_ru": " С чем пить — неважно: вода, сок, молоко или протеиновый коктейль, креатин усвоится. Молоко и сладкий сок добавят калорий (удобно на массе), вода — без калорий (на похудении).",
    "answer_en": " What you mix it with doesn't matter: water, juice, milk or your protein shake all work. Milk or sweet juice add calories (handy when bulking), water adds none (when cutting).",
}


def teach(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    e = KnowledgeEntry.objects.filter(title=TITLE, questions=OLD_QUESTIONS, answer_uz=OLD_UZ).first()
    if e is None:
        return
    e.questions = NEW_QUESTIONS
    for field, extra in MIX.items():
        setattr(e, field, getattr(e, field) + extra)
    e.save(update_fields=["questions", *MIX])


def untaught(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    e = KnowledgeEntry.objects.filter(title=TITLE, questions=NEW_QUESTIONS).first()
    if e is None:
        return
    e.questions = OLD_QUESTIONS
    for field, extra in MIX.items():
        setattr(e, field, getattr(e, field).removesuffix(extra))
    e.save(update_fields=["questions", *MIX])


class Migration(migrations.Migration):
    dependencies = [("assistant", "0009_advisor_gaps")]
    operations = [migrations.RunPython(teach, untaught)]
