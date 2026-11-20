"""
Product questions ("Savol-javob") -- ask on the product page, answer in Dashboard → Sharhlar → Savollar.

ask()        a signed-in customer's question (pending until answered; 5 open questions per customer per day)
answer()     the store's answer -- publishes the question and tells the asker once
public()     answered, visible questions of a product, newest first
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.reviews.infrastructure.models import ProductQuestionModel

QUESTION_MIN, QUESTION_MAX, ANSWER_MAX = 8, 600, 1500
DAILY_LIMIT = 5


class QuestionError(ValueError):
    pass


def _display_name(customer_id) -> str:
    from apps.identity.infrastructure.models import User

    u = User._base_manager.filter(id=customer_id).first()
    if u is None:
        return ""
    parts = (getattr(u, "full_name", "") or "").split()  # "Ali Valiyev" -> "Ali V." -- never a phone number
    if not parts:
        return ""
    return (f"{parts[0]} {parts[1][:1]}." if len(parts) > 1 else parts[0])[:80]


def ask(product_id, customer_id, text: str) -> ProductQuestionModel:
    text = " ".join((text or "").split())
    if len(text) < QUESTION_MIN:
        raise QuestionError(f"Savol kamida {QUESTION_MIN} belgidan iborat bo'lsin.")
    if len(text) > QUESTION_MAX:
        raise QuestionError(f"Savol {QUESTION_MAX} belgidan oshmasin.")
    since = timezone.now() - dt.timedelta(days=1)
    if ProductQuestionModel.objects.filter(customer_id=customer_id, created_at__gte=since).count() >= DAILY_LIMIT:
        raise QuestionError("Bugun juda ko'p savol yuborildi. Ertaga yana urinib ko'ring.")
    if ProductQuestionModel.objects.filter(customer_id=customer_id, product_id=product_id, question=text).exists():
        raise QuestionError("Bu savol allaqachon yuborilgan.")
    return ProductQuestionModel.objects.create(product_id=product_id, customer_id=customer_id, question=text, author_name=_display_name(customer_id))


def answer(question_id, text: str, actor: str = "") -> str:
    """Writes / edits the answer. Returns "added" | "edited" | "removed" | "same"."""
    text = "\n".join(line.rstrip() for line in (text or "").strip().splitlines()).strip()
    if len(text) > ANSWER_MAX:
        raise QuestionError(f"Javob {ANSWER_MAX} belgidan oshmasin (hozir {len(text)}).")
    with transaction.atomic():
        q = ProductQuestionModel.objects.select_for_update().get(pk=question_id)
        before = q.answer
        if text == before:
            return "same"
        q.answer = text
        q.answered_at = timezone.now() if text else None
        q.answered_by = (actor or "")[:150] if text else ""
        if q.status != "hidden":
            q.status = "answered" if text else "pending"
        q.save(update_fields=["answer", "answered_at", "answered_by", "status"])
        if not text:
            return "removed"
        if not before and q.status == "answered":
            _notify(q, text)
        return "edited" if before else "added"


def set_hidden(question_id, hidden: bool) -> None:
    q = ProductQuestionModel.objects.get(pk=question_id)
    q.status = "hidden" if hidden else ("answered" if q.answer else "pending")
    q.save(update_fields=["status"])


def public(product_id, limit: int = 20) -> tuple[list[dict], int]:
    qs = ProductQuestionModel.objects.filter(product_id=product_id, status="answered").exclude(answer="")
    total = qs.count()
    rows = [{
        "id": str(q.id), "question": q.question, "answer": q.answer, "author": q.author_name or "",
        "asked_at": q.created_at.isoformat(), "answered_at": q.answered_at.isoformat() if q.answered_at else None,
    } for q in qs.order_by("-answered_at")[:limit]]
    return rows, total


def mine(product_id, customer_id) -> list[dict]:
    """The asker's own still-unanswered questions, so they see theirs is waiting."""
    return [{"id": str(q.id), "question": q.question, "asked_at": q.created_at.isoformat()}
            for q in ProductQuestionModel.objects.filter(product_id=product_id, customer_id=customer_id, status="pending").order_by("-created_at")[:5]]


def _notify(q: ProductQuestionModel, text: str) -> None:
    from apps.notifications.infrastructure.notify import notify
    from apps.products.infrastructure.models import ProductTranslation

    names, slug = {}, ""
    for locale, name, sl in ProductTranslation.objects.filter(product_id=q.product_id).values_list("locale_code", "name", "slug"):
        names[locale] = name
        if sl and (locale == "uz" or not slug):
            slug = sl
    fallback = names.get("uz") or next(iter(names.values()), "mahsulot")
    short = text if len(text) <= 160 else text[:157].rstrip() + "…"
    i18n = {lang: {"product": names.get(lang) or fallback} for lang in ("uz", "ru", "en")}
    notify(q.customer_id, "question_answered", {"product": fallback, "reply": short, "i18n": i18n},
           link=f"/products/{slug}#questions" if slug else "", dedupe_key=f"question_answered:{q.pk}")
