"""
Coupon business rules -- one place, used by the storefront cart / checkout and the Dashboard.

A coupon can be used when it is ACTIVE, inside its validity window, under its total limit (max_redemptions),
under its per-customer limit (max_per_customer) and the order reaches min_order_amount.
Every use is recorded as a CouponRedemption at checkout (in the order's transaction), which is what the limits
count -- before this, orders carried coupon ids but no use was ever recorded, so limits never applied.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from common.exceptions import ConflictError

ZERO = Decimal("0")


def _err(code: str, message: str) -> ConflictError:
    err = ConflictError(message)
    err.code = code
    return err


def problem(coupon, customer_id=None, subtotal: Decimal | None = None, now=None) -> tuple[str, str] | None:
    """(code, message) why the coupon can't be used now, or None."""
    now = now or timezone.now()
    used = coupon.redemptions.count()
    if coupon.status == "exhausted" or (coupon.max_redemptions is not None and used >= coupon.max_redemptions):
        return "COUPON_EXHAUSTED", f"Coupon '{coupon.code}' has reached its limit."
    if coupon.status != "active":
        return "COUPON_NOT_ACTIVE", f"Coupon '{coupon.code}' is not active."
    if coupon.validity_starts_at and now < coupon.validity_starts_at:
        return "COUPON_NOT_STARTED", f"Coupon '{coupon.code}' is not valid yet."
    if coupon.validity_ends_at and now > coupon.validity_ends_at:
        return "COUPON_EXPIRED", f"Coupon '{coupon.code}' has expired."
    if customer_id and coupon.max_per_customer is not None and coupon.redemptions.filter(redeemed_by=customer_id).count() >= coupon.max_per_customer:
        return "COUPON_ALREADY_USED", f"You have already used coupon '{coupon.code}'."
    if subtotal is not None and coupon.min_order_amount and subtotal < coupon.min_order_amount:
        return "COUPON_MIN_ORDER", f"Coupon '{coupon.code}' needs an order of at least {int(coupon.min_order_amount):,} so'm.".replace(",", " ")
    return None


def assert_usable(coupon, customer_id=None, subtotal: Decimal | None = None) -> None:
    p = problem(coupon, customer_id, subtotal)
    if p:
        raise _err(*p)


def discount_amount(coupon, subtotal: Decimal) -> Decimal:
    if coupon.discount_value_type == "percentage" and coupon.discount_percentage is not None:
        return (subtotal * coupon.discount_percentage / Decimal("100")).quantize(Decimal("0.01"))
    return min(coupon.discount_fixed_amount or ZERO, subtotal)


def redeem(coupon_ids, customer_id, order_reference: str, subtotal: Decimal) -> list[str]:
    """Records one use of every coupon on the order (must run inside the order's transaction). Returns the codes."""
    from apps.pricing.infrastructure import composition
    from apps.pricing.infrastructure.models import CouponModel

    codes = []
    for coupon in CouponModel.objects.select_for_update().filter(id__in=list(coupon_ids or [])):
        assert_usable(coupon, customer_id, subtotal)
        composition.build_redeem_coupon(customer_id).execute(code=coupon.code, redeemed_by=customer_id, order_reference=order_reference)
        codes.append(coupon.code)
    return codes


def usage_map(coupon_ids=None) -> dict:
    """coupon id -> {"uses", "customers", "last"}."""
    from apps.pricing.infrastructure.models import CouponRedemptionModel

    qs = CouponRedemptionModel.objects.all()
    if coupon_ids is not None:
        qs = qs.filter(coupon_id__in=list(coupon_ids))
    out: dict = {}
    for r in qs.values("coupon_id").annotate(n=Count("id"), customers=Count("redeemed_by", distinct=True)):
        out[r["coupon_id"]] = {"uses": r["n"], "customers": r["customers"]}
    return out
