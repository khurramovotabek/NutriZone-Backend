"""
Loyalty reward & wallet services -- the single place coins move.

Money model
-----------
1 so'm = 1 coin. Every credit (earn / referral / refund / adjustment) is a
*lot* with `remaining` and `expires_at` (credited_at + coin_expiry_days).
Every debit (spend / reversal / expiry) consumes lots soonest-to-expire first
and records the lots it drew from in `allocations`. The wallet row is locked
(`select_for_update`) for every movement, and Wallet.balance always equals
Σ remaining of its lots.

Earning rule
------------
An order earns coins once it is delivered/completed, at the tier the customer
held BEFORE this order: tier = Σ fulfilled orders placed within the rolling
`tier_window_days` (365 by default; 0 = lifetime).

    coins = floor(order_amount × tier.percent / 100)

Order amount = Σ active lines (unit × qty − discount + tax) -- i.e. what was
actually paid, so coins spent at checkout never earn coins themselves.
A later cancel/return reverses the earn (never below zero) and returns any
coins that were spent on the order to the lots they came from.

Idempotency: partial unique indexes on (order_id, kind) and (referral, wallet)
mean a signal, a retry and the reconcile task can all see the same event and
at most one row per kind is written.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.loyalty.domain.tiers import TierRule, next_tier, resolve_tier, reward_coins
from apps.loyalty.infrastructure.models import (
    LoyaltySettings,
    LoyaltyTier,
    Referral,
    ReferralCode,
    ReferralStatus,
    TierChange,
    TierChangeKind,
    Wallet,
    WalletTransaction,
    WalletTransactionKind,
)

logger = logging.getLogger("nutrizone.app")

FULFILLED_STATUSES = ("delivered", "completed")
REVERSING_STATUSES = ("cancelled", "returned", "failed")
CREDIT_KINDS = (WalletTransactionKind.EARN, WalletTransactionKind.REFERRAL, WalletTransactionKind.REFUND, WalletTransactionKind.ADJUSTMENT)
REFUND_GRACE_DAYS = 30  # refunded coins whose original lot already expired get this long to be used again


class LoyaltyError(ValueError):
    """A business-rule rejection with a stable machine code (surfaced to the API as a 409 via as_conflict())."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def as_conflict(self):
        from common.exceptions import ConflictError

        err = ConflictError(str(self))
        err.code = self.code  # the storefront localises by this stable code
        return err


# ---------------------------------------------------------------- helpers


def _ordering():
    # Imported lazily: loyalty reads Ordering's tables, Ordering never knows loyalty exists.
    from apps.ordering.infrastructure import models as ordering_orm

    return ordering_orm


def _line_total_expr():
    return ExpressionWrapper(
        F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


def programme() -> LoyaltySettings:
    return LoyaltySettings.load()


def active_tier_rules() -> list[TierRule]:
    return [t.to_rule() for t in LoyaltyTier.objects.filter(is_active=True).order_by("min_spend")]


def _override_rule(user_id: uuid.UUID, rules: list[TierRule]) -> TierRule | None:
    """The tier a superadmin pinned this customer to (if any, and still active) -- it wins over the spend-based tier."""
    slug = Wallet.objects.filter(user_id=user_id, tier_override__isnull=False).values_list("tier_override__slug", flat=True).first()
    return next((r for r in rules if r.slug == slug), None) if slug else None


def tier_for(user_id: uuid.UUID, spend: Decimal, rules: list[TierRule]) -> TierRule | None:
    return _override_rule(user_id, rules) or resolve_tier(spend, rules)


def order_amount(order_id: uuid.UUID) -> Decimal:
    o = _ordering()
    total = o.OrderLineItemModel.objects.filter(order_id=order_id, status="active").aggregate(total=Sum(_line_total_expr()))["total"]
    return total or Decimal("0")


def window_start(now: datetime | None = None) -> datetime | None:
    days = programme().tier_window_days
    return None if days == 0 else (now or timezone.now()) - timedelta(days=days)


def qualifying_spend(customer_id: uuid.UUID, exclude_order_id: uuid.UUID | None = None, since: datetime | None = None, use_window: bool = True) -> tuple[Decimal, int]:
    """
    (total, purchase_count) of the customer's qualifying purchases -- within the
    rolling tier window unless `use_window=False`:
      * online orders that were delivered/completed, and
      * in-store POS sales that were completed (not refunded), counted at what the
        customer actually paid (sale total minus coins redeemed).
    `exclude_order_id` excludes one purchase of either kind (the one being rewarded).
    """
    o = _ordering()
    orders = o.OrderModel.objects.filter(customer_id=customer_id, status__in=FULFILLED_STATUSES)
    if exclude_order_id is not None:
        orders = orders.exclude(id=exclude_order_id)
    start = since if since is not None else (window_start() if use_window else None)
    if start is not None:
        orders = orders.filter(Q(placed_at__gte=start) | Q(placed_at__isnull=True, created_at__gte=start))
    count = orders.count()
    total = o.OrderLineItemModel.objects.filter(order__in=orders, status="active").aggregate(total=Sum(_line_total_expr()))["total"] or Decimal("0")
    pos_total, pos_count = _pos_spend(customer_id, start, exclude_order_id)
    return total + pos_total, count + pos_count


def _pos_spend(customer_id: uuid.UUID, start: datetime | None, exclude_sale_id: uuid.UUID | None) -> tuple[Decimal, int]:
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    sales = SaleModel.objects.filter(customer_id=customer_id, status="completed")
    if exclude_sale_id is not None:
        sales = sales.exclude(id=exclude_sale_id)
    if start is not None:
        sales = sales.filter(completed_at__gte=start)
    count = sales.count()
    if not count:
        return Decimal("0"), 0
    gross = SaleLineItemModel.objects.filter(sale__in=sales).aggregate(v=Sum(F("unit_price_amount") * F("quantity")))["v"] or Decimal("0")
    paid_off = sales.aggregate(c=Sum("coins_redeemed"), d=Sum("discount_amount"), r=Sum("refunded_amount"))
    return max(Decimal("0"), gross - (paid_off["c"] or 0) - (paid_off["d"] or 0) - (paid_off["r"] or 0)), count


def qualifying_purchases(customer_id: uuid.UUID, start: datetime | None) -> list[tuple[datetime, Decimal]]:
    """
    Every qualifying purchase since `start` as (when, amount), oldest first -- the same orders and POS
    sales `qualifying_spend` sums, one row each, so we can see which of them leaves the rolling window when.
    """
    o = _ordering()
    orders = o.OrderModel.objects.filter(customer_id=customer_id, status__in=FULFILLED_STATUSES)
    if start is not None:
        orders = orders.filter(Q(placed_at__gte=start) | Q(placed_at__isnull=True, created_at__gte=start))
    when = {oid: placed or created for oid, placed, created in orders.values_list("id", "placed_at", "created_at")}
    totals = (
        o.OrderLineItemModel.objects.filter(order_id__in=list(when), status="active")
        .values("order_id").annotate(total=Sum(_line_total_expr())).values_list("order_id", "total")
    )
    rows = [(when[oid], total or Decimal("0")) for oid, total in totals]

    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    sales = SaleModel.objects.filter(customer_id=customer_id, status="completed")
    if start is not None:
        sales = sales.filter(completed_at__gte=start)
    sale_rows = {
        sid: (done or created, (c or 0) + (d or 0) + (r or 0))
        for sid, done, created, c, d, r in sales.values_list("id", "completed_at", "created_at", "coins_redeemed", "discount_amount", "refunded_amount")
    }
    if sale_rows:
        gross = SaleLineItemModel.objects.filter(sale_id__in=list(sale_rows)).values("sale_id").annotate(v=Sum(F("unit_price_amount") * F("quantity"))).values_list("sale_id", "v")
        rows += [(sale_rows[sid][0], max(Decimal("0"), (v or Decimal("0")) - sale_rows[sid][1])) for sid, v in gross]
    return sorted(rows, key=lambda row: row[0])


@dataclass(frozen=True)
class TierRisk:
    """The customer's current tier will lapse at `drop_at` unless they buy `needed` so'm more before then."""

    tier: LoyaltyTier
    drop_at: datetime
    needed: Decimal
    falls_to: LoyaltyTier | None


def tier_risk(user_id: uuid.UUID, horizon_days: int = 30, now: datetime | None = None) -> TierRisk | None:
    """
    Will the rolling window take this customer's tier away within `horizon_days` if they buy nothing?
    Purchases leave the window oldest first; the first moment the remaining spend drops below the
    current tier's floor is the deadline. None when the window is off (lifetime tiers never drop),
    the tier is pinned by staff, the customer is on the entry tier, or nothing lapses in time.
    """
    days = programme().tier_window_days
    if days == 0:
        return None
    now = now or timezone.now()
    tiers = list(LoyaltyTier.objects.filter(is_active=True).order_by("min_spend"))
    rules = [t.to_rule() for t in tiers]
    if not rules or _override_rule(user_id, rules) is not None:
        return None
    purchases = qualifying_purchases(user_id, now - timedelta(days=days))
    spend = sum((amount for _when, amount in purchases), Decimal("0"))
    current = resolve_tier(spend, rules)
    if current is None or current.min_spend <= rules[0].min_spend:
        return None
    horizon = now + timedelta(days=horizon_days)
    remaining = spend
    for when, amount in purchases:
        drop_at = when + timedelta(days=days)
        if drop_at > horizon:
            break
        remaining -= amount
        if remaining < current.min_spend:
            by_slug = {t.slug: t for t in tiers}
            lower = resolve_tier(remaining, rules)
            return TierRisk(tier=by_slug[current.slug], drop_at=drop_at, needed=current.min_spend - remaining, falls_to=by_slug.get(lower.slug) if lower else None)
    return None


def award_pos_sale(sale_id: uuid.UUID, customer_id: uuid.UUID, paid_amount: Decimal, sale_number: str) -> AwardResult:
    """Cashback for an in-store purchase: same tier rule as online orders (tier from spend before this sale), on the amount actually paid."""
    result = AwardResult(None)
    if customer_id is None or paid_amount <= 0 or WalletTransaction.objects.filter(order_id=sale_id, kind=WalletTransactionKind.EARN).exists():
        return result
    from apps.notifications.infrastructure.subscriptions import safe_on_purchase

    safe_on_purchase(customer_id, sale_id, sale_number)  # Telegram news subscribers: one-time gift on the first purchase
    spend_before, _count = qualifying_spend(customer_id, exclude_order_id=sale_id)
    rules = active_tier_rules()
    tier = tier_for(customer_id, spend_before, rules)
    if tier is None:
        return result
    coins = reward_coins(paid_amount, tier.percent)
    if coins > 0:
        result.tx = _credit(
            customer_id, coins, WalletTransactionKind.EARN,
            order_id=sale_id, order_number=sale_number, order_amount=paid_amount,
            tier_slug=tier.slug, tier_name=tier.name, tier_percent=tier.percent, note="POS purchase",
        )
    if result.tx:
        after = tier_for(customer_id, spend_before + paid_amount, rules)
        by_slug = {t.slug: t for t in LoyaltyTier.objects.filter(slug__in=[tier.slug, after.slug if after else tier.slug])}
        result.tier_before = by_slug.get(tier.slug)
        result.tier_after = by_slug.get(after.slug) if after else None
    return result


def return_coins_for_refund(customer_id: uuid.UUID, refund_id: uuid.UUID, coins: int, number: str) -> WalletTransaction | None:
    """A (partial) POS return gives back its share of the coins the sale was paid with -- one REFUND lot per return."""
    if not customer_id or coins <= 0:
        return None
    return _credit(customer_id, coins, WalletTransactionKind.REFUND, order_id=refund_id, order_number=number, note="POS return")


def reverse_cashback_for_refund(sale_id: uuid.UUID, customer_id: uuid.UUID, refund_id: uuid.UUID, coins: int, number: str) -> WalletTransaction | None:
    """Takes back the returned items' share of the sale's cashback (from the sale's own lot first, never below zero)."""
    if not customer_id or coins <= 0:
        return None
    earned = WalletTransaction.objects.filter(order_id=sale_id, kind=WalletTransactionKind.EARN).values_list("id", flat=True).first()
    return _debit(customer_id, coins, WalletTransactionKind.REVERSAL, prefer_lot=earned, allow_partial=True, order_id=refund_id, order_number=number, note="POS return")


def notify_award(result: AwardResult | None) -> None:
    _notify_award(result)


# Backwards-compatible name used by the admin/API.
def lifetime_spend(customer_id: uuid.UUID, exclude_order_id: uuid.UUID | None = None) -> tuple[Decimal, int]:
    return qualifying_spend(customer_id, exclude_order_id)


def get_or_create_wallet(user_id: uuid.UUID) -> Wallet:
    wallet, _created = Wallet.objects.get_or_create(user_id=user_id)
    return wallet


def _earn_since() -> datetime | None:
    value = getattr(settings, "LOYALTY_EARN_SINCE", None)
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    from django.utils.dateparse import parse_date, parse_datetime

    parsed = parse_datetime(str(value))
    if parsed is None:
        day = parse_date(str(value))
        parsed = datetime(day.year, day.month, day.day) if day else None
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


# ---------------------------------------------------------------- ledger engine


def _open_lots(wallet: Wallet, now: datetime, prefer: uuid.UUID | None = None) -> list[WalletTransaction]:
    lots = list(
        WalletTransaction.objects.select_for_update()
        .filter(wallet=wallet, remaining__gt=0)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .order_by(F("expires_at").asc(nulls_last=True), "created_at")
    )
    if prefer is not None:
        lots.sort(key=lambda lot: lot.id != prefer)
    return lots


def _credit(user_id: uuid.UUID, amount: int, kind: str, expires_at: datetime | None | bool = True, **fields) -> WalletTransaction | None:
    """Adds one lot. `expires_at=True` means "now + coin_expiry_days". Returns None if the idempotency index says it already happened."""
    get_or_create_wallet(user_id)
    now = timezone.now()
    if expires_at is True:
        days = programme().coin_expiry_days
        expires_at = now + timedelta(days=days) if days else None
    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user_id=user_id)
            wallet.balance += amount
            tx = WalletTransaction.objects.create(wallet=wallet, kind=kind, amount=amount, balance_after=wallet.balance, remaining=amount, expires_at=expires_at or None, **fields)
            if kind != WalletTransactionKind.REFUND:
                wallet.lifetime_earned += amount
            wallet.save(update_fields=["balance", "lifetime_earned", "updated_at"])
            return tx
    except IntegrityError:
        return None


def _debit(user_id: uuid.UUID, amount: int, kind: str, prefer_lot: uuid.UUID | None = None, allow_partial: bool = False, **fields) -> WalletTransaction | None:
    """Consumes `amount` coins FIFO-by-expiry. Raises LoyaltyError if the balance is short (unless allow_partial, which takes what is there)."""
    get_or_create_wallet(user_id)
    now = timezone.now()
    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user_id=user_id)
            lots = _open_lots(wallet, now, prefer=prefer_lot)
            available = sum(lot.remaining for lot in lots)
            if available < amount:
                if not allow_partial:
                    raise LoyaltyError("INSUFFICIENT_COINS", "Not enough coins.")
                amount = available
            if amount <= 0:
                return None
            need, allocations = amount, []
            for lot in lots:
                if need == 0:
                    break
                take = min(lot.remaining, need)
                lot.remaining -= take
                lot.save(update_fields=["remaining"])
                allocations.append({"lot": str(lot.id), "amount": take})
                need -= take
            wallet.balance -= amount
            tx = WalletTransaction.objects.create(wallet=wallet, kind=kind, amount=-amount, balance_after=wallet.balance, allocations=allocations, **fields)
            if kind == WalletTransactionKind.SPEND:
                wallet.lifetime_spent += amount
            elif kind in (WalletTransactionKind.REVERSAL, WalletTransactionKind.ADJUSTMENT):
                wallet.lifetime_earned = max(0, wallet.lifetime_earned - amount)
            wallet.save(update_fields=["balance", "lifetime_earned", "lifetime_spent", "updated_at"])
            return tx
    except IntegrityError:
        return None


# ---------------------------------------------------------------- earning


@dataclass
class AwardResult:
    tx: WalletTransaction | None
    tier_before: LoyaltyTier | None = None
    tier_after: LoyaltyTier | None = None
    referral_payouts: list[WalletTransaction] = field(default_factory=list)

    @property
    def upgraded(self) -> bool:
        return bool(self.tier_after and (self.tier_before is None or self.tier_after.min_spend > self.tier_before.min_spend))


def award_order(order_id: uuid.UUID) -> WalletTransaction | None:
    return award_order_detailed(order_id).tx


def award_order_detailed(order_id: uuid.UUID) -> AwardResult:
    o = _ordering()
    order = o.OrderModel.objects.filter(id=order_id).only("id", "customer_id", "status", "order_number", "currency", "placed_at", "created_at").first()
    if order is None or order.customer_id is None or order.status not in FULFILLED_STATUSES:
        return AwardResult(None)
    result = AwardResult(None)
    result.referral_payouts = _qualify_referral(order)
    from apps.notifications.infrastructure.subscriptions import safe_on_purchase

    safe_on_purchase(order.customer_id, order.id, order.order_number or "", order.placed_at or order.created_at)

    if order.currency and order.currency != "UZS":
        return result  # coins are defined against so'm only
    since = _earn_since()
    if since is not None and (order.placed_at or order.created_at) < since:
        return result  # placed before the programme launched -- counts towards tier, earns nothing
    if WalletTransaction.objects.filter(order_id=order.id, kind=WalletTransactionKind.EARN).exists():
        return result

    amount = order_amount(order.id)
    spend_before, _count = qualifying_spend(order.customer_id, exclude_order_id=order.id)
    rules = active_tier_rules()
    tier = tier_for(order.customer_id, spend_before, rules)
    if tier is None:
        return result
    coins = reward_coins(amount, tier.percent)
    if coins > 0:
        result.tx = _credit(
            order.customer_id, coins, WalletTransactionKind.EARN,
            order_id=order.id, order_number=order.order_number or "", order_amount=amount,
            tier_slug=tier.slug, tier_name=tier.name, tier_percent=tier.percent, note=f"{tier.percent}% cashback",
        )
    if result.tx:
        after = tier_for(order.customer_id, spend_before + amount, rules)
        by_slug = {t.slug: t for t in LoyaltyTier.objects.filter(slug__in=[tier.slug, after.slug if after else tier.slug])}
        result.tier_before = by_slug.get(tier.slug)
        result.tier_after = by_slug.get(after.slug) if after else None
        logger.info("loyalty: order %s earned %s coins at %s", order.order_number, coins, tier.slug)
    return result


def reverse_order(order_id: uuid.UUID) -> WalletTransaction | None:
    """Takes back an order's cashback (from its own lot first, never below zero)."""
    earned = WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.EARN).select_related("wallet").first()
    if earned is None or WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.REVERSAL).exists():
        return None
    return _debit(
        earned.wallet.user_id, earned.amount, WalletTransactionKind.REVERSAL, prefer_lot=earned.id, allow_partial=True,
        order_id=order_id, order_number=earned.order_number, order_amount=earned.order_amount,
        tier_slug=earned.tier_slug, tier_name=earned.tier_name, tier_percent=earned.tier_percent, note="Order cancelled/returned",
    )


def sync_order(order_id: uuid.UUID) -> AwardResult | None:
    """Brings one order's coin state in line with its current status -- safe to call any number of times."""
    o = _ordering()
    status = o.OrderModel.objects.filter(id=order_id).values_list("status", flat=True).first()
    if status in FULFILLED_STATUSES:
        return award_order_detailed(order_id)
    if status in REVERSING_STATUSES:
        reverse_order(order_id)
        refund_order_redemption(order_id)
    return None


def reconcile(batch_size: int = 500) -> dict:
    """Safety net for any status change that bypassed the post_save signal (bulk updates, raw SQL, a crashed worker)."""
    o = _ordering()
    rewarded = WalletTransaction.objects.filter(kind=WalletTransactionKind.EARN).values("order_id")
    reversed_ids = WalletTransaction.objects.filter(kind=WalletTransactionKind.REVERSAL).values("order_id")
    spent = WalletTransaction.objects.filter(kind=WalletTransactionKind.SPEND).values("order_id")
    refunded = WalletTransaction.objects.filter(kind=WalletTransactionKind.REFUND).values("order_id")

    to_award = o.OrderModel.objects.filter(status__in=FULFILLED_STATUSES, customer_id__isnull=False).exclude(id__in=rewarded)
    since = _earn_since()
    if since is not None:
        to_award = to_award.filter(placed_at__gte=since)
    to_reverse = o.OrderModel.objects.filter(status__in=REVERSING_STATUSES, id__in=rewarded).exclude(id__in=reversed_ids)
    to_refund = o.OrderModel.objects.filter(status__in=REVERSING_STATUSES, id__in=spent).exclude(id__in=refunded)
    pending_referrals = Referral.objects.filter(status=ReferralStatus.PENDING).values("referee_id")
    to_qualify = o.OrderModel.objects.filter(status__in=FULFILLED_STATUSES, customer_id__in=pending_referrals)

    awarded = 0
    for oid in to_award.values_list("id", flat=True)[:batch_size]:
        result = award_order_detailed(oid)
        if result.tx:
            awarded += 1
            _notify_award(result)
    for oid in to_qualify.values_list("id", flat=True)[:batch_size]:
        _notify_referrals(_qualify_referral(o.OrderModel.objects.get(id=oid)))
    reversed_count = sum(1 for oid in to_reverse.values_list("id", flat=True)[:batch_size] if reverse_order(oid))
    refunded_count = sum(1 for oid in to_refund.values_list("id", flat=True)[:batch_size] if refund_order_redemption(oid))
    return {"awarded": awarded, "reversed": reversed_count, "refunded": refunded_count}


def adjust(user_id: uuid.UUID, amount: int, note: str, actor_id: uuid.UUID | None = None, actor: str = "") -> WalletTransaction:
    """Manual staff credit/debit, recorded in the ledger with the reason and who did it. Raises ValueError on a zero amount or a debit larger than the balance."""
    if amount == 0:
        raise ValueError("Amount must not be zero.")
    if amount > 0:
        tx = _credit(user_id, amount, WalletTransactionKind.ADJUSTMENT, note=note[:255], created_by=actor_id, actor=actor[:150])
    else:
        try:
            tx = _debit(user_id, -amount, WalletTransactionKind.ADJUSTMENT, note=note[:255], created_by=actor_id, actor=actor[:150])
        except LoyaltyError as exc:
            raise ValueError("Insufficient coin balance.") from exc
    assert tx is not None
    from apps.loyalty.infrastructure import notifications

    notifications.queue("granted" if amount > 0 else "deducted", user_id, tx_id=str(tx.id))
    return tx


# ---------------------------------------------------------------- expiry


def set_tier(user_id: uuid.UUID, tier: LoyaltyTier | None, reason: str, actor: str) -> TierChange | None:
    """Pins the customer to `tier` (or, with None, lets the tier follow spend again). Logged in the tier history."""
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(pk=get_or_create_wallet(user_id).pk)
        before = summary(user_id).current_tier
        if (wallet.tier_override_id or None) == (tier.pk if tier else None):
            return None
        wallet.tier_override = tier
        wallet.tier_override_reason = reason[:255] if tier else ""
        wallet.save(update_fields=["tier_override", "tier_override_reason", "updated_at"])
        after = summary(user_id).current_tier
        change = TierChange.objects.create(
            wallet=wallet, kind=TierChangeKind.MANUAL if tier else TierChangeKind.CLEARED,
            from_tier=before.name if before else "", to_tier=after.name if after else "", reason=reason[:255], actor=actor[:150],
        )
        if after is not None and (before is None or before.pk != after.pk):
            from apps.loyalty.infrastructure import notifications

            notifications.queue("tier_set", user_id, tier_slug=after.slug, ref=str(change.pk))
        return change


def expire_lots(now: datetime | None = None, batch_size: int = 1000) -> int:
    """Burns every lot whose expiry has passed -- one EXPIRY debit per lot, so the statement shows exactly which batch expired."""
    now = now or timezone.now()
    count = 0
    lots = WalletTransaction.objects.filter(remaining__gt=0, expires_at__lte=now).select_related("wallet").order_by("expires_at")[:batch_size]
    for lot in lots:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=lot.wallet_id)
            fresh = WalletTransaction.objects.select_for_update().get(pk=lot.pk)
            if fresh.remaining <= 0:
                continue
            burn = fresh.remaining
            fresh.remaining = 0
            fresh.save(update_fields=["remaining"])
            wallet.balance -= burn
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransaction.objects.create(
                wallet=wallet, kind=WalletTransactionKind.EXPIRY, amount=-burn, balance_after=wallet.balance,
                allocations=[{"lot": str(fresh.id), "amount": burn}], note=f"Expired ({fresh.get_kind_display()})",
            )
            count += 1
    return count


def expiring_soon(user_id: uuid.UUID, within_days: int | None = None) -> tuple[int, datetime | None]:
    """(coins, earliest expiry date) of lots that expire within the reminder window."""
    days = within_days if within_days is not None else max(programme().expiry_reminder_days, 30)
    now = timezone.now()
    lots = WalletTransaction.objects.filter(wallet__user_id=user_id, remaining__gt=0, expires_at__gt=now, expires_at__lte=now + timedelta(days=days))
    agg = lots.aggregate(total=Sum("remaining"))
    first = lots.order_by("expires_at").values_list("expires_at", flat=True).first()
    return agg["total"] or 0, first


# ---------------------------------------------------------------- referral


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I -- readable when dictated


def referral_code_for(user_id: uuid.UUID) -> str:
    existing = ReferralCode.objects.filter(user_id=user_id).values_list("code", flat=True).first()
    if existing:
        return existing
    for _attempt in range(10):
        code = "NZ" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        try:
            with transaction.atomic():
                return ReferralCode.objects.create(user_id=user_id, code=code).code
        except IntegrityError:
            existing = ReferralCode.objects.filter(user_id=user_id).values_list("code", flat=True).first()
            if existing:
                return existing
    raise RuntimeError("Could not allocate a referral code.")


def can_enter_referral(user_id: uuid.UUID) -> bool:
    """A code can only be applied by a genuinely new customer: no referrer yet and no fulfilled order."""
    if not programme().referral_enabled or Referral.objects.filter(referee_id=user_id).exists():
        return False
    return not _ordering().OrderModel.objects.filter(customer_id=user_id, status__in=FULFILLED_STATUSES).exists()


def claim_referral(user_id: uuid.UUID, code: str, channel: str = "web") -> Referral:
    code = (code or "").strip().upper()
    if not programme().referral_enabled:
        raise LoyaltyError("REFERRAL_DISABLED", "The referral programme is currently paused.")
    owner = ReferralCode.objects.filter(code=code).select_related("user").first()
    if owner is None:
        raise LoyaltyError("REFERRAL_CODE_INVALID", "This invite code does not exist.")
    if owner.user_id == user_id:
        raise LoyaltyError("REFERRAL_SELF", "You can't use your own invite code.")
    if Referral.objects.filter(referrer_id=user_id, referee_id=owner.user_id).exists():
        raise LoyaltyError("REFERRAL_CYCLE", "You invited this person — they can't invite you back.")
    if not can_enter_referral(user_id):
        raise LoyaltyError("REFERRAL_NOT_ELIGIBLE", "Invite codes are for new customers who haven't completed an order yet.")
    try:
        with transaction.atomic():
            return Referral.objects.create(referrer_id=owner.user_id, referee_id=user_id, code=code, channel=channel)
    except IntegrityError as exc:
        raise LoyaltyError("REFERRAL_NOT_ELIGIBLE", "An invite code was already applied to this account.") from exc


def _qualify_referral(order) -> list[WalletTransaction]:
    """Pays both sides when a pending referee's first qualifying order is fulfilled."""
    ref = Referral.objects.filter(referee_id=order.customer_id, status=ReferralStatus.PENDING).first()
    cfg = programme()
    if ref is None or not cfg.referral_enabled:
        return []
    if order_amount(order.id) < cfg.referral_min_order:
        return []
    payouts = []
    with transaction.atomic():
        locked = Referral.objects.select_for_update().get(pk=ref.pk)
        if locked.status != ReferralStatus.PENDING:
            return []
        for user_id, amount, note in ((locked.referee_id, cfg.referee_reward, "Welcome bonus (invited by a friend)"), (locked.referrer_id, cfg.referrer_reward, "Friend's first order")):
            if amount > 0:
                tx = _credit(user_id, amount, WalletTransactionKind.REFERRAL, referral=locked, order_number=order.order_number or "", note=note)
                if tx:
                    payouts.append(tx)
        locked.status = ReferralStatus.REWARDED
        locked.qualifying_order_id = order.id
        locked.rewarded_at = timezone.now()
        locked.save(update_fields=["status", "qualifying_order_id", "rewarded_at"])
    return payouts


# ---------------------------------------------------------------- redemption (checkout)


def max_redeemable(user_id: uuid.UUID | None, order_total: Decimal) -> tuple[int, int]:
    """(max coins usable on this order, current balance). 1 coin = 1 so'm."""
    cfg = programme()
    balance = 0
    if user_id is not None:
        balance = Wallet.objects.filter(user_id=user_id).values_list("balance", flat=True).first() or 0
    if not cfg.redeem_enabled or order_total <= 0:
        return 0, balance
    cap = int((order_total * cfg.max_redeem_percent / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_DOWN))
    usable = min(balance, cap)
    return (usable if usable >= cfg.min_redeem_coins else 0), balance


def validate_redemption(user_id: uuid.UUID, coins: int, order_total: Decimal) -> int:
    if coins <= 0:
        return 0
    cfg = programme()
    if not cfg.redeem_enabled:
        raise LoyaltyError("REDEEM_DISABLED", "Paying with coins is currently unavailable.")
    if coins < cfg.min_redeem_coins:
        raise LoyaltyError("REDEEM_BELOW_MINIMUM", f"The minimum is {cfg.min_redeem_coins} coins.")
    usable, balance = max_redeemable(user_id, order_total)
    if coins > balance:
        raise LoyaltyError("INSUFFICIENT_COINS", "Not enough coins.")
    if coins > usable:
        raise LoyaltyError("REDEEM_ABOVE_LIMIT", f"You can pay at most {cfg.max_redeem_percent}% of this order with coins.")
    return coins


def allocate_discount(line_totals: list[Decimal], discount: Decimal) -> list[Decimal]:
    """Spreads an order-level discount over lines pro rata (2 dp), the last line taking the rounding remainder; no line goes below zero."""
    gross = sum(line_totals, Decimal("0"))
    if discount <= 0 or gross <= 0:
        return [Decimal("0")] * len(line_totals)
    discount = min(discount, gross)
    shares, used = [], Decimal("0")
    for i, line in enumerate(line_totals):
        if i == len(line_totals) - 1:
            share = discount - used
        else:
            share = (discount * line / gross).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        share = min(share, line)
        shares.append(share)
        used += share
    return shares


def redeem_for_order(user_id: uuid.UUID, coins: int, order_id: uuid.UUID, order_number: str, order_total: Decimal) -> WalletTransaction | None:
    """Debits coins for an order. Must run inside the same transaction that creates the order."""
    if coins <= 0:
        return None
    return _debit(user_id, coins, WalletTransactionKind.SPEND, order_id=order_id, order_number=order_number, order_amount=order_total, note="Checkout payment")


def coins_spent_on_order(order_id: uuid.UUID) -> int:
    """Coins the customer paid with at checkout for this order (0 if none). 1 coin = 1 so'm."""
    amount = WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.SPEND).values_list("amount", flat=True).first()
    return -amount if amount else 0


def refund_order_redemption(order_id: uuid.UUID) -> WalletTransaction | None:
    """Returns coins spent on a cancelled order to the very lots they came from (still-valid lots get their coins back; expired ones get a 30-day grace lot)."""
    spend = WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.SPEND).select_related("wallet").first()
    if spend is None or WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.REFUND).exists():
        return None
    now = timezone.now()
    amount = -spend.amount
    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=spend.wallet_id)
            grace = 0
            for alloc in spend.allocations or []:
                lot = WalletTransaction.objects.select_for_update().filter(pk=alloc["lot"]).first()
                if lot is not None and (lot.expires_at is None or lot.expires_at > now):
                    lot.remaining = min(lot.amount, lot.remaining + alloc["amount"])
                    lot.save(update_fields=["remaining"])
                else:
                    grace += alloc["amount"]
            wallet.balance += amount
            wallet.lifetime_spent = max(0, wallet.lifetime_spent - amount)
            wallet.save(update_fields=["balance", "lifetime_spent", "updated_at"])
            return WalletTransaction.objects.create(
                wallet=wallet, kind=WalletTransactionKind.REFUND, amount=amount, balance_after=wallet.balance,
                remaining=grace, expires_at=(now + timedelta(days=REFUND_GRACE_DAYS)) if grace else None,
                order_id=order_id, order_number=spend.order_number, order_amount=spend.order_amount, note="Coins returned (order cancelled)",
            )
    except IntegrityError:
        return None


# ---------------------------------------------------------------- summary


@dataclass(frozen=True)
class LoyaltySummary:
    balance: int
    lifetime_earned: int
    lifetime_spent: int
    total_spend: Decimal
    order_count: int
    current_tier: LoyaltyTier | None
    next_tier: LoyaltyTier | None
    amount_to_next: Decimal | None
    progress_percent: int
    manual: bool = False


def summary(user_id: uuid.UUID) -> LoyaltySummary:
    wallet = Wallet.objects.filter(user_id=user_id).first()
    spend, count = qualifying_spend(user_id)
    tiers = list(LoyaltyTier.objects.filter(is_active=True).order_by("min_spend"))
    rules = [t.to_rule() for t in tiers]
    by_slug = {t.slug: t for t in tiers}
    manual = _override_rule(user_id, rules)
    current = manual or resolve_tier(spend, rules)
    upcoming = next_tier(max(spend, current.min_spend) if manual else spend, rules)

    progress = 100
    to_next = None
    if upcoming is not None:
        floor = current.min_spend if current else Decimal("0")
        span = upcoming.min_spend - floor
        to_next = upcoming.min_spend - spend
        progress = int(max(0, min(100, ((spend - floor) / span) * 100))) if span > 0 else 0

    return LoyaltySummary(
        balance=wallet.balance if wallet else 0,
        lifetime_earned=wallet.lifetime_earned if wallet else 0,
        lifetime_spent=wallet.lifetime_spent if wallet else 0,
        total_spend=spend,
        order_count=count,
        current_tier=by_slug.get(current.slug) if current else None,
        next_tier=by_slug.get(upcoming.slug) if upcoming else None,
        amount_to_next=to_next,
        progress_percent=progress,
        manual=manual is not None,
    )


# ---------------------------------------------------------------- notifications (queued, best effort)


def _notify_award(result: AwardResult | None) -> None:
    if result is None:
        return
    from apps.loyalty.infrastructure import notifications

    if result.tx:
        notifications.queue("earned", result.tx.wallet.user_id, tx_id=str(result.tx.id))
    if result.tx and result.upgraded:
        TierChange.objects.create(
            wallet=result.tx.wallet, kind=TierChangeKind.AUTO, from_tier=result.tier_before.name if result.tier_before else "",
            to_tier=result.tier_after.name, reason=f"{result.tx.order_number or ''}".strip(),
        )
        notifications.queue("tier_up", result.tx.wallet.user_id, tier_slug=result.tier_after.slug)
    _notify_referrals(result.referral_payouts)


def _notify_referrals(payouts: list[WalletTransaction]) -> None:
    from apps.loyalty.infrastructure import notifications

    for tx in payouts:
        notifications.queue("referral", tx.wallet.user_id, tx_id=str(tx.id))


def sync_order_and_notify(order_id: uuid.UUID) -> None:
    _notify_award(sync_order(order_id))
