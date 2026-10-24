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
    engine = models.CharField(_("Dvigatel"), max_length=12, default="claude")  # claude / local (free NutriZone advisor)
    meta = models.JSONField(default=dict, blank=True)  # local advisor: the shopper's profile (height, weight, goal...) and last intent
    created_at = models.DateTimeField(_("Boshlangan"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Oxirgi faollik"), auto_now=True, db_index=True)

    class Meta:
        db_table = "assistant_conversations"
        ordering = ["-updated_at"]
        verbose_name = _("AI suhbat")
        verbose_name_plural = _("AI suhbatlar")

    def __str__(self) -> str:  # pragma: no cover
        return self.last_message or str(self.id)


class AdvisorSignal(models.Model):
    """What the free advisor learned about one product: shown in answers, 👍 / 👎, added to cart, bought afterwards."""

    product_id = models.UUIDField(primary_key=True)
    shown = models.PositiveIntegerField(default=0)
    liked = models.PositiveIntegerField(default=0)
    disliked = models.PositiveIntegerField(default=0)
    carted = models.PositiveIntegerField(default=0)
    purchased = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assistant_advisor_signals"
        verbose_name = _("Maslahatchi signali")
        verbose_name_plural = _("Maslahatchi signallari")


class KnowledgeEntry(models.Model):
    """
    AI bilimlar bazasi: what the shop teaches its assistant -- policies, FAQ, usage guidance, promotions, branch
    notes. Both engines read it: Claude through the search_knowledge tool, the free advisor by matching questions.
    """

    TOPICS = (
        ("faq", _("Ko'p so'raladigan savol")), ("policy", _("Qoida (yetkazish, to'lov, qaytarish)")), ("usage", _("Qo'llash bo'yicha maslahat")),
        ("product", _("Mahsulot / brend haqida")), ("promo", _("Aksiya")), ("branch", _("Filial haqida")), ("other", _("Boshqa")),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(_("Mavzu"), max_length=10, choices=TOPICS, default="faq", db_index=True)
    title = models.CharField(_("Sarlavha (o'zbekcha)"), max_length=200)
    questions = models.TextField(_("Savol shakllari"), blank=True, default="",
                                 help_text=_("Mijoz qanday so'rashi mumkin — har qatorda bittadan, istalgan tilda. Masalan: «yetkazib berish qancha turadi», «доставка сколько»."))
    answer_uz = models.TextField(_("Javob (o'zbekcha)"))
    answer_ru = models.TextField(_("Javob (ruscha)"), blank=True, default="")
    answer_en = models.TextField(_("Javob (inglizcha)"), blank=True, default="")
    keywords = models.CharField(_("Kalit so'zlar"), max_length=300, blank=True, default="", help_text=_("Vergul bilan: kreatin, dozasi, creatine"))
    priority = models.PositiveSmallIntegerField(_("Muhimlik"), default=50, help_text=_("0–100: bir nechta mos kelganda yuqorisi ustun."))
    is_active = models.BooleanField(_("Faol"), default=True, db_index=True)
    valid_until = models.DateField(_("Amal qiladi (gacha)"), null=True, blank=True, help_text=_("Aksiya kabi vaqtinchalik ma'lumot uchun."))
    uses = models.PositiveIntegerField(_("Ishlatilgan"), default=0)
    created_by = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assistant_knowledge"
        ordering = ("-priority", "title")
        verbose_name = _("AI bilim")
        verbose_name_plural = _("AI bilimlar bazasi")

    def __str__(self) -> str:
        return self.title

    def answer(self, locale: str) -> str:
        return {"ru": self.answer_ru, "en": self.answer_en}.get(locale) or self.answer_uz
