"""
Teaches the advisor six everyday shopper questions it answered off-topic (2026-11-11 live probe): storing an opened tub,
creatine with coffee, whether a gainer / protein makes you fat, protein on rest days, paying in instalments.
Entries the shop already has (same title) are left as they are.
"""
from django.db import migrations

from . import _expert_faq

TITLES = {  # title_ru, title_en
    "Ochilgan qadoqni saqlash va yaroqlilik muddati": ("Хранение открытой упаковки и срок годности", "Storing an opened tub and expiry"),
    "Kreatinni kofe bilan ichish": ("Креатин с кофе", "Creatine with coffee"),
    "Gainer semirtiradimi": ("Толстит ли гейнер", "Does a gainer make you fat"),
    "Mashg'ulotsiz kunlarda protein": ("Протеин в дни отдыха", "Protein on rest days"),
    "Proteindan semirib ketish mumkinmi": ("Можно ли потолстеть от протеина", "Can protein make you fat"),
    "Bo'lib to'lash (nasiya)": ("Рассрочка", "Paying in instalments"),
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_faq.E:
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
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_faq.E], created_by="NutriZone", uses=0).delete()


class Migration(migrations.Migration):
    dependencies = [("assistant", "0011_expert_premium_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
