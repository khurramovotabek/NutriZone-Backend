"""
Teaches the replay gaps: review coins per order, stomach trouble, protein in food, calories, evening eating, meal count,
combat/team sports, results timeline, stacking, returns -- plus extra phrasings for existing entries.
"""
import re

from django.db import migrations

from . import _expert_more

TITLES = _expert_more.TITLES


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_more.E:
        title_ru, title_en = TITLES[title]
        e, created = KnowledgeEntry.objects.get_or_create(title=title, defaults={
            "topic": topic, "priority": priority, "questions": questions, "keywords": keywords, "title_ru": title_ru, "title_en": title_en,
            "answer_uz": uz, "answer_ru": ru, "answer_en": en, "created_by": "NutriZone"})
        if created:
            base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"[ʻʼ‘’`´'«»]", "", title.lower())).strip("-")[:80] or "maslahat"
            slug, n = base, 2
            while KnowledgeEntry.objects.filter(slug=slug).exclude(pk=e.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            KnowledgeEntry.objects.filter(pk=e.pk).update(slug=slug)
    for title, extra in _expert_more.QUESTIONS_ADD.items():
        for e in KnowledgeEntry.objects.filter(title=title):
            have = set((e.questions or "").split("\n"))
            add = [q for q in extra.split("\n") if q not in have]
            if add:
                KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join([*(e.questions or "").split("\n"), *add]).strip("\n"))


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_more.E], created_by="NutriZone", uses=0).delete()
    for title, extra in _expert_more.QUESTIONS_ADD.items():
        drop = set(extra.split("\n"))
        for e in KnowledgeEntry.objects.filter(title=title):
            KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join(q for q in (e.questions or "").split("\n") if q not in drop))


class Migration(migrations.Migration):
    dependencies = [("assistant", "0017_expert_app_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
