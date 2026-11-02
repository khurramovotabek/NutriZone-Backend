"""
Teaching the free advisor: questions it answered badly are collected (AdvisorGap) and closed once the shop teaches them.

record() is called after a turn the advisor flagged (didn't understand, nothing found, kind out of stock) and on a 👎
vote; resolve() runs when a KnowledgeEntry is saved and closes every open gap that entry now answers.
"""
from __future__ import annotations

import logging
import re

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("nutrizone.assistant.gaps")
_APOS = re.compile(r"[ʻʼ‘’`´']")


def key_for(text: str) -> str:
    t = _APOS.sub("", (text or "").lower().replace("ё", "е"))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()[:200]


def record(text: str, locale: str, reason: str, answer: str = "") -> None:
    """Count one more occurrence of this question (best effort: never breaks the chat)."""
    from apps.assistant.infrastructure.models import AdvisorGap

    key = key_for(text)
    if len(key) < 3:
        return
    try:
        updated = AdvisorGap.objects.filter(key=key).update(count=F("count") + 1, last_seen=timezone.now(), reason=reason, answer=answer[:2000], locale=locale)
        if not updated:
            AdvisorGap.objects.get_or_create(key=key, defaults={"text": text.strip()[:300], "locale": locale, "reason": reason, "answer": answer[:2000]})
        elif reason == "disliked":  # a 👎 on a question that had been taught reopens it -- the answer needs another look
            AdvisorGap.objects.filter(key=key, status="taught").update(status="open")
    except Exception:  # noqa: BLE001 - teaching data is a side channel
        logger.exception("advisor gap not recorded")


def resolve(entry) -> int:
    """Close the open gaps this knowledge entry now answers (its own question forms, or a strong match). Returns how many."""
    from apps.assistant.infrastructure import knowledge
    from apps.assistant.infrastructure.advisor.engine import STRONG_MATCH
    from apps.assistant.infrastructure.models import AdvisorGap

    if not entry.is_active:
        return 0
    closed = []
    for gap in AdvisorGap.objects.filter(status="open").order_by("-count")[:500].only("id", "text"):
        hits = knowledge.search(gap.text, limit=1)
        if hits and hits[0].entry.pk == entry.pk and (hits[0].exact or hits[0].score >= STRONG_MATCH):
            closed.append(gap.pk)
    if closed:
        AdvisorGap.objects.filter(pk__in=closed).update(status="taught", knowledge=entry)
    return len(closed)
