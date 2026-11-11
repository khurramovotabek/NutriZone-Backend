"""
Teaches the advisor to choose like a consultant (owner request 2026-11-11): lactose intolerance vs milk-protein allergy,
dairy-free protein, picking protein for a budget, what brand quality means, the price-of-25-g-protein maths, creatine
forms, gainer vs protein, concentrate / blend / isolate, protein vs creatine. Entries the shop already has (same title)
are left as they are.
"""
from django.db import migrations

from . import _expert_choice

TITLES = {  # title_ru, title_en
    "Laktoza ko'tarmaslik va protein": ("Непереносимость лактозы и протеин", "Lactose intolerance and protein"),
    "Sut oqsiliga allergiya va laktoza farqi": ("Аллергия на белок молока и лактоза", "Milk-protein allergy vs lactose"),
    "Sutsiz protein manbalari: vegan, mol go'shti, tuxum": ("Протеин без молока: веганский, говяжий, яичный", "Dairy-free protein: vegan, beef, egg"),
    "Byudjetga qarab protein tanlash": ("Как выбрать протеин под бюджет", "Choosing protein on a budget"),
    "Brend sifati: nimaga qarash kerak": ("Качество бренда: на что смотреть", "Brand quality: what matters"),
    "Proteinlarni solishtirish hisobi": ("Как сравнивать протеины по цене", "How to compare protein value"),
    "Kreatin turlari: monogidrat, HCl, Kre-Alkalyn": ("Виды креатина: моногидрат, HCl, Kre-Alkalyn", "Creatine types: monohydrate, HCl, Kre-Alkalyn"),
    "Geyner yoki protein: qaysi biri kerak": ("Гейнер или протеин: что нужно", "Gainer or protein: which one"),
    "Whey blend, konsentrat yoki izolyat: qaysi biri": ("Бленд, концентрат или изолят: что выбрать", "Blend, concentrate or isolate: which one"),
    "Protein va kreatin: har xil vazifa": ("Протеин и креатин: разные задачи", "Protein and creatine: different jobs"),
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_choice.E:
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
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_choice.E], created_by="NutriZone", uses=0).delete()


class Migration(migrations.Migration):
    dependencies = [("assistant", "0012_expert_faq_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
