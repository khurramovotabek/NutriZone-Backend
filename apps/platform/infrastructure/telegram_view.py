"""
Dashboard → Telegram botlar markazi (telegram_center.py):

  /django-admin/telegram/status/           the page (any staff member; never shows a token)
  /django-admin/telegram/preview/?kind=…   one bot message rendered as it is sent now (order / sale / report previews
                                           carry customer and sales data: Analitika viewers only)
  /django-admin/telegram/check/  (POST)    live getMe for every configured bot (superusers)
  /django-admin/telegram/invite-owner/ (POST store=<id>)  (re)send a branch owner the Analytics bot invitation
  /django-admin/telegram/orders-channel/ (POST op=connect|connect_chat|test|disconnect|detect)  the Orders channel
                                           (superusers; apps/telegram_bot/infrastructure/orders_chat.py)
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
        "branch_owners": tc.branch_owners() if can_view(request.user) else None,
        "previews": previews,
        "can_check": request.user.is_superuser,
        "orders_channel": _orders_channel_status(),
    }
    return render(request, "admin/platform/telegram_center.html", context)


def _orders_channel_status() -> dict | None:
    from apps.telegram_bot.infrastructure import orders_chat

    try:
        return orders_chat.status()
    except Exception:  # noqa: BLE001 - the rest of the page must still open
        return None


@staff_member_required
@require_POST
def telegram_orders_channel_view(request):
    """Connect / test / disconnect the Orders channel. Customer names, phones and addresses go there -- superusers only."""
    from django.contrib import messages
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    from apps.telegram_bot.infrastructure import orders_chat

    if not request.user.is_superuser:
        raise PermissionDenied
    by = f"Dashboard: {request.user.get_username()}"
    op = request.POST.get("op", "")
    if op == "connect":
        ok, text = orders_chat.connect_ref(request.POST.get("ref", ""), by)
    elif op == "connect_chat":
        ok, text = orders_chat.connect_ref(request.POST.get("chat", ""), by)
    elif op == "test":
        ok, text = orders_chat.send_test(by)
    elif op == "disconnect":
        ok, text = orders_chat.disconnect(by)
    elif op == "detect":
        ok, text = _register_orders_webhook()
    else:
        ok, text = False, "Noma'lum amal."
    (messages.success if ok else messages.warning)(request, text)
    return HttpResponseRedirect(reverse("admin:nz_telegram_status") + "#orders-channel")


def _register_orders_webhook() -> tuple[bool, str]:
    """Re-register the Orders bot webhook with my_chat_member/channel_post, so channels it is admin of show up here."""
    import io

    from django.core.management import call_command

    out = io.StringIO()
    try:
        call_command("telegram_set_webhook", bot="orders", stdout=out, stderr=out)
    except Exception as exc:  # noqa: BLE001 - shown to the superuser, never a 500
        return False, f"Webhook yangilanmadi: {exc}"
    return True, "Orders bot endi kanal o'zgarishlarini eshitadi. Kanalga istalgan xabar yozing — u shu ro'yxatda paydo bo'ladi."


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


@staff_member_required
@require_POST
def telegram_invite_owner_view(request):
    from django.contrib import messages
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    if not request.user.has_perm("stores.change_store"):
        raise PermissionDenied
    ok, text = tc.invite_owner(request.POST.get("store", ""))
    (messages.success if ok else messages.warning)(request, text)
    return HttpResponseRedirect(reverse("admin:nz_telegram_status") + "#owners")
