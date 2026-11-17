"""
Opening campaign: the first N customers who place an order get a one-time coin gift (default 5 000 coins, first 500).

- Paid when the customer's first order is CONFIRMED (loyalty/signals.py) -- a real purchase, not a bare sign-up, so
  throw-away accounts can't take the slots. One gift per customer, whatever happens to later orders.
- `SignupBonusGrant` is the counter and the guard: one row per customer (unique), numbered 1..limit. Slots are taken
  under a row lock on the settings singleton, so two orders confirmed in the same second never both become "№500".
- Coins are an ordinary ledger credit (kind "bonus", normal expiry), visible in the wallet history as a gift.
- Customers who had already ordered before the switch are given their slots by `manage.py grant_signup_bonus --existing`.
- Grants made while the gift was paid at sign-up (source "signup") stay as they are.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.db import IntegrityError, transaction

logger = logging.getLogger("nutrizone.app")


@dataclass(frozen=True)
class CampaignStatus:
    enabled: bool
    coins: int
    limit: int
    granted: int

    @property
    def remaining(self) -> int | None:
        return None if not self.limit else max(self.limit - self.granted, 0)

    @property
    def is_open(self) -> bool:
        return self.enabled and self.coins > 0 and (not self.limit or self.granted < self.limit)


def status() -> CampaignStatus:
    from apps.loyalty.infrastructure.models import SignupBonusGrant
    from apps.loyalty.infrastructure.services import programme

    cfg = programme()
    return CampaignStatus(enabled=bool(cfg.signup_bonus_enabled), coins=int(cfg.signup_bonus_coins or 0),
                          limit=int(cfg.signup_bonus_limit or 0), granted=SignupBonusGrant.objects.count())


def grant(user_id: uuid.UUID, source: str = "first_order", notify_customer: bool = True):
    """Gives `user_id` the next free slot and credits the coins. Returns the grant, or None when the campaign is
    off/full or the customer already has one. Never raises into the caller's business action."""
    from apps.loyalty.infrastructure.models import LoyaltySettings, SignupBonusGrant, WalletTransactionKind
    from apps.loyalty.infrastructure.services import _credit

    from django.conf import settings

    if not getattr(settings, "LOYALTY_SIGNUP_BONUS", True) or SignupBonusGrant.objects.filter(user_id=user_id).exists():
        return None
    try:
        with transaction.atomic():
            LoyaltySettings.load()
            cfg = LoyaltySettings.objects.select_for_update().get(pk=1)  # serializes slot numbering
            coins, limit = int(cfg.signup_bonus_coins or 0), int(cfg.signup_bonus_limit or 0)
            if not cfg.signup_bonus_enabled or coins <= 0:
                return None
            taken = SignupBonusGrant.objects.count()
            if limit and taken >= limit:
                return None
            number = taken + 1
            row = SignupBonusGrant.objects.create(user_id=user_id, number=number, coins=coins, source=source)
            tx = _credit(user_id, coins, WalletTransactionKind.BONUS, note=f"Birinchi buyurtma sovg'asi · №{number}")
            if tx is None:
                raise IntegrityError("signup bonus credit was not recorded")
            row.transaction = tx
            row.save(update_fields=["transaction"])
    except IntegrityError:
        return None  # lost a race for the same customer -- they already have their gift
    if notify_customer:
        _notify(row, limit)
    return row


def safe_grant(user_id: uuid.UUID, source: str = "first_order") -> None:
    from apps.identity.infrastructure.guests import is_guest

    if is_guest(user_id):
        return  # guest checkout: the gift is for signed-up customers
    try:
        grant(user_id, source=source)
    except Exception:  # noqa: BLE001 - a gift must never break an order
        logger.exception("signup bonus failed for %s", user_id)


def _notify(row, limit: int) -> None:
    from apps.loyalty.infrastructure.services import programme
    from apps.notifications.infrastructure.notify import fmt, notify

    cfg = programme()
    ctx = {"coins": fmt(row.coins), "number": row.number, "limit": fmt(limit) if limit else "", "percent": cfg.max_redeem_percent}
    notify(row.user_id, "signup_bonus", ctx, link="/account/loyalty", dedupe_key=f"signup_bonus:{row.user_id}")
