"""
Customer inbox API used by the storefront bell and /account/notifications.

    GET  /api/v1/notifications/inbox?lang=uz&filter=all|unread&page=1   -> {items, unread, total, has_more}
    GET  /api/v1/notifications/inbox/unread-count                     -> {unread}
    POST /api/v1/notifications/inbox/read   {"ids": [...]} | {"all": true}

Always scoped to request.user -- a client can never read or mark another customer's notifications.
Text comes back in the requested language (the site's locale), falling back to Uzbek.
"""
from __future__ import annotations

import uuid

from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.notifications.infrastructure.models import NotificationModel
from apps.notifications.infrastructure.notify import KINDS, LANGS, invalidate
from common.responses import success_response

VISIBLE = ("unseen", "seen", "read")


def _mine(request):
    return NotificationModel.objects.filter(recipient_id=request.user.id, status__in=VISIBLE)


def _unread(request) -> int:
    return _mine(request).exclude(status="read").count()


def _lang(request) -> str:
    lang = (request.query_params.get("lang") or "").lower()[:2]
    return lang if lang in LANGS else "uz"


def _item(row: NotificationModel, lang: str) -> dict:
    text = (row.i18n or {}).get(lang) or (row.i18n or {}).get("uz") or {"title": row.title, "body": row.body}
    spec = KINDS.get(row.kind)
    return {
        "id": str(row.id), "kind": row.kind or "announcement", "title": text["title"], "body": (text.get("body") or "").strip(),
        "link": row.link or "", "icon": spec.icon if spec else "bell", "tone": spec.tone if spec else "primary",
        "priority": row.priority, "read": row.status == "read", "created_at": row.created_at.isoformat(),
    }


class InboxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lang = _lang(request)
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            size = min(max(int(request.query_params.get("page_size", 20)), 1), 50)
        except ValueError:
            page, size = 1, 20
        qs = _mine(request)
        if request.query_params.get("filter") == "unread":
            qs = qs.exclude(status="read")
        total = qs.count()
        rows = list(qs.order_by("-created_at")[(page - 1) * size: page * size])
        # opening the inbox marks what's shown as "seen" (the bell badge counts unread, not unseen)
        unseen = [r.id for r in rows if r.status == "unseen"]
        if unseen:
            NotificationModel.objects.filter(id__in=unseen).update(status="seen", seen_at=timezone.now())
        return success_response(data={"items": [_item(r, lang) for r in rows], "unread": _unread(request), "total": total, "has_more": page * size < total, "page": page})


class InboxUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response(data={"unread": _unread(request)})


class InboxReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        qs = _mine(request).exclude(status="read")
        if not request.data.get("all"):
            ids = []
            for raw in (request.data.get("ids") or [])[:200]:
                try:
                    ids.append(uuid.UUID(str(raw)))
                except ValueError:
                    continue
            qs = qs.filter(id__in=ids)
        changed = qs.update(status="read", read_at=now)
        if changed:
            invalidate()
        return success_response(data={"marked": changed, "unread": _unread(request)})


class NewsSubscriptionInfoView(APIView):
    """`GET /notifications/news` -- public: the Telegram news subscription offer (gift coins, bot deep link, subscribers)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        from apps.notifications.infrastructure.subscriptions import public_info

        return success_response(data=public_info())
