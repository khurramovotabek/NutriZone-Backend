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
    # everyday verbs and time words that matched unrelated entries ("ob-havo qanday bo'ladi" -> a protein answer)
    "boladi", "boladimi", "bolsa", "bolyapti", "bugun", "ertaga", "hozir", "qiladi", "qilsa", "будет", "сегодня", "завтра", "will", "today", "tomorrow",
}
MIN_SCORE = 3.0


# "D vitamini", "vitamin D3", "витамин Д", "b12" → one token ("vitd", "vitb12"), so a question about vitamin D doesn't
# rank as a question about vitamins in general (single letters are otherwise dropped as noise)
_VIT_NAME = r"(?:vitamin\w*|витамин\w*)"
_VIT_LETTER = r"([abcdekавсдек])\s*-?\s*(\d{0,2})"
_VIT_AFTER = re.compile(_VIT_NAME + r"\s*-?\s*" + _VIT_LETTER + r"(?![a-zа-я0-9])")
_VIT_BEFORE = re.compile(r"(?<![a-zа-я0-9])" + _VIT_LETTER + r"\s*-?\s*" + _VIT_NAME)
_VIT_BARE = re.compile(r"(?<![a-zа-я0-9])(d3|k2|b12|b6|b9|b1|b2|b3|b5|b7|д3|в12|в6)(?![a-zа-я0-9])")
_CYR_LETTER = str.maketrans({"а": "a", "в": "b", "с": "c", "д": "d", "е": "e", "к": "k"})


def _vit_token(letter: str, digits: str) -> str:
    letter = letter.translate(_CYR_LETTER)
    return f" vit{letter}{digits if letter == 'b' else ''} "  # D3 = D, K2 = K; B vitamins differ by number


def _norm(text: str) -> str:
    t = _APOS.sub("", (text or "").lower().replace("ё", "е"))
    t = _VIT_AFTER.sub(lambda m: _vit_token(m.group(1), m.group(2)), t)
    t = _VIT_BEFORE.sub(lambda m: _vit_token(m.group(1), m.group(2)), t)
    return _VIT_BARE.sub(lambda m: _vit_token(m.group(1)[0], m.group(1)[1:]), t)


def _stems(text: str) -> set:
    return {w[:6] if w.startswith("vit") and len(w) <= 6 else w[:5] for w in _WORD.findall(_norm(text)) if w not in STOP and len(w) > 1}


@dataclass
class Hit:
    entry: object
    score: float
    exact: bool = False  # the customer asked one of the entry's own question forms (whole, or nearly)


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
        exact = bool(qn) and any(qn == x or (len(x) > 8 and x in qn and len(x) >= 0.6 * len(qn)) for x in questions)
        if exact:
            score += 10  # the customer asked (almost) exactly one of the listed questions
        score += 2.5 * len(q & set().union(*(_stems(x) for x in questions))) if questions else 0
        score += 3.0 * len(q & _stems(e.keywords.replace(",", " ")))
        score += 1.5 * len(q & _stems(e.title))
        score += 0.4 * len(q & _stems(" ".join((e.answer_uz, e.answer_ru, e.answer_en))))
        if score >= min_score:
            hits.append(Hit(e, score + e.priority / 100, exact))
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]


def mark_used(entries) -> None:
    from apps.assistant.infrastructure.models import KnowledgeEntry

    ids = [e.pk for e in entries]
    if ids:
        KnowledgeEntry.objects.filter(pk__in=ids).update(uses=F("uses") + 1)
