"""Template helpers for the shared premium admin list (templates/admin/premium/list.html)."""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def nzi_choices(spec, cl) -> list[dict]:
    """A list filter's choices as plain dicts (an empty list hides a filter with nothing to choose)."""
    choices = list(spec.choices(cl))
    return choices if len(choices) > 1 else []


@register.simple_tag
def nz_phrases_version(lang: str) -> str:
    """Cache-busting version of the dashboard phrase catalog (apps/platform/infrastructure/admin_i18n.py)."""
    from apps.platform.infrastructure.admin_i18n import phrases_version

    return phrases_version((lang or "uz")[:2])


@register.simple_tag
def nz_pager(cl, page_range) -> dict:
    """Everything templates/admin/pagination.html draws: "51–100 / 253", previous / next and the page
    numbers (Django's elided range on wide screens, `compact` -- first, current ±1, last -- on phones). Every link keeps the list's
    filters, search and ordering (ChangeList.get_query_string)."""
    from django.contrib.admin.views.main import PAGE_VAR

    current, total = cl.page_num, cl.paginator.num_pages
    link = lambda n: cl.get_query_string({PAGE_VAR: n})  # noqa: E731
    def entry(i):
        return {"n": i, "url": link(i), "current": i == current}

    items = [{"gap": True} if i == cl.paginator.ELLIPSIS else entry(i) for i in page_range]
    # phones: first, last and the current page with its neighbours, a gap mark wherever pages are skipped
    near = sorted({n for n in (1, current - 1, current, current + 1, total) if 1 <= n <= total})
    compact = []
    for idx, n in enumerate(near):
        if idx and n - near[idx - 1] > 1:
            compact.append(entry(n - 1) if n - near[idx - 1] == 2 else {"gap": True})
        compact.append(entry(n))
    start = (current - 1) * cl.list_per_page + 1 if cl.result_count else 0
    return {
        "items": items,
        "compact": compact,
        "prev": link(current - 1) if current > 1 else None,
        "next": link(current + 1) if current < total else None,
        "start": start,
        "end": min(current * cl.list_per_page, cl.result_count),
        "current": current,
        "total": total,
    }
