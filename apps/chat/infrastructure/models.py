"""
Chat ORM models.

Mirrors Phase 1's 2 aggregates (`Conversation`, `Message`) plus the 1
owned entity (`Participant`) exactly -- 3 base tables + 1 Outbox
table. `ConversationModel` and `MessageModel` both use `SoftDeleteModel`
-- **a deliberate, disclosed distinction from every prior "aggregate
root gets SoftDeleteModel, owned append-only child gets plain Model"
pattern**: `MessageModel` gets `SoftDeleteModel` too, not the plain-
Model treatment `WalletLedgerEntryModel`/`TierChangeEntryModel` get,
because `Message` is genuinely its own certified aggregate root (not
an owned entity) AND genuinely supports real mutation (`edit()`) and
soft-deletion (`delete()`) -- unlike an append-only ledger entry,
which is never mutated once created. `ParticipantModel` IS the
append-only-shaped owned entity here (never independently mutated
except its own `removed_at` field), so it correctly gets the plain-
Model treatment.

`MessageModel.conversation_id` is a plain `UUIDField`, NOT a
`ForeignKey` -- matching the verified, established precedent from
Wallet's own intra-module cross-aggregate reference
(`CashbackModel.wallet_id`, confirmed a plain `UUIDField` during this
phase's own Step 1), not the more permissive FK option this phase's
own brief allowed. `ParticipantModel`, being genuinely owned BY
Conversation (not a separate aggregate), correctly uses a real
`ForeignKey`, matching `WalletLedgerEntryModel.wallet`'s identical
owned-entity pattern.
"""
from __future__ import annotations

import datetime
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.chat.domain.enums import AttachmentType, ConversationStatus, ConversationType, MessageStatus, MessageType, ParticipantRole
from common.models import SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class ConversationModel(SoftDeleteModel):
    conversation_type = models.CharField(**enum_field_kwargs(ConversationType))
    status = models.CharField(default=ConversationStatus.OPEN.value, db_index=True, **enum_field_kwargs(ConversationStatus))
    version = models.PositiveIntegerField(default=1)
    assigned_operator_id = models.UUIDField(null=True, blank=True, db_index=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)
    store_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "chat_conversations"
        verbose_name=_("Conversation")
        verbose_name_plural = _("Conversations")
        indexes = [models.Index(fields=["status", "conversation_type"]), models.Index(fields=["assigned_operator_id", "status"])]
        constraints = [models.CheckConstraint(condition=models.Q(version__gte=1), name="ck_chat_conversations_version_at_least_one")]

    def __str__(self) -> str:  # pragma: no cover
        return f"Conversation({self.id}, {self.conversation_type})"


class ParticipantModel(models.Model):
    """Owned, non-root entity -- see this module's own docstring for why this (not Message) gets the plain-Model treatment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(ConversationModel, on_delete=models.CASCADE, related_name="participants")
    user_id = models.UUIDField(db_index=True)
    role = models.CharField(**enum_field_kwargs(ParticipantRole))
    joined_at = models.DateTimeField()
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_participants"
        indexes = [models.Index(fields=["conversation", "user_id"])]


class MessageModel(SoftDeleteModel):
    """
    `message_deleted_at` (not `deleted_at`) is deliberate, not a
    typo: `SoftDeleteMixin` (via `SoftDeleteModel`) already provides
    its own `is_deleted`/`deleted_at`/`deleted_by` fields for the
    framework-level soft-delete mechanism (triggered by calling
    `.delete()` on the Django model instance itself). That is a
    completely separate concept from Domain's own `Message.status ==
    DELETED` state transition (triggered by the aggregate's own
    `delete()` method) -- this module never calls the ORM's
    `.delete()` for a Domain-level message deletion; the repository
    always uses `update_or_create()` to persist `status=deleted` and
    `message_deleted_at`, leaving the framework-level soft-delete
    fields untouched and reserved for genuine administrative hard-
    removal scenarios in the future, matching `SoftDeleteMixin`'s own
    documented "hard delete must always be a conscious, distinct
    action" rule.
    """

    conversation_id = models.UUIDField(db_index=True)
    sender_id = models.UUIDField(db_index=True)
    message_type = models.CharField(**enum_field_kwargs(MessageType))
    content = models.TextField(null=True, blank=True)
    attachment_type = models.CharField(null=True, blank=True, **enum_field_kwargs(AttachmentType))
    attachment_url = models.URLField(max_length=1000, null=True, blank=True)
    attachment_filename = models.CharField(max_length=255, null=True, blank=True)
    attachment_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    reply_to_message_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(default=MessageStatus.SENT.value, db_index=True, **enum_field_kwargs(MessageStatus))
    version = models.PositiveIntegerField(default=1)
    edited_at = models.DateTimeField(null=True, blank=True)
    message_deleted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_messages"
        verbose_name=_("Message")
        verbose_name_plural = _("Messages")
        indexes = [models.Index(fields=["conversation_id", "created_at"]), models.Index(fields=["sender_id"])]
        constraints = [models.CheckConstraint(condition=models.Q(version__gte=1), name="ck_chat_messages_version_at_least_one")]

    def __str__(self) -> str:  # pragma: no cover
        return f"Message({self.id}, {self.message_type})"


class ChatOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "chat_outbox_events"
        ordering = ["created_at"]


# ---------------------------------------------------------------- support desk settings & automation (Chat markazi)


def _default_work_days() -> list:
    return [0, 1, 2, 3, 4, 5]  # Monday..Saturday (datetime.weekday())


def _default_auto_reply() -> dict:
    return {
        "uz": "Assalomu alaykum! Hozir ish vaqtimizdan tashqari. Savolingizni qoldiring — ish vaqti boshlanishi bilan javob beramiz.",
        "ru": "Здравствуйте! Сейчас нерабочее время. Оставьте вопрос — ответим, как только начнётся рабочий день.",
        "en": "Hello! We're outside working hours right now. Leave your question and we'll reply as soon as we're back.",
    }


class ChatSettings(models.Model):
    """Singleton: working hours, the out-of-hours auto-reply, the staff Telegram alert for unanswered chats and the satisfaction rating."""

    work_start = models.TimeField(_("Ish boshlanishi"), default=datetime.time(9, 0))
    work_end = models.TimeField(_("Ish tugashi"), default=datetime.time(21, 0))
    work_days = models.JSONField(_("Ish kunlari"), default=_default_work_days, blank=True)
    auto_reply_enabled = models.BooleanField(_("Ish vaqtidan tashqari avtomatik javob"), default=True)
    auto_reply_text = models.JSONField(_("Avtomatik javob matni"), default=_default_auto_reply, blank=True)
    alert_enabled = models.BooleanField(_("Javobsiz suhbat haqida Telegram xabari"), default=True)
    alert_after_minutes = models.PositiveIntegerField(_("Necha daqiqadan keyin ogohlantirish"), default=10)
    alert_only_work_hours = models.BooleanField(_("Faqat ish vaqtida ogohlantirish"), default=True)
    rating_enabled = models.BooleanField(_("Suhbat yopilgach baho so'rash"), default=True)
    low_rating_alert = models.BooleanField(_("Past baho (1–2 ★) haqida menejerga Telegram xabari"), default=True)
    order_bot_enabled = models.BooleanField(_("\"Buyurtmam qayerda?\" savoliga bot javobi"), default=True)
    delivery_days = models.PositiveSmallIntegerField(_("Yetkazish muddati (kun)"), default=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_settings"
        verbose_name = _("Chat sozlamalari")
        verbose_name_plural = _("Chat sozlamalari")

    def __str__(self) -> str:
        return "Chat sozlamalari"

    @classmethod
    def load(cls) -> "ChatSettings":
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            obj.refresh_from_db()  # typed values (time, JSON) exactly as stored
        return obj


class ChatQuickReply(models.Model):
    """A canned answer staff insert in the Chat markazi with one click."""

    title = models.CharField(_("Qisqa nom"), max_length=60)
    text = models.TextField(_("Matn"), max_length=1000)
    sort_order = models.PositiveIntegerField(_("Tartib"), default=0)
    is_active = models.BooleanField(_("Faol"), default=True)
    uses = models.PositiveIntegerField(_("Ishlatilgan"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_quick_replies"
        ordering = ["sort_order", "title"]
        verbose_name = _("Tayyor javob")
        verbose_name_plural = _("Tayyor javoblar")

    def __str__(self) -> str:
        return self.title


class ConversationRating(models.Model):
    """The customer's 1–5 ★ satisfaction score for a closed support conversation -- one per closing (a support chat is reused and can be reopened)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(ConversationModel, on_delete=models.CASCADE, related_name="ratings", verbose_name=_("Suhbat"))  # one per closing
    customer_id = models.UUIDField(db_index=True)
    operator_id = models.UUIDField(null=True, blank=True, db_index=True)
    score = models.PositiveSmallIntegerField(_("Baho"))
    comment = models.CharField(_("Izoh"), max_length=500, blank=True)
    # a low score (1–2 ★) puts the chat under review ("nazoratda") until a manager marks it resolved
    review_status = models.CharField(_("Nazorat"), max_length=10, blank=True, default="", db_index=True, choices=[("", "—"), ("open", _("Nazoratda")), ("resolved", _("Hal qilindi"))])
    review_note = models.CharField(_("Menejer izohi"), max_length=500, blank=True)
    reviewed_by = models.CharField(_("Kim hal qildi"), max_length=150, blank=True)
    reviewed_at = models.DateTimeField(_("Hal qilingan vaqt"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "chat_conversation_ratings"
        verbose_name = _("Suhbat bahosi")
        verbose_name_plural = _("Suhbat baholari")
        constraints = [models.CheckConstraint(condition=models.Q(score__gte=1) & models.Q(score__lte=5), name="ck_chat_rating_1_to_5")]

    def __str__(self) -> str:
        return f"{self.score}★"


class ChatAutomationLog(models.Model):
    """One row per automatic action (staff alert, auto-reply, rating request) so none is ever sent twice for the same trigger."""

    kind = models.CharField(max_length=20, db_index=True)  # alert | auto_reply | rating_request | order_bot | low_rating
    ref = models.CharField(max_length=80)  # the triggering message / conversation id (+ window)
    conversation_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "chat_automation_log"
        constraints = [models.UniqueConstraint(fields=["kind", "ref"], name="uq_chat_automation_kind_ref")]


class ConversationClosing(models.Model):
    """Every time a support chat is closed, credited to the operator it was assigned to -- the "closed chats" column of the operator report."""

    conversation = models.ForeignKey(ConversationModel, on_delete=models.CASCADE, related_name="closings")
    operator_id = models.UUIDField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "chat_conversation_closings"
        ordering = ["-closed_at"]
