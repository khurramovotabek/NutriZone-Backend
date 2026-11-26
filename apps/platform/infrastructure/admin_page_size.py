"""
"Sahifada: 25 · 50 · 100 · 200" for every Dashboard list (ChangeList): the pager's size links carry `?nz_per=<n>`;
the choice is remembered per list page in the staff member's session and the list restarts at page 1. `nz_per` is
taken out of request.GET before Django's ChangeList reads it, so it is never mistaken for a filter.
"""
from __future__ import annotations

import inspect

PARAM = "nz_per"
SESSION_KEY = "nz_per_page"
SIZES = (25, 50, 100, 200)
MAX_SIZE = 500


def chosen(request) -> int | None:
    try:
        n = int((request.session.get(SESSION_KEY) or {}).get(request.path) or 0)
    except (AttributeError, TypeError, ValueError):
        return None
    return n if 1 <= n <= MAX_SIZE else None


def _remember(request) -> None:
    raw = request.GET.get(PARAM)
    if raw is None:
        return
    params = request.GET.copy()
    params.pop(PARAM, None)
    params.pop("p", None)  # a new page size starts at the first page
    request.GET = params
    try:
        n = int(raw)
    except ValueError:
        return
    store = dict(request.session.get(SESSION_KEY) or {})
    if 1 <= n <= MAX_SIZE:
        store[request.path] = n
    else:
        store.pop(request.path, None)
    if len(store) > 80:  # keep the session small
        store = dict(list(store.items())[-80:])
    request.session[SESSION_KEY] = store


def install() -> None:
    from django.contrib.admin.views.main import ChangeList

    if getattr(ChangeList, "_nz_page_size", False):
        return
    original = ChangeList.__init__
    sig = inspect.signature(original)

    def __init__(self, *args, **kwargs):
        bound = sig.bind(self, *args, **kwargs)
        request = bound.arguments.get("request")
        if request is not None and hasattr(request, "session"):
            _remember(request)
            n = chosen(request)
            if n:
                bound.arguments["list_per_page"] = n
                bound.arguments["list_max_show_all"] = max(bound.arguments.get("list_max_show_all") or 0, n)
        original(*bound.args, **bound.kwargs)

    ChangeList.__init__ = __init__
    ChangeList._nz_page_size = True
