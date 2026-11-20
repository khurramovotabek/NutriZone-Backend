"""Dashboard → Platforma → Server holati (server_status.py). Superusers and staff with the jobs permission only."""
from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

PERMISSION = "django_celery_beat.view_periodictask"


@staff_member_required
def server_status_view(request):
    if not (request.user.is_superuser or request.user.has_perm(PERMISSION)):
        raise PermissionDenied
    from apps.platform.infrastructure.premium_admin import ASSET_V
    from apps.platform.infrastructure.server_status import snapshot

    context = {**admin.site.each_context(request), "title": "Server holati", "s": snapshot(), "asset_v": ASSET_V}
    template = "admin/platform/server_status_body.html" if request.GET.get("partial") == "1" else "admin/platform/server_status.html"
    response = render(request, template, context)
    response["Cache-Control"] = "no-store"
    return response
