"""Recording and reading search terms (apps/search/infrastructure/models.py::SearchTerm)."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("nutrizone.app")

MIN_LEN, MAX_LEN = 2, 120
POPULAR_CACHE_KEY = "search:popular:v1"
POPULAR_TTL = 600
POPULAR_WINDOW_DAYS = 30


def record(raw_query: str, results: int, locale: str = "") -> None:
    """Count one submitted search. Never raises -- analytics must not break search."""
    from apps.products.infrastructure.smart_search import normalize
    from apps.search.infrastructure.models import SearchTerm

    display = " ".join((raw_query or "").split())[:MAX_LEN]
    term = normalize(display)[:MAX_LEN]
    if len(term) < MIN_LEN:
        return
    now = timezone.now()
    zero = 1 if results == 0 else 0
    try:
        updated = SearchTerm.objects.filter(term=term).update(
            searches=F("searches") + 1, zero_results=F("zero_results") + zero, last_results=results, display=display, last_locale=locale, last_seen=now,
        )
        if not updated:
            try:
                with transaction.atomic():
                    SearchTerm.objects.create(term=term, display=display, searches=1, zero_results=zero, last_results=results, last_locale=locale, last_seen=now)
            except IntegrityError:  # a concurrent first search of the same term won the insert
                SearchTerm.objects.filter(term=term).update(searches=F("searches") + 1, zero_results=F("zero_results") + zero, last_results=results, last_seen=now)
    except Exception:  # noqa: BLE001
        logger.exception("Could not record search term")


def popular(limit: int = 8) -> list[str]:
    """Most searched terms of the last 30 days that currently find products -- the storefront's suggestion chips."""
    from apps.search.infrastructure.models import SearchTerm

    terms = cache.get(POPULAR_CACHE_KEY)
    if terms is None:
        since = timezone.now() - timedelta(days=POPULAR_WINDOW_DAYS)
        terms = list(SearchTerm.objects.filter(last_seen__gte=since, last_results__gt=0).order_by("-searches", "-last_seen").values_list("display", flat=True)[:20])
        cache.set(POPULAR_CACHE_KEY, terms, POPULAR_TTL)
    return terms[:limit]
