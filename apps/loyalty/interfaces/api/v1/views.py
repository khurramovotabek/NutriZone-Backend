"""
Loyalty REST API.

- GET /loyalty/tiers                 public -- the programme's active tiers
- GET /loyalty/me                    customer -- wallet balance, tier, progress
- GET /loyalty/me/transactions       customer -- paginated wallet ledger
- GET /loyalty/me/rate               customer -- tier/next tier only (product pages)
"""
from __future__ import annotations

import math

from django.db.models import Sum
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.loyalty.infrastructure import services
from apps.loyalty.infrastructure.models import (
    LoyaltyTier,
    Referral,
    ReferralStatus,
    Wallet,
    WalletTransaction,
)
from common.responses import paginated_response, success_response

_MAX_PAGE_SIZE = 50


def _num(value) -> str | None:
    """Decimals as plain strings ("1000000", "3.5") -- the storefront formats them; no float rounding on money."""
    if value is None:
        return None
    return f"{value.normalize():f}"


def tier_payload(tier: LoyaltyTier | None) -> dict | None:
    if tier is None:
        return None
    return {
        "id": str(tier.id), "name": tier.name, "slug": tier.slug,
        "min_spend": _num(tier.min_spend), "max_spend": _num(tier.max_spend), "percent": _num(tier.percent),
        "icon": tier.icon, "color": tier.color, "description": tier.description,
    }


def _programme_payload() -> dict:
    cfg = services.programme()
    return {
        "tier_window_days": cfg.tier_window_days, "coin_expiry_days": cfg.coin_expiry_days,
        "max_redeem_percent": cfg.max_redeem_percent, "min_redeem_coins": cfg.min_redeem_coins, "redeem_enabled": cfg.redeem_enabled,
        "referral_enabled": cfg.referral_enabled, "referrer_reward": cfg.referrer_reward, "referee_reward": cfg.referee_reward,
    }


def _expiring_payload(user_id) -> dict | None:
    coins, first = services.expiring_soon(user_id, within_days=30)
    return {"coins": coins, "first_expiry": first.isoformat()} if coins and first else None


def _expiry_schedule(user_id, limit: int = 4) -> list[dict]:
    """Upcoming expiry dates (lots grouped by day, soonest first) -- the wallet's "what burns when" view."""
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    rows = (
        WalletTransaction.objects.filter(wallet__user_id=user_id, remaining__gt=0, expires_at__gt=timezone.now())
        .annotate(day=TruncDate("expires_at")).values("day").annotate(coins=Sum("remaining")).order_by("day")[:limit]
    )
    return [{"date": r["day"].isoformat(), "coins": r["coins"]} for r in rows]


def tier_risk_payload(user_id) -> dict | None:
    from django.utils import timezone

    risk = services.tier_risk(user_id)
    if risk is None:
        return None
    return {
        "tier": tier_payload(risk.tier), "falls_to": tier_payload(risk.falls_to), "needed": _num(risk.needed),
        "drop_date": risk.drop_at.isoformat(), "days_left": max(0, math.ceil((risk.drop_at - timezone.now()).total_seconds() / 86400)),
    }


def _mask(name: str) -> str:
    parts = (name or "").split()
    if not parts:
        return "—"
    first = parts[0]
    return f"{first} {parts[1][0]}." if len(parts) > 1 else first


def _referral_payload(user) -> dict:
    made = Referral.objects.filter(referrer_id=user.id).select_related("referee").order_by("-created_at")
    rewarded = made.filter(status=ReferralStatus.REWARDED)
    earned = WalletTransaction.objects.filter(wallet__user_id=user.id, kind="referral", referral__referrer_id=user.id).values_list("amount", flat=True)
    referred_by = Referral.objects.filter(referee_id=user.id).select_related("referrer").first()
    return {
        "code": services.referral_code_for(user.id),
        "invited_count": made.count(),
        "rewarded_count": rewarded.count(),
        "earned_coins": sum(earned),
        "can_enter_code": services.can_enter_referral(user.id),
        "referred_by": _mask(referred_by.referrer.full_name) if referred_by else None,
        "referred_status": referred_by.status if referred_by else None,
        "friends": [{"name": _mask(r.referee.full_name), "status": r.status, "joined_at": r.created_at.isoformat()} for r in made[:10]],
    }


class ReferralClaimView(APIView):
    """POST {code} -- attach an invite code to the signed-in (new) customer. Both sides are paid when their first order is delivered."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Loyalty"], summary="Apply a friend's invite code", responses={200: OpenApiResponse(description="Applied"), 409: OpenApiResponse(description="Not eligible / invalid code")})
    def post(self, request):
        channel = request.data.get("channel") if request.data.get("channel") in ("web", "telegram", "manual") else "web"
        try:
            ref = services.claim_referral(request.user.id, str(request.data.get("code", "")), channel=channel)
        except services.LoyaltyError as exc:
            raise exc.as_conflict() from exc
        return success_response(data={"status": ref.status, "referee_reward": services.programme().referee_reward})


class LoyaltyTierListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Loyalty"], summary="List active loyalty tiers", responses={200: OpenApiResponse(description="Tiers, lowest first")})
    def get(self, request):
        tiers = LoyaltyTier.objects.filter(is_active=True).order_by("min_spend")
        return success_response(data=[tier_payload(t) for t in tiers])


class MyLoyaltyView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Loyalty"], summary="My wallet & loyalty status", responses={200: OpenApiResponse(description="Wallet summary")})
    def get(self, request):
        s = services.summary(request.user.id)
        wallet = Wallet.objects.filter(user_id=request.user.id).only("created_at").first()
        joined = getattr(request.user, "created_at", None) or (wallet.created_at if wallet else None)
        tiers = LoyaltyTier.objects.filter(is_active=True).order_by("min_spend")
        return success_response(data={
            "member_name": getattr(request.user, "full_name", "") or "",
            "member_since": joined.isoformat() if joined else None,
            "tiers": [tier_payload(t) for t in tiers],
            "balance": s.balance,
            "lifetime_earned": s.lifetime_earned,
            "lifetime_spent": s.lifetime_spent,
            "total_spend": _num(s.total_spend),
            "order_count": s.order_count,
            "current_tier": tier_payload(s.current_tier),
            "next_tier": tier_payload(s.next_tier),
            "amount_to_next": _num(s.amount_to_next),
            "progress_percent": s.progress_percent,
            "coin_rate": "1",  # 1 so'm = 1 coin
            "programme": _programme_payload(),
            "expiring": _expiring_payload(request.user.id),
            "expiry_schedule": _expiry_schedule(request.user.id),
            "tier_risk": tier_risk_payload(request.user.id),
            "referral": _referral_payload(request.user),
        })


class MyLoyaltyRateView(APIView):
    """Light "what do I earn" for product pages: tier, next tier and balance -- no ledger, referral or expiry work."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Loyalty"], summary="My cashback rate", responses={200: OpenApiResponse(description="Tier, next tier, balance")})
    def get(self, request):
        s = services.summary(request.user.id)
        return success_response(data={
            "current_tier": tier_payload(s.current_tier), "next_tier": tier_payload(s.next_tier),
            "amount_to_next": _num(s.amount_to_next), "balance": s.balance,
        })


class MyWalletTransactionsView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(
        tags=["Loyalty"], summary="My wallet transactions",
        parameters=[OpenApiParameter("page", int), OpenApiParameter("page_size", int), OpenApiParameter("direction", str, enum=["in", "out"])],
        responses={200: OpenApiResponse(description="Paginated ledger, newest first")},
    )
    def get(self, request):
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(_MAX_PAGE_SIZE, max(1, int(request.query_params.get("page_size", 20))))
        except ValueError:
            page, page_size = 1, 20

        wallet = Wallet.objects.filter(user_id=request.user.id).first()
        qs = WalletTransaction.objects.filter(wallet=wallet).order_by("-created_at") if wallet else WalletTransaction.objects.none()
        # Filter server-side so paging stays correct ("Received" page 2 is the 2nd page of credits, not of everything).
        direction = request.query_params.get("direction")
        if direction == "in":
            qs = qs.filter(amount__gt=0)
        elif direction == "out":
            qs = qs.filter(amount__lt=0)
        total = qs.count()
        rows = list(qs[(page - 1) * page_size: page * page_size])
        # Only the customer's own online orders get a link (POS sale / refund ids live elsewhere).
        from apps.ordering.infrastructure.models import OrderModel

        own_orders = set(OrderModel.objects.filter(customer_id=request.user.id, id__in=[tx.order_id for tx in rows if tx.order_id]).values_list("id", flat=True))
        data = [
            {
                "id": str(tx.id), "kind": tx.kind, "amount": tx.amount, "balance_after": tx.balance_after,
                "order_id": str(tx.order_id) if tx.order_id else None, "order_number": tx.order_number or None,
                "order_linkable": tx.order_id in own_orders,
                "order_amount": _num(tx.order_amount), "tier_name": tx.tier_name or None, "tier_percent": _num(tx.tier_percent),
                "note": tx.note or None, "created_at": tx.created_at.isoformat(),
                # A credit lot still holding coins shows when they burn.
                "remaining": tx.remaining if tx.amount > 0 else 0,
                "expires_at": tx.expires_at.isoformat() if tx.amount > 0 and tx.remaining > 0 and tx.expires_at else None,
            }
            for tx in rows
        ]
        total_pages = (total + page_size - 1) // page_size if total else 0
        return paginated_response(data=data, pagination={"strategy": "page", "page": page, "page_size": page_size, "total_pages": total_pages, "total_count": total})
