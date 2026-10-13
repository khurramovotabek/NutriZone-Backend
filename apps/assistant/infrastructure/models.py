"""
One customer conversation with the AI assistant.

`history` is the exact Messages-API conversation (user turns, assistant content blocks incl. thinking and tool_use,
tool results), APPEND-ONLY: Claude Opus 5.5 binds its thinking blocks to the conversation, so earlier turns are never
edited -- only new turns are added. `transcript` is what the customer saw (text + product cards), for the chat UI
and for staff review.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class AssistantConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_id = models.UUIDField(_("Mijoz"), null=True, blank=True, db_index=True)
    client_key = models.CharField(max_length=64, db_index=True)  # sha256 of the browser's anonymous id
    channel = models.CharField(_("Kanal"), max_length=16, default="web")
    locale = models.CharField(_("Til"), max_length=5, default="uz")
    history = models.JSONField(default=list, blank=True)
    transcript = models.JSONField(default=list, blank=True)
    turns = models.PositiveIntegerField(_("Savollar"), default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    products_shown = models.PositiveIntegerField(_("Ko'rsatilgan mahsulotlar"), default=0)
    feedback_up = models.PositiveSmallIntegerField(default=0)
    feedback_down = models.PositiveSmallIntegerField(default=0)
    last_message = models.CharField(_("Oxirgi savol"), max_length=300, blank=True, default="")
    errors = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(_("Boshlangan"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Oxirgi faollik"), auto_now=True, db_index=True)

    class Meta:
        db_table = "assistant_conversations"
        ordering = ["-updated_at"]
        verbose_name = _("AI suhbat")
        verbose_name_plural = _("AI suhbatlar")

    def __str__(self) -> str:  # pragma: no cover
        return self.last_message or str(self.id)
