"""
Teaches the gaps found by replaying every real question (2026-11-20): belly fat, can't gain weight, how fast muscle
grows, water with creatine, supplements next to medicines; plus the wordings customers really used. Existing titles
are left alone; extra questions are only appended.
"""
import re

from django.db import migrations

from . import _expert_gaps

TITLES = {
    "Qorin yog'ini yo'qotish": ("Как убрать жир с живота", "Losing belly fat"),
    "Ko'p yeyman, lekin semirmayman": ("Много ем, но не набираю вес", "I eat a lot but can't gain"),
    "Bir oyda qancha mushak qo'shish mumkin": ("Сколько мышц можно набрать за месяц", "How much muscle you can gain in a month"),
    "Kreatin bilan qancha suv ichish kerak": ("Сколько воды пить с креатином", "How much water with creatine"),
    "Dori ichayotganda qo'shimchalar": ("Добавки при приёме лекарств", "Supplements and medication"),
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_gaps.E:
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
    for title, extra in _expert_gaps.QUESTIONS_ADD.items():
        for e in KnowledgeEntry.objects.filter(title=title):
            have = set((e.questions or "").split("\n"))
            add = [q for q in extra.split("\n") if q not in have]
            if add:
                KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join([*(e.questions or "").split("\n"), *add]).strip("\n"))


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_gaps.E], created_by="NutriZone", uses=0).delete()
    for title, extra in _expert_gaps.QUESTIONS_ADD.items():
        drop = set(extra.split("\n"))
        for e in KnowledgeEntry.objects.filter(title=title):
            KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join(q for q in (e.questions or "").split("\n") if q not in drop))


class Migration(migrations.Migration):
    dependencies = [("assistant", "0015_expert_schedule_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
