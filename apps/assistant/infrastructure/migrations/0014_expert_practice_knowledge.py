"""
Teaches the advisor practical everyday answers (owner request 2026-11-11): a mass-gain stack and a fat-loss stack in
order of importance, how long a tub lasts and its monthly cost, protein recipes, lumps and foam, L-carnitine forms,
choosing a flavour. Entries the shop already has (same title) are left as they are.
"""
from django.db import migrations

from . import _expert_practice

TITLES = {  # title_ru, title_en
    "Massa olish uchun to'plam: nimadan boshlash": ("Набор для массы: с чего начать", "Mass-gain stack: where to start"),
    "Ozish (quritish) uchun to'plam": ("Набор для похудения (сушки)", "Fat-loss (cutting) stack"),
    "Bir banka qancha vaqtga yetadi va oyiga qancha turadi": ("На сколько хватает банки и сколько это в месяц", "How long a tub lasts and the monthly cost"),
    "Protein bilan retseptlar": ("Рецепты с протеином", "Protein recipes"),
    "Proteinni aralashtirish: kesak va ko'pik": ("Как размешать протеин: комки и пена", "Mixing protein: lumps and foam"),
    "L-karnitin turlari: tartrat, ALCAR, suyuq": ("Виды L-карнитина: тартрат, ALCAR, жидкий", "L-carnitine types: tartrate, ALCAR, liquid"),
    "Ta'm tanlash va ta'msiz protein": ("Как выбрать вкус и протеин без вкуса", "Choosing a flavour and unflavoured protein"),
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_practice.E:
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
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_practice.E], created_by="NutriZone", uses=0).delete()


class Migration(migrations.Migration):
    dependencies = [("assistant", "0013_expert_choice_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
