"""
Loyalty tiers, customer wallets and the wallet ledger.

Money model: 1 so'm of qualifying spend = 1 coin at the tier's percent,
coins are whole numbers (BigInteger). `Wallet.balance` is a cached sum
of the ledger, updated only inside the same transaction that writes a
`WalletTransaction` (see services.py) and guarded by a DB check that it
never goes negative.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.loyalty.domain.tiers import TierRule


class TierIcon(models.TextChoices):
    """The emblem the storefront draws for a tier (see the frontend's TierBadge) -- a fixed, designed set of metallic badges rather than an uploaded image, so every tier looks consistent in both themes. Ordered from entry level to the very top."""

    BRONZE = "bronze", _("Bronze medal")
    SILVER = "silver", _("Silver medal")
    GOLD = "gold", _("Gold laurel medal")
    PLATINUM = "platinum", _("Platinum rosette")
    DIAMOND = "diamond", _("Brilliant-cut diamond")
    ELITE = "elite", _("Elite winged shield")
    LEGEND = "legend", _("Legend flame crest")
    VIP = "vip", _("VIP jewelled crown")


class LoyaltyTier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=64)
    slug = models.SlugField(_("Slug"), max_length=64, unique=True)
    min_spend = models.DecimalField(
        _("Minimum total spend (UZS)"), max_digits=16, decimal_places=0, validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Inclusive. The customer's lifetime total of delivered/completed orders must be at least this amount."),
    )
    max_spend = models.DecimalField(
        _("Maximum total spend (UZS)"), max_digits=16, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(Decimal("1"))],
        help_text=_("Exclusive. Leave empty for the top, open-ended tier."),
    )
    percent = models.DecimalField(
        _("Cashback %"), max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_("Share of every qualifying order returned as coins (1 so'm = 1 coin)."),
    )
    icon = models.CharField(_("Icon"), max_length=16, choices=TierIcon.choices, default=TierIcon.BRONZE)
    color = models.CharField(
        _("Accent colour"), max_length=7, default="#b87333", validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a hex colour like #b87333."))],
    )
    description = models.CharField(_("Short description"), max_length=255, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loyalty_tiers"
        ordering = ["min_spend"]
        verbose_name = _("Loyalty tier")
        verbose_name_plural = _("Loyalty tiers")
        constraints = [
            models.CheckConstraint(condition=models.Q(max_spend__isnull=True) | models.Q(max_spend__gt=models.F("min_spend")), name="ck_loyalty_tier_range"),
            models.CheckConstraint(condition=models.Q(percent__gte=0) & models.Q(percent__lte=100), name="ck_loyalty_tier_percent"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.percent}%)"

    def to_rule(self) -> TierRule:
        return TierRule(slug=self.slug, name=self.name, min_spend=self.min_spend, max_spend=self.max_spend, percent=self.percent)

    def clean(self) -> None:
        super().clean()
        if self.max_spend is not None and self.min_spend is not None and self.max_spend <= self.min_spend:
            raise ValidationError({"max_spend": _("Must be greater than the minimum spend.")})
        # The changelist's bulk editor validates the whole ladder at once (see
        # LoyaltyTierAdmin) -- comparing one row against not-yet-saved neighbours
        # would wrongly reject a valid multi-row shift.
        if getattr(self, "_skip_overlap_check", False) or not self.is_active or self.min_spend is None:
            return
        # A customer must land in exactly one tier -- reject overlapping active ranges.
        mine_max = self.max_spend
        for other in LoyaltyTier.objects.filter(is_active=True).exclude(pk=self.pk):
            other_max = other.max_spend
            starts_before_other_ends = other_max is None or self.min_spend < other_max
            other_starts_before_mine_ends = mine_max is None or other.min_spend < mine_max
            if starts_before_other_ends and other_starts_before_mine_ends:
                raise ValidationError(_("This range overlaps the active tier “%(name)s”. Tier ranges must not overlap.") % {"name": other.name})


class Wallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField("identity.User", on_delete=models.PROTECT, related_name="wallet", verbose_name=_("Customer"))
    balance = models.BigIntegerField(_("Balance (coins)"), default=0)
    lifetime_earned = models.BigIntegerField(_("Lifetime earned"), default=0)
    lifetime_spent = models.BigIntegerField(_("Lifetime spent"), default=0)
    # A superadmin can pin the customer to a tier (VIP guest, partner, a correction)
    # regardless of spend; empty = the tier follows the customer's spend as usual.
    tier_override = models.ForeignKey(
        "loyalty.LoyaltyTier", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("Manual tier"),
        help_text=_("Leave empty to let the tier follow the customer's spend."),
    )
    tier_override_reason = models.CharField(_("Manual tier reason"), max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loyalty_wallets"
        verbose_name = _("Wallet")
        verbose_name_plural = _("Wallets")
        constraints = [models.CheckConstraint(condition=models.Q(balance__gte=0), name="ck_loyalty_wallet_balance_non_negative")]

    def __str__(self) -> str:
        return f"{self.user} — {self.balance:,} coins"


class WalletTransactionKind(models.TextChoices):
    # credits (+) -- each credit is a "lot" with its own expiry and `remaining`
    EARN = "earn", _("Earned (order cashback)")
    REFERRAL = "referral", _("Referral bonus")
    REFUND = "refund", _("Refund (order with coin payment cancelled)")
    ADJUSTMENT = "adjustment", _("Manual adjustment")
    # debits (−) -- consume lots first-to-expire-first (FIFO), recorded in `allocations`
    SPEND = "spend", _("Spent at checkout")
    REVERSAL = "reversal", _("Reversed (order cancelled/returned)")
    EXPIRY = "expiry", _("Expired")


ORDER_SCOPED_KINDS = ("earn", "reversal", "spend", "refund")


class WalletTransaction(models.Model):
    """
    One immutable ledger row per coin movement. `amount` is signed (+ credit,
    − debit); `balance_after` makes every statement line self-verifying.

    Credits are *lots*: `remaining` is how much of the lot is still unspent
    and `expires_at` when that remainder burns. Debits consume lots
    soonest-to-expire first and record exactly which lots they drew from in
    `allocations` ([{"lot": id, "amount": n}]) -- so a cancelled order's coin
    payment can be returned to the very lots it came from. Invariant:
    Wallet.balance == Σ remaining of the wallet's credit rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="transactions")
    kind = models.CharField(max_length=16, choices=WalletTransactionKind.choices, db_index=True)
    amount = models.BigIntegerField(_("Amount (coins)"))
    balance_after = models.BigIntegerField(_("Balance after"))
    remaining = models.BigIntegerField(_("Unspent (lot)"), default=0)
    expires_at = models.DateTimeField(_("Expires at"), null=True, blank=True, db_index=True)
    expiry_notified_at = models.DateTimeField(null=True, blank=True)
    allocations = models.JSONField(default=list, blank=True)
    order_id = models.UUIDField(null=True, blank=True, db_index=True)
    order_number = models.CharField(max_length=64, blank=True)
    order_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    referral = models.ForeignKey("loyalty.Referral", on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    tier_slug = models.CharField(max_length=64, blank=True)
    tier_name = models.CharField(max_length=64, blank=True)
    tier_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.UUIDField(null=True, blank=True)
    # Dashboard staff (Django auth users) who made a manual movement -- the audit trail's "who".
    actor = models.CharField(_("Changed by"), max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "loyalty_wallet_transactions"
        ordering = ["-created_at"]
        verbose_name = _("Wallet transaction")
        verbose_name_plural = _("Wallet transactions")
        constraints = [
            # Exactly-once per order and kind, no matter how many times a signal/reconcile run sees it.
            models.UniqueConstraint(fields=["order_id", "kind"], condition=models.Q(order_id__isnull=False, kind__in=list(ORDER_SCOPED_KINDS)), name="uq_loyalty_tx_order_kind"),
            # A referral pays each side exactly once.
            models.UniqueConstraint(fields=["referral", "wallet"], condition=models.Q(referral__isnull=False), name="uq_loyalty_tx_referral_wallet"),
            models.CheckConstraint(condition=~models.Q(amount=0), name="ck_loyalty_tx_amount_non_zero"),
            models.CheckConstraint(condition=models.Q(remaining__gte=0), name="ck_loyalty_tx_remaining_non_negative"),
        ]
        indexes = [
            models.Index(fields=["wallet", "-created_at"]),
            models.Index(fields=["wallet", "expires_at"], condition=models.Q(remaining__gt=0), name="loyalty_open_lots_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount:+,}"


class LoyaltySettings(models.Model):
    """Singleton (pk=1) -- every programme rule staff can tune from the dashboard without a deploy."""

    tier_window_days = models.PositiveIntegerField(
        _("Tier qualification window (days)"), default=365,
        help_text=_("A customer's tier is based on delivered orders placed within this many days (rolling). 0 = lifetime."),
    )
    coin_expiry_days = models.PositiveIntegerField(
        _("Coin lifetime (days)"), default=365,
        help_text=_("Each batch of earned coins burns this many days after it was credited if not spent. 0 = never expire."),
    )
    expiry_reminder_days = models.PositiveIntegerField(_("Expiry reminder (days before)"), default=7)
    max_redeem_percent = models.PositiveIntegerField(
        _("Max order share payable with coins (%)"), default=30, validators=[MaxValueValidator(100)],
        help_text=_("1 coin = 1 so'm. Customers can cover at most this share of an order's total with coins."),
    )
    min_redeem_coins = models.PositiveIntegerField(_("Minimum coins per redemption"), default=1000)
    redeem_enabled = models.BooleanField(_("Coin payment at checkout enabled"), default=True)
    referral_enabled = models.BooleanField(_("Referral programme enabled"), default=True)
    referrer_reward = models.PositiveIntegerField(_("Referrer reward (coins)"), default=5000)
    referee_reward = models.PositiveIntegerField(_("New customer reward (coins)"), default=5000)
    referral_min_order = models.DecimalField(
        _("Referral: minimum first order (UZS)"), max_digits=16, decimal_places=0, default=Decimal("0"),
        help_text=_("Rewards are paid when the invited friend's first order is delivered and totals at least this amount."),
    )
    subscribe_gift_coins = models.PositiveIntegerField(
        _("News subscription gift (coins)"), default=10000,
        help_text=_("Coins a customer gets once, on their first purchase after subscribing to news in the Telegram bot. 0 = no gift."),
    )
    telegram_notifications = models.BooleanField(_("Telegram notifications"), default=True, help_text=_("Coins earned, tier upgrades, referral bonuses and expiry reminders."))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loyalty_settings"
        verbose_name = _("Programme settings")
        verbose_name_plural = _("Programme settings")

    def __str__(self) -> str:
        return str(_("Loyalty programme settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> LoyaltySettings:
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class ReferralCode(models.Model):
    """Each customer's personal, shareable invite code (created lazily on first view)."""

    user = models.OneToOneField("identity.User", on_delete=models.CASCADE, related_name="referral_code")
    code = models.CharField(max_length=16, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "loyalty_referral_codes"
        verbose_name = _("Referral code")
        verbose_name_plural = _("Referral codes")

    def __str__(self) -> str:
        return self.code


class ReferralStatus(models.TextChoices):
    PENDING = "pending", _("Waiting for first delivered order")
    REWARDED = "rewarded", _("Rewarded")
    VOID = "void", _("Void")


class Referral(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey("identity.User", on_delete=models.CASCADE, related_name="referrals_made")
    referee = models.OneToOneField("identity.User", on_delete=models.CASCADE, related_name="referred_by")
    code = models.CharField(max_length=16)
    channel = models.CharField(max_length=16, default="web")  # web | telegram | manual
    status = models.CharField(max_length=16, choices=ReferralStatus.choices, default=ReferralStatus.PENDING, db_index=True)
    qualifying_order_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    rewarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "loyalty_referrals"
        ordering = ["-created_at"]
        verbose_name = _("Referral")
        verbose_name_plural = _("Referrals")
        constraints = [models.CheckConstraint(condition=~models.Q(referrer=models.F("referee")), name="ck_loyalty_referral_not_self")]

    def __str__(self) -> str:
        return f"{self.referrer} → {self.referee}"


class TierChangeKind(models.TextChoices):
    AUTO = "auto", _("Automatic (spend)")
    MANUAL = "manual", _("Set by admin")
    CLEARED = "cleared", _("Manual tier removed")


class TierChange(models.Model):
    """Append-only tier history: every automatic level-up and every manual tier change, with who, when and why."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="tier_changes")
    kind = models.CharField(_("Kind"), max_length=8, choices=TierChangeKind.choices)
    from_tier = models.CharField(_("From"), max_length=64, blank=True)
    to_tier = models.CharField(_("To"), max_length=64, blank=True)
    reason = models.CharField(_("Reason"), max_length=255, blank=True)
    actor = models.CharField(_("Changed by"), max_length=150, blank=True)
    created_at = models.DateTimeField(_("When"), auto_now_add=True, db_index=True)

    class Meta:
        db_table = "loyalty_tier_changes"
        ordering = ["-created_at"]
        verbose_name = _("Tier change")
        verbose_name_plural = _("Tier history")

    def __str__(self) -> str:
        return f"{self.from_tier or '—'} → {self.to_tier or '—'}"
