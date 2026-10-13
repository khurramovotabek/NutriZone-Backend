"""
Dashboard → Telegram botlar markazi (telegram_center.py):

  /django-admin/telegram/status/           the page (any staff member; never shows a token)
  /django-admin/telegram/preview/?kind=…   one bot message rendered as it is sent now (order / sale / report previews
                                           carry customer and sales data: Analitika viewers only)
  /django-admin/telegram/check/  (POST)    live getMe for every configured bot (superusers)
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.platform.infrastructure import telegram_center as tc
from apps.platform.infrastructure.analytics_view import can_view


def _previews_for(user) -> list[dict]:
    return [p for p in tc.PREVIEWS if not p["private"] or can_view(user)]


@staff_member_required
def telegram_center_view(request):
    previews = _previews_for(request.user)
    context = {
        **admin.site.each_context(request),
        "title": "Telegram botlar markazi",
        "gateway_live": tc.gateway_live(),
        "bots": tc.bots(),
        "subscribers": tc.subscribers() if can_view(request.user) else None,
        "previews": previews,
        "can_check": request.user.is_superuser,
    }
    return render(request, "admin/platform/telegram_center.html", context)


@staff_member_required
def telegram_preview_view(request):
    kind = request.GET.get("kind", "")
    if kind not in {p["kind"] for p in _previews_for(request.user)}:
        raise PermissionDenied
    data = tc.preview(kind)
    if data is None:
        return JsonResponse({"ok": False, "message": "Ko'rsatish uchun ma'lumot hali yo'q."})
    return JsonResponse({"ok": True, **data})


@staff_member_required
@require_POST
def telegram_check_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    return JsonResponse({"ok": True, "bots": tc.check()})
