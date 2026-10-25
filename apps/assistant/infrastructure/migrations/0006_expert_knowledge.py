"""
Teaches the assistant as a sports-nutrition and vitamin expert: ~50 knowledge entries in uz / ru / en (vitamins and
minerals, supplement types and myths, calories, meal timing, recovery, women, 50+, teens, Ramadan, anti-doping).
Doses follow ISSN position stands and NIH ODS / EFSA reference intakes and upper limits. Entries the shop already has
(same title) are left as they are; the shop edits or switches them off on the dashboard (AI bilimlar bazasi).
"""
from django.db import migrations

from . import _expert_nutrition, _expert_supplements, _expert_vitamins

ENTRIES = _expert_vitamins.E + _expert_supplements.E + _expert_nutrition.E


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in ENTRIES:
        KnowledgeEntry.objects.get_or_create(title=title, defaults={"topic": topic, "priority": priority, "questions": questions, "keywords": keywords,
                                                                    "answer_uz": uz, "answer_ru": ru, "answer_en": en, "created_by": "NutriZone"})


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in ENTRIES], created_by="NutriZone", uses=0).delete()


class Migration(migrations.Migration):
    dependencies = [("assistant", "0005_bcaa_answer")]
    operations = [migrations.RunPython(seed, unseed)]
