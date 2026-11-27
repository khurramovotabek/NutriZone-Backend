"""
Teaches the 150-question replay gaps: "what is X" for the main kinds, fakes, changing an order, coupon codes, wholesale/jobs,
sold-out products, energy drinks, coffee, smoking, liver, acne, constipation, stress, memory, eyes, height, men/women,
abs, training basics, cardio vs weights, sugar, carbs, breakfast -- plus extra phrasings for existing entries.
"""
import re

from django.db import migrations

from . import _expert_pro

TITLES = _expert_pro.TITLES


def seed(apps, schema_editor):  # noqa: C901 - one plain loop per kind of change
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_pro.E:
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
    for title, extra in _expert_pro.QUESTIONS_ADD.items():
        for e in KnowledgeEntry.objects.filter(title=title):
            have = set((e.questions or "").split("\n"))
            add = [q for q in extra.split("\n") if q not in have]
            if add:
                KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join([*(e.questions or "").split("\n"), *add]).strip("\n"))

    for title, words in {**_expert_pro.KEYWORDS_SET, **{e[2]: e[4] for e in _expert_pro.E}}.items():
        KnowledgeEntry.objects.filter(title=title, created_by="NutriZone").update(keywords=words)
    for old, new in _expert_pro.SUPERSEDES.items():
        keep = KnowledgeEntry.objects.filter(title=new).first()
        for e in KnowledgeEntry.objects.filter(title=old, created_by="NutriZone", is_active=True):
            if keep:
                have = (keep.questions or "").split("\n")
                add = [q for q in (e.questions or "").split("\n") if q and q not in have]
                if add:
                    keep.questions = "\n".join([*have, *add]).strip("\n")
                    KnowledgeEntry.objects.filter(pk=keep.pk).update(questions=keep.questions)
            KnowledgeEntry.objects.filter(pk=e.pk).update(is_active=False)


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=list(_expert_pro.SUPERSEDES), created_by="NutriZone").update(is_active=True)
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_pro.E], created_by="NutriZone", uses=0).delete()
    for title, extra in _expert_pro.QUESTIONS_ADD.items():
        drop = set(extra.split("\n"))
        for e in KnowledgeEntry.objects.filter(title=title):
            KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join(q for q in (e.questions or "").split("\n") if q not in drop))


class Migration(migrations.Migration):
    dependencies = [("assistant", "0018_expert_more_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
