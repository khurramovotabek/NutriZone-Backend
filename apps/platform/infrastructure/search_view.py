"""
Phase 17.1: global admin dashboard search (Ctrl+K command palette).

Deliberately NOT a new search engine -- reuses existing models via
simple icontains queries, matching this phase's own explicit "keep it
simple" instruction. Patches admin.site.get_urls() following the exact
same pattern already established by reports_view.py.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse

_MAX_RESULTS_PER_GROUP = 5


@staff_member_required
def global_search_view(request):
    """
    Returns grouped, permission-safe results for the dashboard's own
    Ctrl+K command palette. staff_member_required means only
    authenticated staff ever reach this view at all -- no additional
    per-entity authorization is layered on top, matching the same
    boundary every other custom admin view in this project already
    uses (reports_view, audit_timeline_view, etc.).
    """
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"query": query, "groups": []})

    groups = []

    products = _search_products(query)
    if products:
        groups.append({"label": "Products", "results": products})

    orders = _search_orders(query)
    if orders:
        groups.append({"label": "Orders", "results": orders})

    customers = _search_customers(query)
    if customers:
        groups.append({"label": "Customers", "results": customers})

    return JsonResponse({"query": query, "groups": groups})


def _search_products(query: str) -> list[dict]:
    from apps.products.infrastructure import models as products_orm

    rows = (
        products_orm.Product.objects.filter(translations__name__icontains=query)
        .prefetch_related("translations")
        .distinct()[:_MAX_RESULTS_PER_GROUP]
    )
    return [
        {
            "id": str(row.id),
            "title": str(row),
            "subtitle": row.status,
            "url": f"/django-admin/products/product/{row.id}/change/",
        }
        for row in rows
    ]


def _search_orders(query: str) -> list[dict]:
    from apps.ordering.infrastructure import models as ordering_orm

    rows = ordering_orm.OrderModel.objects.filter(order_number__icontains=query)[:_MAX_RESULTS_PER_GROUP]
    return [
        {
            "id": str(row.id),
            "title": row.order_number,
            "subtitle": row.status,
            "url": f"/django-admin/ordering/ordermodel/{row.id}/change/",
        }
        for row in rows
    ]


def _search_customers(query: str) -> list[dict]:
    from django.db.models import Q

    from apps.identity.infrastructure import models as identity_orm

    rows = identity_orm.User.objects.filter(Q(phone_number__icontains=query) | Q(full_name__icontains=query))[:_MAX_RESULTS_PER_GROUP]
    return [
        {
            "id": str(row.id),
            "title": row.full_name or row.phone_number,
            "subtitle": row.phone_number,
            "url": f"/django-admin/identity/user/{row.id}/change/",
        }
        for row in rows
    ]


def install() -> None:
    """Called once from PlatformConfig.ready() -- idempotent (safe if ready() ever runs twice). Captures admin.site.get_urls at call time, not import time -- this must run after reports_view.install() (see apps.py's own ready() ordering) so its own URL patches are preserved, not discarded."""
    from django.urls import path

    original_get_urls = admin.site.get_urls

    def _get_urls_with_search():
        return [
            path("search/", global_search_view, name="nz_global_search"),
        ] + original_get_urls()

    admin.site.get_urls = _get_urls_with_search
