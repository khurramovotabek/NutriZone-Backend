"""
Finance models. Sales, supplier payments and payroll already live in their own apps; they reach the money accounts
automatically through `MoneyAccount.sources` (flows.py computes them live, nothing is copied). This app stores only
what the system can't know by itself: the accounts, manual income/expenses/transfers, expense categories and budgets.
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class AccountKind(models.TextChoices):
    CASH = "cash", _("Naqd kassa")
    BANK = "bank", _("Bank hisobi")
    CARD = "card", _("Korporativ karta")
    ONLINE = "online", _("Onlayn hamyon")
    OTHER = "other", _("Boshqa")


# Money the system records elsewhere, and which account it lands in / leaves from.
SOURCES = {
    "pos_cash": (_("Kassa savdosi: naqd"), "in"),
    "pos_card": (_("Kassa savdosi: Uzcard/Humo terminal"), "in"),
    "pos_qr": (_("Kassa savdosi: Click/Payme/Uzum"), "in"),
    "web_online": (_("Sayt: onlayn to'lov"), "in"),
    "web_cod": (_("Sayt: yetkazishda naqd"), "in"),
    "supplier_cash": (_("Yetkazib beruvchiga: naqd"), "out"),
    "supplier_bank": (_("Yetkazib beruvchiga: bank"), "out"),
    "supplier_card": (_("Yetkazib beruvchiga: karta"), "out"),
    "payroll": (_("Kassirlar ish haqi"), "out"),
}
POS_SOURCES = ("pos_cash", "pos_card", "pos_qr")


class MoneyAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Nomi"), max_length=120)
    kind = models.CharField(_("Turi"), max_length=10, choices=AccountKind.choices, default=AccountKind.CASH)
    store = models.ForeignKey("stores.Store", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("Filial"),
                              help_text=_("Kassa savdosi faqat shu filialdan olinadi. Bo'sh = barcha kassalar."))
    sources = models.JSONField(_("Avtomatik tushumlar"), default=list, blank=True)
    opening_balance = models.DecimalField(_("Boshlang'ich qoldiq"), max_digits=16, decimal_places=2, default=0)
    opening_date = models.DateField(_("Hisob boshlangan sana"), help_text=_("Avtomatik harakatlar shu kundan boshlab hisoblanadi."))
    color = models.CharField(_("Rang"), max_length=9, default="#2563eb")
    note = models.CharField(_("Izoh"), max_length=255, blank=True, default="")
    is_active = models.BooleanField(_("Faol"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("Tartib"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finance_accounts"
        ordering = ("sort_order", "name")
        verbose_name = _("Hisob")
        verbose_name_plural = _("Hisoblar")

    def __str__(self) -> str:
        return self.name

    def clean(self):
        unknown = [s for s in (self.sources or []) if s not in SOURCES]
        if unknown:
            raise ValidationError({"sources": _("Noma'lum manba: %(s)s") % {"s": ", ".join(unknown)}})
        if not self.is_active:
            return
        clash = []
        for other in MoneyAccount.objects.filter(is_active=True).exclude(pk=self.pk):
            for s in set(self.sources or []) & set(other.sources or []):
                # POS money can be split per branch; everything else goes to one account only
                if s in POS_SOURCES and self.store_id and other.store_id and self.store_id != other.store_id:
                    continue
                clash.append(f"{SOURCES[s][0]} → {other.name}")
        if clash:
            raise ValidationError({"sources": _("Bu tushumlar allaqachon boshqa hisobga yo'naltirilgan: %(c)s") % {"c": "; ".join(str(c) for c in clash)}})


class CategoryKind(models.TextChoices):
    EXPENSE = "expense", _("Xarajat")
    INCOME = "income", _("Kirim")


class PnlSection(models.TextChoices):
    OPEX = "opex", _("Operatsion xarajat")
    TAX = "tax", _("Soliq")
    OTHER_INCOME = "other_income", _("Boshqa daromad")
    CAPITAL = "capital", _("Kapital / qarz (foydaga kirmaydi)")


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Nomi"), max_length=120)
    kind = models.CharField(_("Turi"), max_length=10, choices=CategoryKind.choices, default=CategoryKind.EXPENSE)
    section = models.CharField(_("Hisobotdagi o'rni"), max_length=14, choices=PnlSection.choices, default=PnlSection.OPEX)
    icon = models.CharField(_("Belgi"), max_length=40, default="fa-tag", help_text="Font Awesome, masalan fa-house")
    color = models.CharField(_("Rang"), max_length=9, default="#64748b")
    is_active = models.BooleanField(_("Faol"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("Tartib"), default=0)

    class Meta:
        db_table = "finance_categories"
        ordering = ("kind", "sort_order", "name")
        verbose_name = _("Moliya moddasi")
        verbose_name_plural = _("Moliya moddalari")

    def __str__(self) -> str:
        return self.name


class TxKind(models.TextChoices):
    EXPENSE = "expense", _("Xarajat")
    INCOME = "income", _("Kirim")
    TRANSFER = "transfer", _("O'tkazma")


class Transaction(models.Model):
    """A manual money movement. Never deleted: a wrong one is voided (it then counts nowhere)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(_("Raqam"), max_length=20, unique=True)
    kind = models.CharField(_("Turi"), max_length=10, choices=TxKind.choices, db_index=True)
    occurred_on = models.DateField(_("Sana"), db_index=True)
    amount = models.DecimalField(_("Summa"), max_digits=16, decimal_places=2)
    account = models.ForeignKey(MoneyAccount, on_delete=models.PROTECT, related_name="transactions", verbose_name=_("Hisob"))
    to_account = models.ForeignKey(MoneyAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="transfers_in", verbose_name=_("Qaysi hisobga"))
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions", verbose_name=_("Modda"))
    store = models.ForeignKey("stores.Store", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("Filial"),
                              help_text=_("Xarajat qaysi filialga tegishli (ixtiyoriy)."))
    counterparty = models.CharField(_("Kontragent"), max_length=160, blank=True, default="")
    reference = models.CharField(_("Hujjat raqami"), max_length=60, blank=True, default="")
    note = models.CharField(_("Izoh"), max_length=255, blank=True, default="")
    created_by = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    voided_at = models.DateTimeField(_("Bekor qilingan"), null=True, blank=True)
    voided_by = models.CharField(max_length=150, blank=True, default="")
    void_reason = models.CharField(_("Bekor qilish sababi"), max_length=255, blank=True, default="")

    class Meta:
        db_table = "finance_transactions"
        ordering = ("-occurred_on", "-created_at")
        verbose_name = _("Operatsiya")
        verbose_name_plural = _("Operatsiyalar")
        indexes = [models.Index(fields=["account", "occurred_on"]), models.Index(fields=["category", "occurred_on"])]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_finance_tx_amount_positive")]
        permissions = [("void_transaction", "Can void finance operations")]

    def __str__(self) -> str:
        return self.number

    def clean(self):
        errors = {}
        if self.kind == TxKind.TRANSFER:
            if not self.to_account_id:
                errors["to_account"] = _("O'tkazma uchun qabul qiluvchi hisobni tanlang.")
            elif self.to_account_id == self.account_id:
                errors["to_account"] = _("Hisoblar har xil bo'lishi kerak.")
        else:
            if not self.category_id:
                errors["category"] = _("Moddani tanlang.")
            elif self.category and self.category.kind != self.kind:
                errors["category"] = _("Modda turi operatsiya turiga mos emas.")
        if errors:
            raise ValidationError(errors)


class BudgetLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.DateField(_("Oy"), db_index=True)  # the 1st of the month
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="budget_lines", verbose_name=_("Modda"))
    amount = models.DecimalField(_("Reja"), max_digits=16, decimal_places=2)

    class Meta:
        db_table = "finance_budget_lines"
        verbose_name = _("Budjet")
        verbose_name_plural = _("Budjet")
        constraints = [models.UniqueConstraint(fields=["month", "category"], name="uniq_finance_budget_month_category")]
