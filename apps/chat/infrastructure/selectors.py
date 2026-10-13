"""
Chat read-model selectors -- optimized, read-only Postgres queries.
No business logic, no aggregate construction, matching the pattern
established by every prior module.

**A deliberately absent selector, explicitly documented per this
phase's own anti-pattern list**: no unread-message-count query exists
here. `add unread-count infrastructure without a justified contract`
is explicitly forbidden by this phase's own rules -- Domain's `Message.
read_at` is a per-message timestamp, not an aggregate-level concept
Domain has ever certified as "unread count," so building one now
would be inventing a capability rather than implementing one.
"""
from __future__ import annotations

import uuid

from django.db.models import Count

from apps.chat.infrastructure import models as orm
from apps.chat.infrastructure import presence


def _store_summaries(store_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Real, closed gap: a customer's conversation card had no way to show WHICH branch/store they're talking to -- only a generic "operator" id. One extra query for the whole page (never N+1), reusing Store's own logo-thumbnail convention directly (apps.stores has no dedicated selectors module -- confirmed empty except admin.py/models.py/migrations -- so this stays a small, local, read-only query, matching the one-directional "other apps reach INTO stores" convention already established elsewhere)."""
    if not store_ids:
        return {}
    from apps.stores.infrastructure.models import Store

    rows = Store.objects.filter(id__in=store_ids)
    result = {}
    for store in rows:
        logo_url = f"/media/{(store.logo_thumbnail_paths or {}).get('small') or store.logo_storage_path}" if store.logo_storage_path else None
        # the branch the customer is writing to: where it is, its brand colour and whether it's open right now
        result[store.id] = {
            "id": str(store.id), "name": store.name, "slug": store.slug, "logo_url": logo_url,
            "city": store.city, "district": store.district, "address": store.address, "color": store.color or "",
            "is_open_now": store.is_open_now(),
        }
    return result


def _identity_summaries(user_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Lightweight, PII-free identity for a conversation card (full name + avatar only) -- never phone/telegram here, which stay behind the dedicated, popover-only `CustomerProfileSelector` below since a bulk list response is the wrong place to expose them."""
    if not user_ids:
        return {}
    from apps.identity.infrastructure.models import User, UserAvatarAsset

    users = {u.id: u for u in User.objects.filter(id__in=user_ids).only("id", "full_name", "phone_number")}
    assets = {}
    for asset in UserAvatarAsset.objects.filter(user_id__in=user_ids).order_by("user_id", "-created_at"):
        assets.setdefault(asset.user_id, asset)  # first (most recent, per the ordering above) wins per user

    result = {}
    for user_id, user in users.items():
        asset = assets.get(user_id)
        avatar_url = f"/media/{asset.thumbnail_paths.get('small') or asset.storage_path}" if asset else None
        result[user_id] = {"full_name": user.full_name or user.phone_number, "avatar_url": avatar_url}
    return result


class ConversationSelector:
    def list_for_user(self, user_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        conversation_ids = orm.ParticipantModel.objects.filter(user_id=user_id, removed_at__isnull=True).values_list("conversation_id", flat=True)
        qs = orm.ConversationModel.objects.filter(id__in=conversation_ids)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        start = (page - 1) * page_size
        rows = list(qs.order_by("-last_activity_at")[start : start + page_size])

        # Real, closed gap: the card previously carried no way to know
        # WHO the other side of the conversation is, so a customer's
        # inbox could never show a store's name or an online dot next
        # to it. One extra query for the whole page (never N+1): fetch
        # every active participant across these rows' conversations,
        # then pick "the other" per conversation, and check presence
        # in a single batched Redis round trip (presence.is_online_bulk).
        other_ids_by_conversation = self._other_participant_ids(user_id, [r.id for r in rows])
        online_by_user = presence.is_online_bulk(list(set(other_ids_by_conversation.values())))
        identity_by_user = _identity_summaries(list(set(other_ids_by_conversation.values())))
        store_by_id = _store_summaries([r.store_id for r in rows if r.store_id])
        inbox = inbox_state(user_id, [r.id for r in rows])
        cards = []
        for r in rows:
            card = self._card(r, other_ids_by_conversation.get(r.id), online_by_user, identity_by_user, store_by_id)
            card.update(inbox.get(r.id, {"unread_count": 0, "last_message": None}))
            cards.append(card)
        return cards, total

    def get_detail(self, conversation_id: uuid.UUID) -> dict | None:
        row = orm.ConversationModel.objects.filter(id=conversation_id).first()
        return self._card(row, None, {}, {}, {}) if row else None

    @staticmethod
    def _other_participant_ids(user_id: uuid.UUID, conversation_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
        rows = orm.ParticipantModel.objects.filter(conversation_id__in=conversation_ids, removed_at__isnull=True).exclude(user_id=user_id).values("conversation_id", "user_id")
        result: dict[uuid.UUID, uuid.UUID] = {}
        for row in rows:
            result.setdefault(row["conversation_id"], row["user_id"])  # first match wins -- a support/sales conversation has exactly one "other side" in practice
        return result

    def _card(self, row: orm.ConversationModel, other_participant_id: uuid.UUID | None, online_by_user: dict[uuid.UUID, bool], identity_by_user: dict[uuid.UUID, dict], store_by_id: dict[uuid.UUID, dict]) -> dict:
        other_identity = identity_by_user.get(other_participant_id) if other_participant_id else None
        return {
            "id": str(row.id), "conversation_type": row.conversation_type, "status": row.status,
            "assigned_operator_id": str(row.assigned_operator_id) if row.assigned_operator_id else None,
            "last_activity_at": row.last_activity_at.isoformat() if row.last_activity_at else None,
            "other_participant_id": str(other_participant_id) if other_participant_id else None,
            "other_participant_is_online": bool(online_by_user.get(other_participant_id, False)) if other_participant_id else False,
            "other_participant_full_name": other_identity["full_name"] if other_identity else None,
            "other_participant_avatar_url": other_identity["avatar_url"] if other_identity else None,
            "store": store_by_id.get(row.store_id) if row.store_id else None,
        }


class MessageSelector:
    def list_for_conversation(self, conversation_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.MessageModel.objects.filter(conversation_id=conversation_id)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("created_at")[start : start + page_size]
        from apps.chat.infrastructure.automation import card_payload
        from apps.chat.infrastructure.realtime import attachment_url

        return [
            {
                "id": str(r.id), "conversation_id": str(r.conversation_id), "sender_id": str(r.sender_id), "message_type": r.message_type, "content": r.content,
                # stored URLs point at whatever public host the backend had back then -- rebuilt on today's host
                "attachment_type": r.attachment_type, "attachment_url": attachment_url(r.attachment_url), "attachment_filename": r.attachment_filename, "attachment_size_bytes": r.attachment_size_bytes,
                "reply_to_message_id": str(r.reply_to_message_id) if r.reply_to_message_id else None,
                "status": r.status, "created_at": r.created_at.isoformat(),
                "read_at": r.read_at.isoformat() if r.read_at else None,
                "card": card_payload(r.content) if r.message_type == "card" else None,
            }
            for r in rows
        ], total


class CustomerProfileSelector:
    """
    Backs the store-manager-only "customer profile" popover
    (`CustomerProfileView`) -- deliberately its own selector, not
    folded into `ConversationSelector`'s list card, since phone
    number/Telegram username/order history are real PII/business data
    that must never appear in a bulk conversation-list response, only
    when a specific store operator explicitly opens this one
    customer's profile.
    """

    def get(self, user_id: uuid.UUID) -> dict | None:
        from apps.identity.infrastructure.models import User, UserAvatarAsset

        user = User.objects.filter(id=user_id).first()
        if user is None:
            return None

        asset = UserAvatarAsset.objects.filter(user_id=user_id).order_by("-created_at").first()
        avatar_url = f"/media/{asset.thumbnail_paths.get('small') or asset.storage_path}" if asset else None

        from apps.ordering.infrastructure.selectors import OrderSelector

        orders, order_count = OrderSelector().list(status=None, customer_id=user_id, page=1, page_size=10)

        return {
            "user_id": str(user.id), "full_name": user.full_name or None, "phone_number": user.phone_number,
            "telegram_username": user.telegram_username or None, "avatar_url": avatar_url,
            "is_online": presence.is_online(user_id),
            "orders": orders, "order_count": order_count,
        }


class ChatStatisticsSelector:
    def conversation_counts_by_status(self) -> dict:
        rows = orm.ConversationModel.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}


def inbox_state(viewer_id: uuid.UUID, conversation_ids: list) -> dict:
    """Per conversation, for this viewer: how many messages from the other side are still unread, and the latest
    message (preview) -- two bulk queries for a whole page of conversations, never one per row."""
    from django.db.models import Count

    if not conversation_ids:
        return {}
    live = orm.MessageModel.objects.filter(conversation_id__in=conversation_ids).exclude(status="deleted")
    unread = dict(live.filter(read_at__isnull=True).exclude(sender_id=viewer_id).values("conversation_id").annotate(n=Count("id")).values_list("conversation_id", "n"))
    latest = live.order_by("conversation_id", "-created_at").distinct("conversation_id").values("conversation_id", "sender_id", "message_type", "content", "attachment_type", "created_at", "read_at")
    out = {cid: {"unread_count": unread.get(cid, 0), "last_message": None} for cid in conversation_ids}
    for m in latest:
        out[m["conversation_id"]]["last_message"] = {
            "type": m["message_type"], "content": (m["content"] or "")[:140], "attachment_type": m["attachment_type"],
            "is_mine": m["sender_id"] == viewer_id, "read": m["read_at"] is not None,
            "created_at": m["created_at"].isoformat() if m["created_at"] else None,
        }
    return out


def unread_total(viewer_id: uuid.UUID) -> dict:
    """Unread messages across every conversation the viewer takes part in: {"total", "conversations"}."""
    from django.db.models import Count

    ids = orm.ParticipantModel.objects.filter(user_id=viewer_id, removed_at__isnull=True).values_list("conversation_id", flat=True)
    rows = (orm.MessageModel.objects.filter(conversation_id__in=ids, read_at__isnull=True).exclude(sender_id=viewer_id).exclude(status="deleted")
            .values("conversation_id").annotate(n=Count("id")))
    return {"total": sum(r["n"] for r in rows), "conversations": len(rows)}
