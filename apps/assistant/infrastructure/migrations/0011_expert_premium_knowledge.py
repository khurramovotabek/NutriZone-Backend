"""
Teaches the advisor what the first expert set left out (17 entries, uz / ru / en): glutamine, HMB, ashwagandha, CoQ10,
endurance fuelling, reading a label, protein myths, steroids / SARMs, vitamins A / E / K2, iodine, folic acid,
high-dose antioxidants, which blood tests to take, "detox". Entries the shop already has (same title) are left as they
are; the shop edits or switches them off on the dashboard (AI bilimlar bazasi).
"""
from django.db import migrations

from . import _expert_premium

TITLES = {  # title_ru, title_en
    "Glutamin kerakmi": ("Нужен ли глютамин", "Is glutamine worth it"),
    "HMB nima": ("Что такое HMB", "What is HMB"),
    "Ashvagandha: stress, uyqu va kuch": ("Ашваганда: стресс, сон и сила", "Ashwagandha: stress, sleep and strength"),
    "Yugurish, futbol va uzoq mashg'ulotda ovqatlanish": ("Питание для бега, футбола и долгих тренировок", "Fuelling running, football and long sessions"),
    "Yorliqni o'qish va porsiya narxi": ("Как читать этикетку и считать цену порции", "Reading a label and price per serving"),
    "Protein ovqat o'rnini bosadimi": ("Может ли протеин заменить еду", "Can a protein shake replace a meal"),
    "Anabolik oyna: proteinni darhol ichish shartmi": ("Анаболическое окно: нужно ли пить протеин сразу", "The anabolic window: do you need protein right away"),
    "Bir martada qancha oqsil so'riladi": ("Сколько белка усваивается за раз", "How much protein you can absorb at once"),
    "Steroidlar va SARM xavfi": ("Стероиды и SARM: риски", "Steroids and SARMs: the risks"),
    "A va E vitaminlari: ortiqchasi zararli": ("Витамины A и E: избыток вреден", "Vitamins A and E: too much is harmful"),
    "K2 vitamini va D3 bilan birga": ("Витамин K2 и D3 вместе", "Vitamin K2 together with D3"),
    "Yod va qalqonsimon bez": ("Йод и щитовидная железа", "Iodine and the thyroid"),
    "Foliy kislotasi va homiladorlikni rejalashtirish": ("Фолиевая кислота и планирование беременности", "Folic acid and planning a pregnancy"),
    "Koenzim Q10": ("Коэнзим Q10", "Coenzyme Q10"),
    "Katta dozali antioksidantlar va mashg'ulot": ("Большие дозы антиоксидантов и тренировки", "High-dose antioxidants and training"),
    "Qaysi tahlillarni topshirish kerak": ("Какие анализы сдать", "Which blood tests to take"),
    "Detoks va «organizmni tozalash» afsonasi": ("Детокс и миф об «очищении организма»", "Detox and the 'cleanse' myth"),
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_premium.E:
        title_ru, title_en = TITLES[title]
        e, created = KnowledgeEntry.objects.get_or_create(title=title, defaults={
            "topic": topic, "priority": priority, "questions": questions, "keywords": keywords, "title_ru": title_ru, "title_en": title_en,
            "answer_uz": uz, "answer_ru": ru, "answer_en": en, "created_by": "NutriZone"})
        if created:  # the historical model has no custom save(): give it the readable address the live model would
            import re

            base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"[ʻʼ‘’`´'«»]", "", title.lower())).strip("-")[:80] or "maslahat"
            slug, n = base, 2
            while KnowledgeEntry.objects.filter(slug=slug).exclude(pk=e.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            KnowledgeEntry.objects.filter(pk=e.pk).update(slug=slug)


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_premium.E], created_by="NutriZone", uses=0).delete()


class Migration(migrations.Migration):
    dependencies = [("assistant", "0010_teach_creatine_mixing")]
    operations = [migrations.RunPython(seed, unseed)]
