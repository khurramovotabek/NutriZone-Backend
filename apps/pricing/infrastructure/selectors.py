"""
Pricing read-model selectors -- optimized, read-only Postgres queries.
No business logic, no aggregate construction, matching the pattern
established by every prior module.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Count, Q

from apps.pricing.domain.enums import CampaignStatus, CouponStatus, PriceListStatus
from apps.pricing.infrastructure import models as orm


class PriceListSelector:
    def list(self, status: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.PriceListModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("code")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def get_by_code(self, code: str) -> dict | None:
        row = orm.PriceListModel.objects.filter(code=code, status=PriceListStatus.ACTIVE.value).first()
        return self._card(row) if row else None

    def _card(self, row: orm.PriceListModel) -> dict:
        return {"id": str(row.id), "code": row.code, "name": row.name, "currency": row.currency, "status": row.status, "region": row.region, "entry_count": row.entries.count()}


class PricingRuleSelector:
    def list_active(self, rule_type: str | None = None) -> list[dict]:
        qs = orm.PricingRuleModel.objects.filter(status="active")
        if rule_type:
            qs = qs.filter(rule_type=rule_type)
        return [{"id": str(r.id), "rule_type": r.rule_type, "priority": r.priority} for r in qs]


class CampaignSelector:
    def list_active(self, at: datetime | None = None) -> list[dict]:
        at = at or datetime.utcnow()
        qs = orm.CampaignModel.objects.filter(status=CampaignStatus.ACTIVE.value, validity_starts_at__lte=at).filter(Q(validity_ends_at__isnull=True) | Q(validity_ends_at__gt=at))
        return [{"id": str(c.id), "name": c.name, "campaign_type": c.campaign_type, "target_count": c.targets.count()} for c in qs]

    def upcoming(self, within_days: int = 7) -> list[dict]:
        from datetime import timedelta

        now = datetime.utcnow()
        cutoff = now + timedelta(days=within_days)
        qs = orm.CampaignModel.objects.filter(status__in=[CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value], validity_starts_at__gte=now, validity_starts_at__lte=cutoff)
        return [{"id": str(c.id), "name": c.name, "starts_at": c.validity_starts_at.isoformat()} for c in qs]


class CouponSelector:
    def get_by_code(self, code: str) -> dict | None:
        row = orm.CouponModel.objects.filter(code=code).first()
        if row is None:
            return None
        return {"id": str(row.id), "code": row.code, "status": row.status, "redemption_count": row.redemptions.count(), "max_redemptions": row.max_redemptions}

    def list_active(self) -> list[dict]:
        qs = orm.CouponModel.objects.filter(status=CouponStatus.ACTIVE.value)
        return [{"id": str(c.id), "code": c.code, "coupon_type": c.coupon_type} for c in qs]


class PriceSnapshotSelector:
    def list_expiring_soon(self, within_minutes: int = 5) -> list[dict]:
        from datetime import timedelta

        cutoff = datetime.utcnow() + timedelta(minutes=within_minutes)
        qs = orm.PriceSnapshotModel.objects.filter(status="locked", expires_at__lte=cutoff)
        return [{"id": str(s.id), "token": str(s.token), "expires_at": s.expires_at.isoformat()} for s in qs]


class PriceHistorySelector:
    def list_for_variant(self, price_list_id: uuid.UUID, product_variant_id: uuid.UUID) -> list[dict]:
        qs = orm.PriceHistoryEntryModel.objects.filter(price_list_id=price_list_id, product_variant_id=product_variant_id).order_by("-changed_at")
        return [{"id": str(h.id), "price_type": h.price_type, "old_amount": str(h.old_amount) if h.old_amount is not None else None, "new_amount": str(h.new_amount), "reason": h.reason, "changed_at": h.changed_at.isoformat()} for h in qs]


class DjangoPricingSearchBackend:
    """Implements `application/ports.py::PricingSearchGateway` -- Postgres ILIKE search over price list name/code, per every other module's identical launch-stage search approach."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.PriceListModel.objects.filter(status=PriceListStatus.ACTIVE.value)
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("code")[start : start + page_size]
        return [{"id": str(r.id), "code": r.code, "name": r.name} for r in rows], total


class MarketingStatisticsSelector:
    """
    Phase 08.8: closes a genuine, confirmed gap -- no statistics
    selector existed for Coupon/Campaign at all before this (verified
    by direct search). Matches the exact established pattern already
    used identically by ReviewStatisticsSelector, WalletStatisticsSelector,
    and ShipmentStatisticsSelector -- reporting-only aggregate
    queries, no new business logic.
    """

    def coupon_counts_by_status(self) -> dict:
        rows = orm.CouponModel.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}

    def campaign_counts_by_status(self) -> dict:
        rows = orm.CampaignModel.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}

    def total_redemptions(self) -> int:
        return orm.CouponRedemptionModel.objects.count()
