"""
Dashboard → Chat markazi: the support desk where staff answer customers.

Three panes -- the conversation queue (waiting for a reply / mine / open / store chats / closed, search, unread
counts, waiting time), the thread (text, photos / videos, stickers, read receipts, quick replies) and the customer
profile (contact, loyalty, recent orders, other chats) with the conversation actions.

Django admin uses session auth while the chat REST API is JWT-only, so these views call the chat Application
Services directly (SendMessage, AddParticipant, AssignOperator, Close/Reopen/ArchiveConversation,
MarkConversationRead). A staff member acts in the chat domain under a stable UUID derived from their admin id.
Replies are pushed to the customer in real time (apps/chat/infrastructure/realtime.py); the bell notification is
sent by chat's own post_save hook. Store conversations (customer ↔ branch owner) are visible here but answered by
the store, not the support desk.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.chat.domain.enums import MessageType, ParticipantRole
from apps.chat.infrastructure import composition
from apps.chat.infrastructure import automation
from apps.chat.infrastructure.automation import BOT_ID, VARIABLES, card_payload, hours_label, is_open, render_template, template_vars
from apps.chat.infrastructure.realtime import attachment_url
from common.exceptions import DomainException

STICKERS = {  # code -> (emoji, Uzbek label) -- mirrors the storefront's lib/chat-stickers.ts
    "hello": ("👋", "Assalomu alaykum!"), "thanks": ("🙏", "Rahmat!"), "in_stock": ("✅", "Mavjud"), "order_ready": ("📦", "Buyurtma tayyor"),
    "on_the_way": ("🚚", "Yo'lda"), "delivered": ("🎉", "Yetkazildi"), "discount": ("🔥", "Chegirma!"), "original": ("🛡️", "100% original"),
    "one_moment": ("⏳", "Bir daqiqa"), "power": ("💪", "Kuch sizda!"), "call_me": ("📞", "Qo'ng'iroq qiling"), "deal": ("🤝", "Kelishdik!"),
}
ORDER_STATUS = {"pending_payment": ("To'lov kutilmoqda", "#d97706"), "confirmed": ("Tasdiqlandi", "#0ea5e9"), "processing": ("Yig'ilmoqda", "#0ea5e9"),
                "shipped": ("Yo'lda", "#2563eb"), "delivered": ("Yetkazildi", "#16a34a"), "completed": ("Yakunlandi", "#16a34a"), "cancelled": ("Bekor qilingan", "#dc2626"),
                "returned": ("Qaytarilgan", "#dc2626"), "failed": ("Muvaffaqiyatsiz", "#dc2626")}
FILTERS = ("waiting", "mine", "open", "review", "stores", "closed")


def _desk_card(content: str | None) -> dict | None:
    """card_payload() with the photo on this host (the dashboard is served by the backend itself, whatever the public host is today)."""
    card = card_payload(content)
    if card and card.get("image"):
        card["image"] = attachment_url(card["image"], absolute=False)
    return card


def _quick_replies() -> list[dict]:
    from apps.chat.infrastructure.models import ChatQuickReply

    return [{"id": q.pk, "title": q.title, "text": q.text} for q in ChatQuickReply.objects.filter(is_active=True).order_by("sort_order", "title")]


def _actor_id(request) -> uuid.UUID:
    """A staff member's identity inside the chat domain (admin ids are integers, chat ids UUIDs) -- stable per staff user."""
    return staff_uuid(request.user.id)


def staff_uuid(user_pk) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"nutrizone-admin-staff-{user_pk}")


def _staff_names() -> dict:
    return automation.staff_names()


def _staff_name(request) -> str:
    return request.user.get_full_name() or request.user.get_username()


def _json_error(exc, status: int = 422) -> JsonResponse:
    message = str(exc)
    if "not open" in message:
        message = "Suhbat yopiq. Javob yozish uchun avval uni qayta oching."
    return JsonResponse({"success": False, "error": {"message": message}}, status=getattr(exc, "http_status", status) if isinstance(exc, DomainException) else status)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _media(path: str) -> str:
    return path if not path or path.startswith(("http://", "https://", "/")) else f"{settings.MEDIA_URL}{path}"


def _avatar(user) -> str:
    latest = next(iter(user.avatar_assets.all()), None) if user is not None else None
    if latest is None or not latest.storage_path:
        return ""
    return _media((latest.thumbnail_paths or {}).get("small") or latest.storage_path)


def _users(ids) -> dict:
    from django.db.models import Prefetch

    from apps.identity.infrastructure.models import User, UserAvatarAsset

    return {u.id: u for u in User._base_manager.filter(id__in=list({i for i in ids if i})).prefetch_related(Prefetch("avatar_assets", queryset=UserAvatarAsset.objects.order_by("-created_at")))}


def _stores(ids) -> dict:
    from apps.stores.infrastructure.models import Store

    return {s.id: s for s in Store.objects.filter(id__in=list({i for i in ids if i}))}


def _preview(m) -> str:
    if m is None:
        return ""
    if m.sender_id == BOT_ID:
        return "🤖 " + ("Buyurtma kartochkasi" if m.message_type == "card" else (m.content or "").strip())
    if m.message_type == "sticker":
        emoji, label = STICKERS.get(m.content or "", ("🏷️", "Stiker"))
        return f"{emoji} {label}"
    if m.message_type == "card":
        return "🛍️ Mahsulot / buyurtma kartochkasi"
    if m.message_type == "attachment":
        return {"image": "📷 Rasm", "video": "🎬 Video"}.get(m.attachment_type or "", "📎 Fayl")
    return (m.content or "").strip()


# ---------------------------------------------------------------- the queue


def _queue(request, flt: str, q: str) -> list[dict]:
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel

    me = _actor_id(request)
    qs = ConversationModel.objects.all()
    if flt == "review":
        from apps.chat.infrastructure.models import ConversationRating

        qs = qs.filter(id__in=ConversationRating.objects.filter(review_status="open").values("conversation_id"))
    elif flt == "closed":
        qs = qs.filter(status__in=("closed", "archived"))
    else:
        qs = qs.filter(status="open")
    if flt == "stores":
        qs = qs.filter(conversation_type="customer_sales")
    elif flt in ("waiting", "mine", "open"):
        qs = qs.exclude(conversation_type="customer_sales")
    if flt == "mine":
        qs = qs.filter(assigned_operator_id=me)
    convs = list(qs.order_by("-last_activity_at", "-created_at")[:300])
    ids = [c.id for c in convs]
    parts: dict = {}
    for p in ParticipantModel.objects.filter(conversation_id__in=ids, removed_at__isnull=True):
        parts.setdefault(p.conversation_id, []).append(p)
    customers = {cid: next((p.user_id for p in ps if p.role == "customer"), None) for cid, ps in parts.items()}
    users, stores = _users(customers.values()), _stores(c.store_id for c in convs)
    last = {m.conversation_id: m for m in MessageModel.objects.filter(conversation_id__in=ids).order_by("conversation_id", "-created_at").distinct("conversation_id")}
    last_human = dict(MessageModel.objects.filter(conversation_id__in=ids).exclude(sender_id=BOT_ID).order_by("conversation_id", "-created_at").distinct("conversation_id")
                      .values_list("conversation_id", "sender_id"))  # a bot answer doesn't take a chat out of "waiting"
    reviews = automation.under_review(ids)
    unread = dict(MessageModel.objects.filter(conversation_id__in=ids, read_at__isnull=True, sender_id__in=[u for u in customers.values() if u])
                  .values("conversation_id").annotate(n=Count("id")).values_list("conversation_id", "n"))
    counts = dict(MessageModel.objects.filter(conversation_id__in=ids).values("conversation_id").annotate(n=Count("id")).values_list("conversation_id", "n"))
    from apps.chat.infrastructure.models import ConversationRating

    ratings = dict(ConversationRating.objects.filter(conversation_id__in=ids).order_by("conversation_id", "created_at").values_list("conversation_id", "score"))  # latest wins
    rows = []
    needle = q.strip().lower()
    for c in convs:
        u = users.get(customers.get(c.id))
        m = last.get(c.id)
        waiting = c.status == "open" and customers.get(c.id) is not None and last_human.get(c.id) == customers.get(c.id)
        if flt == "waiting" and not waiting:
            continue
        name = (u.full_name or u.phone_number) if u else "Mijoz"
        if needle and needle not in f"{name} {u.phone_number if u else ''} {_preview(m)}".lower():
            continue
        store = stores.get(c.store_id)
        rows.append({
            "id": str(c.id), "type": c.conversation_type, "status": c.status, "store": store.name if store else "",
            "customer": {"name": name, "phone": u.phone_number if u else "", "avatar": _avatar(u)},
            "last": _preview(m), "last_from_customer": waiting, "last_at": _iso(m.created_at if m else c.last_activity_at or c.created_at),
            "unread": unread.get(c.id, 0), "messages": counts.get(c.id, 0), "waiting_since": _iso(_waiting_since(c.id, customers.get(c.id))) if waiting else None,
            "assigned": "me" if c.assigned_operator_id == me else ("other" if c.assigned_operator_id else ""), "rating": ratings.get(c.id),
            "review": reviews.get(c.id),
        })
    return rows[:150]


def _waiting_since(conversation_id, customer_id):
    """When the customer's latest unanswered message arrived (bot messages ignored)."""
    from apps.chat.infrastructure.models import MessageModel

    human = MessageModel.objects.filter(conversation_id=conversation_id).exclude(sender_id=BOT_ID).order_by("-created_at")
    return human.filter(sender_id=customer_id).values_list("created_at", flat=True).first()


def _waiting_ids() -> list:
    """Open conversations whose latest message came from the customer -- the ones waiting for an answer."""
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel

    ids = list(ConversationModel.objects.filter(status="open").values_list("id", flat=True))
    customers = set(ParticipantModel.objects.filter(conversation_id__in=ids, role="customer").values_list("conversation_id", "user_id"))
    last = MessageModel.objects.filter(conversation_id__in=ids).exclude(sender_id=BOT_ID).order_by("conversation_id", "-created_at").distinct("conversation_id").values_list("conversation_id", "sender_id")
    return [cid for cid, sender in last if (cid, sender) in customers]


def _stats(request) -> dict:
    from apps.chat.infrastructure.models import ConversationModel, MessageModel

    me = _actor_id(request)
    support = ConversationModel.objects.filter(status="open").exclude(conversation_type="customer_sales")
    day = timezone.now() - timedelta(days=1)
    waiting = ConversationModel.objects.filter(id__in=_waiting_ids()).exclude(conversation_type="customer_sales").count()
    return {
        "waiting": waiting, "open": support.count(), "mine": support.filter(assigned_operator_id=me).count(),
        "stores": ConversationModel.objects.filter(status="open", conversation_type="customer_sales").count(),
        "today": MessageModel.objects.filter(created_at__gte=day).count(), "first_reply": _first_reply_minutes(),
        "csat": _csat(), "open_now": is_open(), "hours": hours_label(), "review": _review_count(),
    }


def _review_count() -> int:
    from apps.chat.infrastructure.models import ConversationRating

    return ConversationRating.objects.filter(review_status="open").values("conversation_id").distinct().count()


def _csat() -> float | None:
    """Average 1–5 ★ score of the last 30 days' rated support chats."""
    from django.db.models import Avg

    from apps.chat.infrastructure.models import ConversationRating

    avg = ConversationRating.objects.filter(created_at__gte=timezone.now() - timedelta(days=30)).aggregate(a=Avg("score"))["a"]
    return round(avg, 1) if avg else None


def _first_reply_minutes() -> int | None:
    """Median first-response time of the last 30 days (business time, per customer request -- see chat/infrastructure/reports.py)."""
    from statistics import median

    from apps.chat.infrastructure.reports import first_responses

    waits = [r["minutes"] for r in first_responses(timezone.now() - timedelta(days=30))]
    return round(median(waits)) if waits else None


# ---------------------------------------------------------------- one conversation


def _thread(request, conv, after: datetime | None) -> list[dict]:
    from apps.chat.infrastructure.models import MessageModel, ParticipantModel

    me = _actor_id(request)
    roles = {p.user_id: p.role for p in ParticipantModel.objects.filter(conversation_id=conv.id)}
    qs = MessageModel.objects.filter(conversation_id=conv.id).order_by("created_at")
    if after:
        qs = qs.filter(created_at__gt=after)
    msgs = list(qs[:500])
    users, staff = _users(m.sender_id for m in msgs), _staff_names()
    store = _stores([conv.store_id]).get(conv.store_id) if conv.store_id else None
    out = []
    for m in msgs:
        role = roles.get(m.sender_id, "operator")
        if m.message_type == "system" or m.sender_id == BOT_ID:
            who, kind = "Avtomatik javob", "system"
        elif m.sender_id in staff:
            who, kind = staff[m.sender_id], "staff"
        elif role == "customer":
            u = users.get(m.sender_id)
            who, kind = (u.full_name or u.phone_number) if u else "Mijoz", "customer"
        elif conv.conversation_type == "customer_sales":
            who, kind = (store.name if store else "Do'kon"), "store"
        else:
            who, kind = "Operator", "staff"
        sticker = STICKERS.get(m.content or "") if m.message_type == "sticker" else None
        out.append({
            "id": str(m.id), "kind": kind, "mine": m.sender_id == me, "who": who, "type": m.message_type, "deleted": m.status == "deleted",
            "content": "" if m.status == "deleted" else (m.content or ""), "sticker": {"emoji": sticker[0], "label": sticker[1]} if sticker else None,
            "attachment": {"type": m.attachment_type, "url": attachment_url(m.attachment_url, absolute=False), "name": m.attachment_filename, "size": m.attachment_size_bytes} if m.attachment_url else None,
            "card": _desk_card(m.content) if m.message_type == "card" else None,
            "at": _iso(m.created_at), "read_at": _iso(m.read_at), "edited": bool(m.edited_at),
        })
    return out


def _profile(conv) -> dict:
    from apps.chat.infrastructure.models import ConversationModel, ParticipantModel

    customer_id = ParticipantModel.objects.filter(conversation_id=conv.id, role="customer").values_list("user_id", flat=True).first()
    u = _users([customer_id]).get(customer_id) if customer_id else None
    out: dict = {"customer": None, "loyalty": None, "orders": [], "order_count": 0, "spent": 0, "other_chats": 0}
    if u is None:
        return out
    out["customer"] = {"id": str(u.id), "name": u.full_name or "Ismsiz mijoz", "phone": u.phone_number, "telegram": u.telegram_username or ("ulangan" if u.telegram_user_id else ""),
                       "avatar": _avatar(u), "joined": u.created_at.strftime("%d.%m.%Y"), "status": u.status, "url": reverse("admin:identity_user_change", args=[u.id])}
    try:
        from apps.loyalty.infrastructure import services as loyalty

        s = loyalty.summary(u.id)
        out["loyalty"] = {"balance": s.balance, "tier": s.current_tier.name if s.current_tier else "", "color": s.current_tier.color if s.current_tier else "#64748b"}
    except Exception:  # noqa: BLE001 - loyalty is optional for the desk
        pass
    try:
        from django.db.models import DecimalField, ExpressionWrapper, F, Sum

        from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

        orders = list(OrderModel.objects.filter(customer_id=u.id).exclude(status="draft").order_by("-created_at")[:5])
        expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
        totals = dict(OrderLineItemModel.objects.filter(order__in=orders, status="active").values("order_id").annotate(t=Sum(expr)).values_list("order_id", "t"))
        out["order_count"] = OrderModel.objects.filter(customer_id=u.id).exclude(status="draft").count()
        out["spent"] = int(OrderLineItemModel.objects.filter(order__customer_id=u.id, order__status__in=("delivered", "completed"), status="active").aggregate(t=Sum(expr))["t"] or 0)
        out["orders"] = [{"id": str(o.pk), "number": o.order_number, "status": ORDER_STATUS.get(o.status, (o.status, "#64748b"))[0], "color": ORDER_STATUS.get(o.status, ("", "#64748b"))[1],
                          "total": int(totals.get(o.pk) or 0), "date": o.created_at.strftime("%d.%m.%Y"), "url": reverse("admin:ordering_ordermodel_change", args=[o.pk])} for o in orders]
    except Exception:  # noqa: BLE001
        pass
    out["other_chats"] = ConversationModel.objects.filter(participants__user_id=u.id).exclude(id=conv.id).distinct().count()
    from django.db.models import Avg

    from apps.chat.infrastructure.models import ConversationRating

    agg = ConversationRating.objects.filter(customer_id=u.id).aggregate(a=Avg("score"), n=Count("id"))
    out["ratings"] = {"avg": round(agg["a"], 1) if agg["a"] else None, "count": agg["n"]}
    return out


def _conv_payload(request, conv) -> dict:
    store = _stores([conv.store_id]).get(conv.store_id) if conv.store_id else None
    me = _actor_id(request)
    staff = _staff_names()
    return {"id": str(conv.id), "type": conv.conversation_type, "status": conv.status, "store": store.name if store else "",
            "assigned": "me" if conv.assigned_operator_id == me else ("other" if conv.assigned_operator_id else ""),
            "assigned_name": staff.get(conv.assigned_operator_id, "") if conv.assigned_operator_id else "", "created": conv.created_at.strftime("%d.%m.%Y %H:%M"),
            "can_reply": conv.conversation_type != "customer_sales", "rating": _rating(conv.id), "review": automation.under_review([conv.id]).get(conv.id)}


def _rating(conversation_id) -> dict | None:
    from apps.chat.infrastructure.models import ConversationRating

    return ConversationRating.objects.filter(conversation_id=conversation_id).order_by("-created_at").values("score", "comment").first()


def _is_participant(conv_id, user_id) -> bool:
    from apps.chat.infrastructure.models import ParticipantModel

    return ParticipantModel.objects.filter(conversation_id=conv_id, user_id=user_id, removed_at__isnull=True).exists()


def _join(conv, operator_id) -> None:
    """Seat the staff member as an operator (AddParticipant) and take the conversation if nobody has (AssignOperator)."""
    if not _is_participant(conv.id, operator_id):
        composition.build_add_participant(operator_id).execute(conversation_id=conv.id, user_id=operator_id, role=ParticipantRole.OPERATOR)
    if conv.assigned_operator_id is None:
        composition.build_assign_operator(operator_id).execute(conversation_id=conv.id, operator_user_id=operator_id)


def _mark_read(conv_id, operator_id) -> None:
    if _is_participant(conv_id, operator_id):
        try:
            composition.build_mark_conversation_read(operator_id).execute(conversation_id=conv_id, reader_id=operator_id)
        except Exception:  # noqa: BLE001 - read receipts are best effort
            pass


def _load(conversation_id):
    from apps.chat.infrastructure.models import ConversationModel

    try:
        return ConversationModel.objects.get(pk=uuid.UUID(str(conversation_id)))
    except (ValueError, ConversationModel.DoesNotExist):
        return None


# ---------------------------------------------------------------- views


@staff_member_required
def chat_admin_view(request):
    config = {
        "urls": {"queue": reverse("admin:nz_chat_queue"), "conversation": reverse("admin:nz_chat_conversation", args=["__"]), "send": reverse("admin:nz_chat_send", args=["__"]),
                 "upload": reverse("admin:nz_chat_upload", args=["__"]), "action": reverse("admin:nz_chat_action", args=["__", "--"])},
        "stickers": [{"code": k, "emoji": v[0], "label": v[1]} for k, v in STICKERS.items()], "quick": _quick_replies(),
        "cards": reverse("admin:nz_chat_cards"), "variables": VARIABLES, "report": reverse("admin:nz_chat_report"), "site": (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/"), "quick_admin": reverse("admin:chat_chatquickreply_changelist"), "settings_admin": reverse("admin:chat_chatsettings_changelist"),
        "open": request.GET.get("c", ""), "filter": request.GET.get("f", "waiting") if request.GET.get("f") in FILTERS else "waiting",
    }
    config["rows"] = _queue(request, config["filter"], "")  # first paint without a round trip
    return render(request, "admin/chat_admin.html", {**admin.site.each_context(request), "title": "Chat markazi", "config": config, "stats": _stats(request)})


@staff_member_required
def chat_queue_api(request):
    flt = request.GET.get("f", "waiting")
    return JsonResponse({"success": True, "data": {"rows": _queue(request, flt if flt in FILTERS else "waiting", request.GET.get("q", "")), "stats": _stats(request)}})


@staff_member_required
def chat_conversation_api(request, conversation_id: str):
    conv = _load(conversation_id)
    if conv is None:
        return JsonResponse({"success": False, "error": {"message": "Suhbat topilmadi."}}, status=404)
    after = None
    if request.GET.get("after"):
        try:
            after = datetime.fromisoformat(request.GET["after"])
        except ValueError:
            after = None
    me = _actor_id(request)
    messages = _thread(request, conv, after)
    if messages and any(m["kind"] == "customer" and not m["read_at"] for m in messages):
        _mark_read(conv.id, me)
    data = {"conversation": _conv_payload(request, conv), "messages": messages}
    if after is None:
        data["profile"] = _profile(conv)
        data["vars"] = template_vars(conv.id, _staff_name(request)) if conv.conversation_type != "customer_sales" else {}
    return JsonResponse({"success": True, "data": data})


@staff_member_required
def chat_admin_send_message_api(request, conversation_id: str):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": {"message": "Method not allowed"}}, status=405)
    conv = _load(conversation_id)
    if conv is None:
        return JsonResponse({"success": False, "error": {"message": "Suhbat topilmadi."}}, status=404)
    if conv.conversation_type == "customer_sales":
        return JsonResponse({"success": False, "error": {"message": "Bu do'kon suhbati — mijozga do'kon egasi javob beradi."}}, status=409)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    kind = body.get("kind") or "text"
    content = (body.get("content") or "").strip()
    attachment = None
    if kind == "text" and not content:
        return JsonResponse({"success": False, "error": {"message": "Xabar bo'sh bo'lmasin."}}, status=422)
    if kind in ("text", "attachment") and content:
        content, missing = render_template(content, template_vars(conv.id, _staff_name(request)))
        if missing:  # never send a customer a raw "{buyurtma_raqami}"
            names = ", ".join("{" + m + "}" for m in missing)
            return JsonResponse({"success": False, "error": {"message": f"{names} uchun ma'lumot yo'q — matnda o'zingiz to'ldiring.", "missing": missing}}, status=422)
    if kind == "sticker" and content not in STICKERS:
        return JsonResponse({"success": False, "error": {"message": "Noma'lum stiker."}}, status=422)
    if kind == "card" and card_payload(content) is None:
        return JsonResponse({"success": False, "error": {"message": "Mahsulot yoki buyurtma topilmadi."}}, status=422)
    if kind == "attachment":
        from apps.chat.domain.enums import AttachmentType
        from apps.chat.domain.value_objects import AttachmentMetadata

        a = body.get("attachment") or {}
        if not a.get("url") or not composition.build_media_storage_gateway().confirm_media_url_exists(a["url"]):
            return JsonResponse({"success": False, "error": {"message": "Fayl topilmadi — qayta yuklang."}}, status=422)
        attachment = AttachmentMetadata(attachment_type=AttachmentType(a.get("type") or "image"), url=a["url"], filename=str(a.get("name") or "fayl")[:255], size_bytes=int(a.get("size") or 0))
    operator = _actor_id(request)
    try:
        _join(conv, operator)
        message = composition.build_send_message(operator).execute(
            conversation_id=conv.id, sender_id=operator, message_type={"sticker": MessageType.STICKER, "attachment": MessageType.ATTACHMENT, "card": MessageType.CARD}.get(kind, MessageType.TEXT),
            content=content or None, attachment=attachment,
        )
    except Exception as exc:  # noqa: BLE001 -- boundary layer, reported to the operator
        return _json_error(exc)
    from apps.chat.infrastructure.models import ParticipantModel
    from apps.chat.infrastructure.realtime import message_payload, push_message

    push_message(conv.id, message_payload(message), operator, ParticipantModel.objects.filter(conversation_id=conv.id, removed_at__isnull=True).values_list("user_id", flat=True))
    _mark_read(conv.id, operator)
    if body.get("quick_id"):
        from django.db.models import F

        from apps.chat.infrastructure.models import ChatQuickReply

        ChatQuickReply.objects.filter(pk=body["quick_id"]).update(uses=F("uses") + 1)
    conv.refresh_from_db()
    return JsonResponse({"success": True, "data": {"messages": _thread(request, conv, None)[-1:], "conversation": _conv_payload(request, conv)}}, status=201)


@staff_member_required
def chat_cards_api(request):
    """Products to share as a card (search by name / SKU); the customer's own orders come from the profile."""
    from apps.products.infrastructure.models import Product

    q = (request.GET.get("q") or "").strip()
    qs = Product.objects.filter(status="published")
    if q:
        qs = qs.filter(Q(translations__name__icontains=q) | Q(variants__sku__icontains=q)).distinct()
    cards = [_desk_card(f"product:{pid}") for pid in qs.order_by("-created_at").values_list("id", flat=True)[:8]]
    return JsonResponse({"success": True, "data": [c for c in cards if c]})


@staff_member_required
def chat_upload_api(request, conversation_id: str):
    """A photo / video for a reply -- the same media pipeline as the customer's upload; the client then sends it as an attachment message."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": {"message": "Method not allowed"}}, status=405)
    if _load(conversation_id) is None:
        return JsonResponse({"success": False, "error": {"message": "Suhbat topilmadi."}}, status=404)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"success": False, "error": {"message": "Faylni tanlang."}}, status=422)
    if uploaded.size > 20 * 1024 * 1024:
        return JsonResponse({"success": False, "error": {"message": "Fayl 20 MB dan katta bo'lmasin."}}, status=422)
    from apps.products.infrastructure.composition import build_media_pipeline
    from core.media import MediaType, MediaUploadRequest

    is_video = bool(uploaded.content_type and uploaded.content_type.startswith("video/"))
    result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type,
                                                               media_type=MediaType.VIDEO if is_video else MediaType.IMAGE))
    if result.is_failure:
        return JsonResponse({"success": False, "error": {"message": result.errors[0].message}}, status=422)
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return JsonResponse({"success": True, "data": {"type": "video" if is_video else "image", "url": f"{base}{settings.MEDIA_URL}{result.value.storage_path}",
                                                   "name": uploaded.name, "size": uploaded.size}}, status=201)


@staff_member_required
def chat_action_api(request, conversation_id: str, action: str):
    """take (join + assign to me), close, reopen, archive -- each through its chat Application Service; resolve -- ends a low-rating review."""
    if request.method != "POST" or action not in ("take", "close", "reopen", "archive", "resolve"):
        return JsonResponse({"success": False, "error": {"message": "Not allowed"}}, status=405)
    conv = _load(conversation_id)
    if conv is None:
        return JsonResponse({"success": False, "error": {"message": "Suhbat topilmadi."}}, status=404)
    me = _actor_id(request)
    try:
        if action == "resolve":
            try:
                note = (json.loads(request.body or b"{}").get("note") or "")
            except ValueError:
                note = ""
            if not automation.resolve_review(conv.id, _staff_name(request), note):
                return JsonResponse({"success": False, "error": {"message": "Bu suhbat nazoratda emas."}}, status=409)
        elif action == "take":
            if conv.conversation_type == "customer_sales":
                return JsonResponse({"success": False, "error": {"message": "Do'kon suhbatini do'kon egasi olib boradi."}}, status=409)
            if not _is_participant(conv.id, me):
                composition.build_add_participant(me).execute(conversation_id=conv.id, user_id=me, role=ParticipantRole.OPERATOR)
            composition.build_assign_operator(me).execute(conversation_id=conv.id, operator_user_id=me)
        else:
            {"close": composition.build_close_conversation, "reopen": composition.build_reopen_conversation, "archive": composition.build_archive_conversation}[action](me).execute(conversation_id=conv.id)
    except Exception as exc:  # noqa: BLE001
        return _json_error(exc)
    conv.refresh_from_db()
    return JsonResponse({"success": True, "data": {"conversation": _conv_payload(request, conv)}})


@staff_member_required
def chat_report_view(request):
    """Operatorlar hisoboti: per staff member -- answered requests, first-response time, closed chats, ratings."""
    from apps.chat.infrastructure.reports import operator_report

    days = int(request.GET.get("days", 30)) if request.GET.get("days") in ("7", "30", "90") else 30
    report = operator_report(days)
    t = report["totals"]
    stats = [
        {"label": "Javob berilgan murojaat", "value": t["answered"], "tone": "#4f46e5", "icon": "fa-reply"},
        {"label": "Birinchi javob (median)", "value": t["first_median"], "tone": "#0891b2", "icon": "fa-stopwatch", "sub": f"{report['sla_minutes']} daqiqagacha: {t['sla']}%" if t["sla"] is not None else ""},
        {"label": "Yopilgan suhbat", "value": t["closed"], "tone": "#16a34a", "icon": "fa-circle-check"},
        {"label": "O'rtacha baho", "value": f"{t['csat']} ★" if t["csat"] else "—", "tone": "#f59e0b", "icon": "fa-star", "sub": f"{t['ratings']} ta baho"},
        {"label": "Past baho (1–2 ★)", "value": t["low"], "tone": "#dc2626", "icon": "fa-triangle-exclamation", "sub": f"nazoratda: {t['review_open']}",
         "href": reverse("admin:chat_conversationrating_changelist") + "?review_status=open"},
    ]
    tabs = [{"label": f"{d} kun", "url": f"?days={d}", "on": d == days} for d in (7, 30, 90)]
    return render(request, "admin/chat_report.html", {**admin.site.each_context(request), "title": "Operatorlar hisoboti", "report": report, "stats": stats, "tabs": tabs,
                                                      "desk": reverse("admin:nz_chat_admin")})


# ---------------------------------------------------------------- legacy endpoints (kept for existing links)


@staff_member_required
def chat_admin_messages_api(request, conversation_id: str):
    conv = _load(conversation_id)
    if conv is None:
        return JsonResponse({"success": False, "error": {"message": "Suhbat topilmadi."}}, status=404)
    return JsonResponse({"success": True, "data": _thread(request, conv, None)})

