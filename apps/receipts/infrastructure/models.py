"""
One registry of receipts (cheklar): POS sales (number/token shared with the POS slip), online orders and manual
receipts. `data` is a frozen snapshot in the same shape as apps.pos.infrastructure.receipts.receipt(), so the paper
slip, the public e-receipt (/r/<token>) and the dashboard always show the same thing even if the order changes later.
Fiscal fields hold what an OFD / virtual-kassa provider returns (fiscal sign, terminal, QR link to the tax site).
"""
from __future__ import annotations

import uuid

from django.db import models


class ReceiptSource(models.TextChoices):
    POS = "pos", "POS kassa"
    ONLINE = "online", "Onlayn buyurtma"
    MANUAL = "manual", "Qo'lda"


class ReceiptKind(models.TextChoices):
    SALE = "sale", "Sotuv"
    REFUND = "refund", "Qaytarish"


class ReceiptStatus(models.TextChoices):
    ISSUED = "issued", "Berilgan"
    FISCAL_PENDING = "fiscal_pending", "Fiskallashtirilmoqda"
    FISCALIZED = "fiscalized", "Fiskallashtirilgan"
    FISCAL_FAILED = "fiscal_failed", "Fiskal xato"
    CANCELLED = "cancelled", "Bekor qilingan"


class Receipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField("Chek raqami", max_length=24, unique=True)
    token = models.CharField(max_length=32, unique=True)
    source = models.CharField("Manba", max_length=8, choices=ReceiptSource.choices, db_index=True)
    kind = models.CharField("Turi", max_length=8, choices=ReceiptKind.choices, default=ReceiptKind.SALE)
    status = models.CharField("Holat", max_length=16, choices=ReceiptStatus.choices, default=ReceiptStatus.ISSUED, db_index=True)
    sale_id = models.UUIDField(null=True, blank=True, unique=True)
    order_id = models.UUIDField(null=True, blank=True, unique=True)
    order_number = models.CharField("Buyurtma", max_length=32, blank=True, default="", db_index=True)
    store_id = models.UUIDField(null=True, blank=True, db_index=True)
    customer_name = models.CharField("Mijoz", max_length=255, blank=True, default="")
    customer_phone = models.CharField("Telefon", max_length=32, blank=True, default="", db_index=True)
    total = models.DecimalField("Summa", max_digits=14, decimal_places=2, default=0)
    vat_amount = models.DecimalField("QQS", max_digits=14, decimal_places=2, default=0)
    payment_method = models.CharField("To'lov", max_length=32, blank=True, default="")
    data = models.JSONField(default=dict)
    issued_at = models.DateTimeField("Berilgan vaqt", db_index=True)
    created_by = models.CharField(max_length=150, blank=True, default="")
    printed = models.PositiveIntegerField("Chop etilgan", default=0)
    # fiscal (OFD / virtual kassa)
    fiscal_provider = models.CharField(max_length=24, blank=True, default="")
    fiscal_terminal_id = models.CharField("Terminal ID", max_length=64, blank=True, default="")
    fiscal_number = models.CharField("Fiskal raqam", max_length=64, blank=True, default="")
    fiscal_sign = models.CharField("Fiskal belgi", max_length=128, blank=True, default="")
    fiscal_url = models.URLField("Soliq QR havolasi", max_length=500, blank=True, default="")
    fiscalized_at = models.DateTimeField(null=True, blank=True)
    fiscal_error = models.TextField(blank=True, default="")
    fiscal_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "receipts"
        ordering = ("-issued_at",)
        verbose_name = "Chek"
        verbose_name_plural = "Cheklar"

    def __str__(self) -> str:
        return self.number


class ReceiptSettings(models.Model):
    """Dashboard → Cheklar → Sozlamalar (singleton): seller requisites on every receipt and the fiscal provider."""

    legal_name = models.CharField("Yuridik nom", max_length=200, blank=True, default="", help_text="Masalan: «NUTRIZONE» MChJ")
    tin = models.CharField("STIR (INN)", max_length=20, blank=True, default="")
    address = models.CharField("Yuridik manzil", max_length=255, blank=True, default="")
    phone = models.CharField("Telefon", max_length=32, blank=True, default="")
    vat_payer = models.BooleanField("QQS to'lovchisi", default=False)
    vat_rate = models.DecimalField("QQS stavkasi (%)", max_digits=5, decimal_places=2, default=12)
    footer = models.CharField("Pastki matn", max_length=255, blank=True, default="Xaridingiz uchun rahmat! NutriZone — original sport ozuqalari.")
    fiscal_provider = models.CharField("Fiskal provayder", max_length=24, default="none", choices=[
        ("none", "O'chirilgan (ichki chek)"), ("epos", "E-POS (api.epos.uz)"), ("http", "Boshqa virtual kassa / OFD (HTTP API)")])
    fiscal_endpoint = models.URLField("API manzili", blank=True, default="", help_text="Provayder (OFD / virtual kassa) chek qabul qiladigan URL.")
    fiscal_terminal_id = models.CharField("Terminal (kassa) ID", max_length=64, blank=True, default="")
    fiscal_auto = models.BooleanField("Avtomatik fiskallashtirish", default=False, help_text="Har bir yangi chek darhol provayderga yuboriladi.")
    fiscal_cashier_id = models.CharField("Kassir ID (E-POS)", max_length=64, blank=True, default="", help_text="E-POS kabinetidagi kassir identifikatori, masalan CSH-007.")
    payme_fiscal = models.BooleanField("Payme orqali fiskal chek", default=False, help_text=(
        "Payme bilan to'langan buyurtmalar uchun soliq cheki Payme virtual kassasi orqali chiqadi (QR kod bilan). "
        "Payme Business kabinetida fiskalizatsiya yoqilgan bo'lishi kerak."))
    fiscal_auth = models.CharField("Avtorizatsiya turi", max_length=12, default="bearer", choices=[
        ("bearer", "Bearer token (Authorization: Bearer …)"), ("header", "Token alohida sarlavhada"), ("basic", "Login + parol (Basic)")])
    fiscal_auth_header = models.CharField("Sarlavha nomi", max_length=64, blank=True, default="Authorization",
                                          help_text="«Token alohida sarlavhada» uchun, masalan X-API-Key.")
    fiscal_login = models.CharField("Login", max_length=128, blank=True, default="", help_text="Faqat «Login + parol» turida.")
    fiscal_secret_encrypted = models.TextField(blank=True, default="")  # the token / password, Fernet-encrypted (never shown back)
    fiscal_timeout = models.PositiveSmallIntegerField("Kutish vaqti (soniya)", default=20)
    fiscal_checked_at = models.DateTimeField(null=True, blank=True)
    fiscal_check_result = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "receipt_settings"
        verbose_name = "Chek sozlamalari"
        verbose_name_plural = "Chek sozlamalari"

    def __str__(self) -> str:
        return "Chek sozlamalari"

    @property
    def fiscal_secret(self) -> str:
        """The provider token / password: the one saved on the dashboard, else the server's FISCAL_API_TOKEN."""
        import os

        from apps.payment.infrastructure.crypto import decrypt_secrets

        return decrypt_secrets(self.fiscal_secret_encrypted).get("secret", "") or os.environ.get("FISCAL_API_TOKEN", "")

    def set_fiscal_secret(self, value: str) -> None:
        from apps.payment.infrastructure.crypto import encrypt_secrets

        self.fiscal_secret_encrypted = encrypt_secrets({"secret": value.strip()}) if value and value.strip() else ""

    @classmethod
    def get(cls) -> "ReceiptSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
