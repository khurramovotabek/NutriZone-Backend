"""
Coins for feedback, one per order: every delivered online order earns `reward_coins` (default 1 000) for ONE review
of a product from that order -- any star rating, an honest 1★ counts the same as a 5★.

Rules (ReviewRequestSettings, Dashboard → Sharhlar → Sharh so'rovi):
- only online orders (delivered / completed); the review must be written after that order reached the customer;
- the text is at least reward_min_chars long (no one-word reviews); rating >= reward_min_rating (default 1 = any);
- signed-up customers only (guest checkout accounts are skipped);
- one reward per order -- ReviewRewardModel's unique (customer, order) constraint is the guard, so retries and races
  never pay twice. The next order earns the next reward;
- an edit later does not pay again; a review hidden by staff keeps the coins (staff can deduct in Loyalty if abused).
Never raises into the review flow.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction

logger = logging.getLogger("nutrizone.app")


def _unrewarded_order(customer_id, product_id, written_at) -> str | None:
    """The earliest online order containing this product that reached the customer before `written_at` and has not
    paid a review reward yet ("order:<id>"), or None."""
    from apps.ordering.infrastructure.replenishment import purchases
    from apps.reviews.infrastructure.models import ReviewRewardModel

    paid = set(ReviewRewardModel.objects.filter(customer_id=customer_id).values_list("received_ref", flat=True))
    hits = sorted((p for p in purchases(customer_ids=[customer_id], since=written_at - timedelta(days=730))
                   if p.ref.startswith("order:") and p.product_id == product_id and p.at <= written_at and p.ref not in paid), key=lambda p: p.at)
    return hits[0].ref if hits else None


def eligibility(review) -> tuple[bool, str, str]:
    """(ok, reason, purchase_ref) for a ReviewModel row -- reason is shown in the admin when it is not ok."""
    from apps.identity.infrastructure.guests import is_guest
    from apps.reviews.infrastructure.models import ReviewRequestSettings, ReviewRewardModel

    cfg = ReviewRequestSettings.load()
    if not cfg.reward_enabled or not cfg.reward_coins:
        return False, "Sharh mukofoti o'chirilgan", ""
    if review.status != "published":
        return False, "Sharh saytda emas", ""
    if review.rating < cfg.reward_min_rating:
        return False, f"{cfg.reward_min_rating}★ dan past", ""
    if len((review.body or "").strip()) < cfg.reward_min_chars:
        return False, f"Matn {cfg.reward_min_chars} belgidan qisqa", ""
    if ReviewRewardModel.objects.filter(review_id=review.id).exists():
        return False, "Bu sharh uchun mukofot berilgan", ""
    if is_guest(review.customer_id):
        return False, "Ro'yxatdan o'tmagan mijoz", ""
    ref = _unrewarded_order(review.customer_id, review.product_id, review.created_at)
    if not ref:
        return False, "Yetkazilgan buyurtma yo'q yoki bu buyurtma uchun mukofot berilgan", ""
    return True, "", ref


def award(review_id: uuid.UUID):
    """Pays the reward for one review if it qualifies. Returns the ReviewRewardModel row or None."""
    from apps.loyalty.infrastructure.models import WalletTransactionKind
    from apps.loyalty.infrastructure.services import _credit
    from apps.reviews.infrastructure.models import ReviewModel, ReviewRequestSettings, ReviewRewardModel

    review = ReviewModel.objects.filter(pk=review_id).first()
    if review is None:
        return None
    ok, _reason, ref = eligibility(review)
    if not ok:
        return None
    coins = int(ReviewRequestSettings.load().reward_coins)
    try:
        with transaction.atomic():
            row = ReviewRewardModel.objects.create(review_id=review.id, customer_id=review.customer_id, product_id=review.product_id,
                                                   coins=coins, rating=review.rating, received_ref=ref)
            tx = _credit(review.customer_id, coins, WalletTransactionKind.BONUS, note="Sharh uchun rahmat")
            if tx is None:
                raise IntegrityError("review reward credit was not recorded")
            row.transaction_id = tx.id
            row.save(update_fields=["transaction_id"])
    except IntegrityError:
        return None  # already rewarded (race / retry)
    _notify(row, tx)
    return row


def safe_award(review_id) -> None:
    def _run():
        try:
            award(review_id)
        except Exception:  # noqa: BLE001 - a reward must never break publishing a review
            logger.exception("review reward failed for %s", review_id)

    transaction.on_commit(_run)


def _notify(row, tx) -> None:
    from apps.notifications.infrastructure.notify import fmt, notify
    from apps.products.infrastructure.models import ProductTranslation

    names = dict(ProductTranslation.objects.filter(product_id=row.product_id).values_list("locale_code", "name"))
    fallback = names.get("uz") or next(iter(names.values()), "")
    i18n = {lang: {"product": names.get(lang) or fallback} for lang in ("uz", "ru", "en")}
    notify(row.customer_id, "review_reward", {"coins": fmt(row.coins), "balance": fmt(tx.balance_after), "product": fallback, "i18n": i18n},
           link="/account/loyalty", dedupe_key=f"review_reward:{row.review_id}")


def offer(customer_id, product_id) -> dict:
    """What the review form shows: {enabled, coins, min_rating, min_chars, state} -- state for a signed-in customer:
    "eligible" (a delivered order with this product has not paid a reward yet), "rewarded" (its order already paid),
    "not_received"; "anonymous" otherwise."""
    from apps.reviews.infrastructure.models import ReviewRequestSettings, ReviewRewardModel

    cfg = ReviewRequestSettings.load()
    out = {"enabled": bool(cfg.reward_enabled and cfg.reward_coins), "coins": int(cfg.reward_coins), "min_rating": int(cfg.reward_min_rating),
           "min_chars": int(cfg.reward_min_chars), "state": "anonymous"}
    if not out["enabled"] or not customer_id or not product_id:
        return out
    from django.utils import timezone

    if _unrewarded_order(customer_id, product_id, timezone.now()):
        out["state"] = "eligible"
    elif ReviewRewardModel.objects.filter(customer_id=customer_id, product_id=product_id).exists():
        out["state"] = "rewarded"
    else:
        out["state"] = "not_received"
    return out
