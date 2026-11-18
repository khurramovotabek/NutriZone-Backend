"""
Teaches the advisor daily timing (owner request 2026-11-18): an empty stomach, timetables for mass and for fat loss,
what not to combine, a beginner's first month; and adds the ways customers actually phrased existing questions.
New entries already present (same title) are left alone; extra questions are only appended, never replacing text.
"""
import re

from django.db import migrations

from . import _expert_schedule

TITLES = {
    "Och qoringa nima ichsa bo'ladi": ("Что можно пить натощак", "What to take on an empty stomach"),
    "Kunlik qabul jadvali: massa uchun": ("График приёма: на массу", "Daily schedule: bulking"),
    "Kunlik qabul jadvali: ozish uchun": ("График приёма: похудение", "Daily schedule: fat loss"),
    "Qaysi qo'shimchalarni birga ichib bo'lmaydi": ("Какие добавки нельзя сочетать", "Supplements not to take together"),
    "Birinchi oy: yangi boshlovchi qanday ichadi": ("Первый месяц: как принимать новичку", "First month: how a beginner starts"),
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_schedule.E:
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
    for title, extra in _expert_schedule.QUESTIONS_ADD.items():
        for e in KnowledgeEntry.objects.filter(title=title):
            have = set((e.questions or "").split("\n"))
            add = [q for q in extra.split("\n") if q not in have]
            if add:
                KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join([*(e.questions or "").split("\n"), *add]).strip("\n"))


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in _expert_schedule.E], created_by="NutriZone", uses=0).delete()
    for title, extra in _expert_schedule.QUESTIONS_ADD.items():
        drop = set(extra.split("\n"))
        for e in KnowledgeEntry.objects.filter(title=title):
            KnowledgeEntry.objects.filter(pk=e.pk).update(questions="\n".join(q for q in (e.questions or "").split("\n") if q not in drop))


class Migration(migrations.Migration):
    dependencies = [("assistant", "0014_expert_practice_knowledge")]
    operations = [migrations.RunPython(seed, unseed)]
