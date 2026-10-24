"""
AI bilimlar bazasi search: ranks KnowledgeEntry rows for a customer question in any of uz / ru / en. Light stemming
(Uzbek and Russian words carry long suffixes: "kreatinni", "креатина") -- word prefixes of 5 letters match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import F, Q
from django.utils import timezone

_APOS = re.compile(r"[ʻʼ‘’`´']")
_WORD = re.compile(r"[0-9a-zа-яёўқғҳ]+")
STOP = {
    "va", "bilan", "uchun", "qanday", "nima", "qancha", "bormi", "men", "menga", "siz", "sizda", "bu", "u", "ham", "yoki", "edi", "kerak", "mumkin",
    "и", "в", "на", "как", "что", "сколько", "есть", "у", "вас", "мне", "я", "для", "с", "по", "ли", "а", "не",
    "the", "a", "an", "is", "are", "do", "you", "how", "what", "for", "to", "of", "and", "i", "me", "my", "can", "it", "in", "on",
}
MIN_SCORE = 3.0


def _norm(text: str) -> str:
    return _APOS.sub("", (text or "").lower().replace("ё", "е"))


def _stems(text: str) -> set:
    return {w[:5] for w in _WORD.findall(_norm(text)) if w not in STOP and len(w) > 1}


@dataclass
class Hit:
    entry: object
    score: float


def search(query: str, limit: int = 3, min_score: float = MIN_SCORE) -> list[Hit]:
    from apps.assistant.infrastructure.models import KnowledgeEntry

    q = _stems(query)
    if not q:
        return []
    today = timezone.localdate()
    hits = []
    qn = _norm(query).strip(" ?!.")
    for e in KnowledgeEntry.objects.filter(is_active=True).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today)):
        questions = [_norm(x).strip(" ?!.") for x in (e.questions or "").splitlines() if x.strip()]
        score = 0.0
        if qn and any(qn == x or (len(x) > 8 and x in qn) for x in questions):
            score += 10  # the customer asked (almost) exactly one of the listed questions
        score += 2.5 * len(q & set().union(*(_stems(x) for x in questions))) if questions else 0
        score += 3.0 * len(q & _stems(e.keywords.replace(",", " ")))
        score += 1.5 * len(q & _stems(e.title))
        score += 0.4 * len(q & _stems(" ".join((e.answer_uz, e.answer_ru, e.answer_en))))
        if score >= min_score:
            hits.append(Hit(e, score + e.priority / 100))
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]


def mark_used(entries) -> None:
    from apps.assistant.infrastructure.models import KnowledgeEntry

    ids = [e.pk for e in entries]
    if ids:
        KnowledgeEntry.objects.filter(pk__in=ids).update(uses=F("uses") + 1)
