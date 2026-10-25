"""
The knowledge base as public guides (nutrizone.uz/guides): every active entry except time-limited promotions, in
uz / ru / en, with the catalogue search that shows matching products. Read-only and cached -- search engines and AI
answer engines crawl these pages, the shop edits the entries on the dashboard (AI bilimlar bazasi).
"""
from __future__ import annotations

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

PUBLIC_TOPICS = ("usage", "product", "faq", "policy")
TTL = 600
LOCALES = ("uz", "ru", "en")


def _entries():
    from apps.assistant.infrastructure.models import KnowledgeEntry

    today = timezone.localdate()
    return (KnowledgeEntry.objects.filter(is_active=True, topic__in=PUBLIC_TOPICS).exclude(slug="")
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today)).order_by("-priority", "title"))


def _product_query(entry) -> str:
    """The catalogue search for the product kind a guide is about ("D vitamini..." -> "vitamin d3"), or ""."""
    from apps.assistant.infrastructure.advisor import nlu, reco

    text = nlu.normalize(f"{entry.title} {entry.keywords}")
    kinds = nlu.concepts_in(f"{text} {text.translate(nlu.LATIN_FROM_CYR)}")
    return reco.QUERIES.get(kinds[0], kinds[0]) if kinds else ""


def _card(entry, locale: str) -> dict:
    answer = entry.answer(locale)
    first = answer.strip().split("\n", 1)[0]
    return {"slug": entry.slug, "topic": entry.topic, "title": entry.localized_title(locale), "summary": first[:240],
            "updated_at": entry.updated_at.isoformat()}


def listing(locale: str) -> list[dict]:
    locale = locale if locale in LOCALES else "uz"
    key = f"assistant:guides:list:{locale}"
    data = cache.get(key)
    if data is None:
        data = [_card(e, locale) for e in _entries()]
        cache.set(key, data, TTL)
    return data


def detail(slug: str, locale: str) -> dict | None:
    locale = locale if locale in LOCALES else "uz"
    key = f"assistant:guides:one:{locale}:{slug[:90]}"
    data = cache.get(key)
    if data is None:
        entry = _entries().filter(slug=slug).first()
        if entry is None:
            return None
        questions = [q.strip() for q in (entry.questions or "").splitlines() if q.strip()]
        related = [_card(e, locale) for e in _entries().filter(topic=entry.topic).exclude(pk=entry.pk)[:6]]
        data = {**_card(entry, locale), "answer": entry.answer(locale), "questions": questions[:12], "keywords": entry.keywords,
                "product_query": _product_query(entry), "related": related,
                "titles": {loc: entry.localized_title(loc) for loc in LOCALES}}
        cache.set(key, data, TTL)
    return data
