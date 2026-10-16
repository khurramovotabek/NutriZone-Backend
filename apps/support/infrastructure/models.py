"""
Support CRM: one SupportCase per customer contact (a call, a walk-in, a Telegram question) with notes and a status
pipeline shown as a Kanban board. Logging a case for an unknown phone creates the customer account on the spot
(SupportProfile marks it as made by staff); when that person later registers in the Telegram bot with the same
number, the bot asks them to confirm the details staff wrote down.
"""
from __future__ import annotations

import uuid

from django.db import models


class CaseStatus(models.TextChoices):
    NEW = "new", "Yangi"
    THINKING = "thinking", "O'ylab ko'radi"
    CALLBACK = "callback", "Qayta qo'ng'iroq"
    ORDERED = "ordered", "Buyurtma berdi"
    RESOLVED = "resolved", "Hal qilindi"
    LOST = "lost", "Rad etdi"


OPEN_STATUSES = (CaseStatus.NEW, CaseStatus.THINKING, CaseStatus.CALLBACK)


class CaseTopic(models.TextChoices):
    PRODUCT = "product", "Mahsulot bo'yicha savol"
    PRICE = "price", "Narx / chegirma"
    ORDER = "order", "Buyurtma holati"
    DELIVERY = "delivery", "Yetkazib berish"
    COMPLAINT = "complaint", "Shikoyat"
    RETURN = "return", "Qaytarish / almashtirish"
    WHOLESALE = "wholesale", "Ulgurji / hamkorlik"
    OTHER = "other", "Boshqa"


class CaseChannel(models.TextChoices):
    CALL_IN = "call_in", "Kiruvchi qo'ng'iroq"
    CALL_OUT = "call_out", "Chiquvchi qo'ng'iroq"
    TELEGRAM = "telegram", "Telegram"
    WALK_IN = "walk_in", "Do'konga keldi"
    SITE = "site", "Sayt / chat"


class CasePriority(models.TextChoices):
    LOW = "low", "Past"
    NORMAL = "normal", "Oddiy"
    HIGH = "high", "Muhim"


class SupportCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField("Raqam", max_length=16, unique=True, editable=False)
    customer = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="support_cases", verbose_name="Mijoz")
    phone = models.CharField("Telefon", max_length=20, db_index=True)
    name = models.CharField("Ism", max_length=120, blank=True, default="", help_text="Bo'sh qolsa — «Noma'lum».")
    topic = models.CharField("Mavzu", max_length=16, choices=CaseTopic.choices, default=CaseTopic.PRODUCT, db_index=True)
    channel = models.CharField("Kanal", max_length=12, choices=CaseChannel.choices, default=CaseChannel.CALL_IN)
    status = models.CharField("Holat", max_length=12, choices=CaseStatus.choices, default=CaseStatus.NEW, db_index=True)
    priority = models.CharField("Muhimlik", max_length=8, choices=CasePriority.choices, default=CasePriority.NORMAL)
    summary = models.TextField("Nima haqida gaplashildi")
    products = models.ManyToManyField("products.Product", blank=True, related_name="+", verbose_name="Qiziqqan mahsulotlar")
    next_contact_at = models.DateTimeField("Keyingi aloqa", null=True, blank=True, db_index=True)
    order_number = models.CharField("Buyurtma", max_length=32, blank=True, default="")
    assigned_to = models.CharField("Mas'ul", max_length=150, blank=True, default="")
    created_by = models.CharField("Yozgan", max_length=150, blank=True, default="")
    created_at = models.DateTimeField("Yaratilgan", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_cases"
        ordering = ("-created_at",)
        verbose_name = "Murojaat"
        verbose_name_plural = "Murojaatlar"
        permissions = [("view_support_board", "Can view the support board")]

    def __str__(self) -> str:
        return f"{self.number} · {self.display_name}"

    @property
    def display_name(self) -> str:
        return self.name.strip() or "Noma'lum"


class SupportNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(SupportCase, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(max_length=12, default="note")  # note / status / call
    text = models.TextField()
    author = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "support_notes"
        ordering = ("created_at",)


class SupportProfile(models.Model):
    """A customer account staff created from a call: the bot asks the person to confirm it on first registration."""

    user = models.OneToOneField("identity.User", on_delete=models.CASCADE, primary_key=True, related_name="support_profile")
    created_by_support = models.BooleanField(default=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "support_profiles"
