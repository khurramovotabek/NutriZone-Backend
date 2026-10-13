"""
Pricing repositories.

Concrete implementations of application/ports.py's Protocols -- maps
ORM rows to domain dataclasses only, never leaks ORM objects outside
this module, matching the pattern established by every prior module.
`DiscountLine` is deliberately never persisted (see domain/entities.py's
own docstring: it's a calculation-output entity, not aggregate state)
-- no repository method here constructs or returns one.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Q

from apps.pricing.domain.aggregates import Campaign, Coupon, PriceList, PriceSnapshot, PricingRule
from apps.pricing.domain.entities import CampaignTarget, CouponRedemption, PriceHistoryEntry, PriceListEntry
from apps.pricing.domain.enums import (
    CampaignStatus, CampaignType, CouponStatus, CouponType, PriceChangeReason,
    PriceListStatus, PriceSnapshotStatus, PriceType, PricingRuleStatus, PricingRuleType, StackingMode,
)
from apps.pricing.domain.value_objects import (
    CouponCode, DiscountValue, Money, Percentage, PriceListCode, PriceSnapshotToken, PriceValidityPeriod,
    QuantityTier, RegionCode,
)
from apps.pricing.infrastructure import models as orm
from common.exceptions import ConflictError


def _discount_to_domain(value_type: str, percentage, fixed_amount, currency: str) -> DiscountValue:
    return DiscountValue(
        value_type=value_type, percentage=Percentage(value=percentage) if percentage is not None else None,
        fixed_amount=Money(amount=fixed_amount, currency=currency) if fixed_amount is not None else None,
    )


def _discount_to_orm_fields(discount: DiscountValue, prefix: str = "discount_") -> dict:
    return {
        f"{prefix}value_type": discount.value_type,
        f"{prefix}percentage": discount.percentage.value if discount.percentage else None,
        f"{prefix}fixed_amount": discount.fixed_amount.amount if discount.fixed_amount else None,
    }


class DjangoPriceListRepository:
    def get_by_id(self, price_list_id: uuid.UUID) -> PriceList | None:
        row = orm.PriceListModel.objects.filter(id=price_list_id).prefetch_related("entries", "history").first()
        return self._to_domain(row) if row else None

    def get_by_code(self, code: str) -> PriceList | None:
        row = orm.PriceListModel.objects.filter(code=code).prefetch_related("entries", "history").first()
        return self._to_domain(row) if row else None

    def get_active_for_region(self, region: str | None) -> PriceList | None:
        qs = orm.PriceListModel.objects.filter(status=PriceListStatus.ACTIVE.value)
        row = qs.filter(region=region).first() if region else qs.filter(region__isnull=True).first()
        return self._to_domain(row) if row else None

    def save(self, price_list: PriceList) -> PriceList:
        try:
            row, _ = orm.PriceListModel.objects.update_or_create(
                id=price_list.id,
                defaults={"code": price_list.code.value, "name": price_list.name, "currency": price_list.currency, "status": price_list.status.value, "region": price_list.region.value if price_list.region else None},
            )
        except IntegrityError as exc:
            raise ConflictError("A price list with conflicting unique fields already exists.") from exc

        existing_entry_ids = set(row.entries.values_list("id", flat=True))
        for entry in price_list.entries.values():
            orm.PriceListEntryModel.objects.update_or_create(
                id=entry.id,
                defaults={
                    "price_list": row, "product_variant_id": entry.product_variant_id, "base_price_amount": entry.base_price.amount,
                    "cost_price_amount": entry.cost_price.amount if entry.cost_price else None, "sale_price_amount": entry.sale_price.amount if entry.sale_price else None,
                    "compare_at_price_amount": entry.compare_at_price.amount if entry.compare_at_price else None,
                },
            )
        if price_list.entries:
            row.entries.exclude(id__in=[e.id for e in price_list.entries.values()]).delete()

        existing_history_ids = set(row.history.values_list("id", flat=True))
        for h in price_list.history:
            if h.id not in existing_history_ids:
                orm.PriceHistoryEntryModel.objects.create(
                    id=h.id, price_list=row, product_variant_id=h.product_variant_id, price_type=h.price_type,
                    old_amount=h.old_amount.amount if h.old_amount else None, new_amount=h.new_amount.amount, reason=h.reason, changed_at=h.changed_at,
                )
        return price_list

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.PriceListModel.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def list_for_admin(self, status: str | None, page: int, page_size: int) -> tuple[list[PriceList], int]:
        qs = orm.PriceListModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.PriceListModel) -> PriceList:
        entries = {}
        for e in row.entries.all():
            entries[e.id] = PriceListEntry(
                id=e.id, product_variant_id=e.product_variant_id, base_price=Money(amount=e.base_price_amount, currency=row.currency),
                cost_price=Money(amount=e.cost_price_amount, currency=row.currency) if e.cost_price_amount is not None else None,
                sale_price=Money(amount=e.sale_price_amount, currency=row.currency) if e.sale_price_amount is not None else None,
                compare_at_price=Money(amount=e.compare_at_price_amount, currency=row.currency) if e.compare_at_price_amount is not None else None,
            )
        history = [
            PriceHistoryEntry(id=h.id, product_variant_id=h.product_variant_id, price_type=h.price_type, old_amount=Money(amount=h.old_amount, currency=row.currency) if h.old_amount is not None else None, new_amount=Money(amount=h.new_amount, currency=row.currency), reason=h.reason, changed_at=h.changed_at)
            for h in row.history.all()
        ]
        return PriceList(id=row.id, code=PriceListCode(row.code), name=row.name, currency=row.currency, status=PriceListStatus(row.status), region=RegionCode(row.region) if row.region else None, entries=entries, history=history)


class DjangoPricingRuleRepository:
    def get_by_id(self, pricing_rule_id: uuid.UUID) -> PricingRule | None:
        row = orm.PricingRuleModel.objects.filter(id=pricing_rule_id).prefetch_related("quantity_tiers").first()
        return self._to_domain(row) if row else None

    def save(self, pricing_rule: PricingRule) -> PricingRule:
        row, _ = orm.PricingRuleModel.objects.update_or_create(
            id=pricing_rule.id,
            defaults={
                "rule_type": pricing_rule.rule_type.value, "status": pricing_rule.status.value,
                **_discount_to_orm_fields(pricing_rule.discount, "discount_"),
                "currency": pricing_rule.discount.fixed_amount.currency if pricing_rule.discount.fixed_amount else "UZS",
                "validity_starts_at": pricing_rule.validity.starts_at if pricing_rule.validity else None,
                "validity_ends_at": pricing_rule.validity.ends_at if pricing_rule.validity else None,
                "region": pricing_rule.region.value if pricing_rule.region else None,
                "membership_tier_code": pricing_rule.membership_tier_code, "priority": pricing_rule.priority,
            },
        )
        existing_tier_ids = {t.minimum_quantity: t for t in row.quantity_tiers.all()}
        for tier in pricing_rule.quantity_tiers:
            orm.QuantityTierModel.objects.update_or_create(
                pricing_rule=row, minimum_quantity=tier.minimum_quantity,
                defaults={"id": uuid.uuid4(), **_discount_to_orm_fields(tier.discount, "discount_"), "currency": tier.discount.fixed_amount.currency if tier.discount.fixed_amount else "UZS"},
            )
        return pricing_rule

    def list_active_at(self, at: datetime, rule_type: str | None = None) -> list[PricingRule]:
        qs = orm.PricingRuleModel.objects.filter(status=PricingRuleStatus.ACTIVE.value).prefetch_related("quantity_tiers")
        if rule_type:
            qs = qs.filter(rule_type=rule_type)
        rules = [self._to_domain(r) for r in qs]
        return [r for r in rules if r.is_active_at(at)]

    def _to_domain(self, row: orm.PricingRuleModel) -> PricingRule:
        tiers = tuple(
            QuantityTier(minimum_quantity=t.minimum_quantity, discount=_discount_to_domain(t.discount_value_type, t.discount_percentage, t.discount_fixed_amount, t.currency))
            for t in row.quantity_tiers.all()
        )
        validity = PriceValidityPeriod(starts_at=row.validity_starts_at, ends_at=row.validity_ends_at) if row.validity_starts_at else None
        return PricingRule(
            id=row.id, rule_type=PricingRuleType(row.rule_type), discount=_discount_to_domain(row.discount_value_type, row.discount_percentage, row.discount_fixed_amount, row.currency),
            status=PricingRuleStatus(row.status), validity=validity, region=RegionCode(row.region) if row.region else None,
            quantity_tiers=tiers, membership_tier_code=row.membership_tier_code, priority=row.priority,
        )


class DjangoCampaignRepository:
    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None:
        row = orm.CampaignModel.objects.filter(id=campaign_id).prefetch_related("targets").first()
        return self._to_domain(row) if row else None

    def save(self, campaign: Campaign) -> Campaign:
        row, _ = orm.CampaignModel.objects.update_or_create(
            id=campaign.id,
            defaults={
                "campaign_type": campaign.campaign_type.value, "name": campaign.name, "status": campaign.status.value,
                **_discount_to_orm_fields(campaign.discount, "discount_"),
                "currency": campaign.discount.fixed_amount.currency if campaign.discount.fixed_amount else "UZS",
                "validity_starts_at": campaign.validity.starts_at, "validity_ends_at": campaign.validity.ends_at, "stacking_mode": campaign.stacking_mode.value,
            },
        )
        existing_target_ids = set(row.targets.values_list("id", flat=True))
        for target in campaign.targets.values():
            if target.id not in existing_target_ids:
                orm.CampaignTargetModel.objects.create(id=target.id, campaign=row, target_type=target.target_type, target_id=target.target_id)
        return campaign

    def list_active_for_target(self, target_type: str, target_id: uuid.UUID, at: datetime) -> list[Campaign]:
        qs = orm.CampaignModel.objects.filter(status=CampaignStatus.ACTIVE.value, targets__target_type=target_type, targets__target_id=target_id).prefetch_related("targets").distinct()
        campaigns = [self._to_domain(r) for r in qs]
        return [c for c in campaigns if c.is_active_at(at)]

    def _to_domain(self, row: orm.CampaignModel) -> Campaign:
        targets = {t.id: CampaignTarget(id=t.id, target_type=t.target_type, target_id=t.target_id) for t in row.targets.all()}
        return Campaign(
            id=row.id, campaign_type=CampaignType(row.campaign_type), name=row.name, discount=_discount_to_domain(row.discount_value_type, row.discount_percentage, row.discount_fixed_amount, row.currency),
            validity=PriceValidityPeriod(starts_at=row.validity_starts_at, ends_at=row.validity_ends_at), status=CampaignStatus(row.status), stacking_mode=StackingMode(row.stacking_mode), targets=targets,
        )


class DjangoCouponRepository:
    def get_by_id(self, coupon_id: uuid.UUID) -> Coupon | None:
        row = orm.CouponModel.objects.filter(id=coupon_id).prefetch_related("redemptions").first()
        return self._to_domain(row) if row else None

    def get_by_code(self, code: str) -> Coupon | None:
        row = orm.CouponModel.objects.filter(code=code).prefetch_related("redemptions").first()
        return self._to_domain(row) if row else None

    def save(self, coupon: Coupon) -> Coupon:
        try:
            row, _ = orm.CouponModel.objects.update_or_create(
                id=coupon.id,
                defaults={
                    "code": coupon.code.value, "coupon_type": coupon.coupon_type.value, "status": coupon.status.value,
                    **_discount_to_orm_fields(coupon.discount, "discount_"),
                    "currency": coupon.discount.fixed_amount.currency if coupon.discount.fixed_amount else "UZS",
                    "validity_starts_at": coupon.validity.starts_at if coupon.validity else None, "validity_ends_at": coupon.validity.ends_at if coupon.validity else None,
                    "max_redemptions": coupon.max_redemptions, "stacking_mode": coupon.stacking_mode.value,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A coupon with conflicting unique fields already exists.") from exc

        existing_redemption_ids = set(row.redemptions.values_list("id", flat=True))
        for redemption in coupon.redemptions.values():
            if redemption.id not in existing_redemption_ids:
                orm.CouponRedemptionModel.objects.create(id=redemption.id, coupon=row, redeemed_by=redemption.redeemed_by, order_reference=redemption.order_reference, redeemed_at=redemption.redeemed_at)
        return coupon

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.CouponModel.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def _to_domain(self, row: orm.CouponModel) -> Coupon:
        redemptions = {r.id: CouponRedemption(id=r.id, redeemed_by=r.redeemed_by, order_reference=r.order_reference, redeemed_at=r.redeemed_at) for r in row.redemptions.all()}
        validity = PriceValidityPeriod(starts_at=row.validity_starts_at, ends_at=row.validity_ends_at) if row.validity_starts_at else None
        return Coupon(
            id=row.id, code=CouponCode(row.code), coupon_type=CouponType(row.coupon_type), discount=_discount_to_domain(row.discount_value_type, row.discount_percentage, row.discount_fixed_amount, row.currency),
            status=CouponStatus(row.status), validity=validity, max_redemptions=row.max_redemptions, stacking_mode=StackingMode(row.stacking_mode), redemptions=redemptions,
        )


class DjangoPriceSnapshotRepository:
    def get_by_id(self, snapshot_id: uuid.UUID) -> PriceSnapshot | None:
        row = orm.PriceSnapshotModel.objects.filter(id=snapshot_id).first()
        return self._to_domain(row) if row else None

    def get_by_token(self, token: str) -> PriceSnapshot | None:
        row = orm.PriceSnapshotModel.objects.filter(token=token).first()
        return self._to_domain(row) if row else None

    def save(self, snapshot: PriceSnapshot) -> PriceSnapshot:
        orm.PriceSnapshotModel.objects.update_or_create(
            id=snapshot.id,
            defaults={
                "token": snapshot.token.value, "product_variant_id": snapshot.product_variant_id, "locked_price_amount": snapshot.locked_price.amount,
                "currency": snapshot.locked_price.currency, "expires_at": snapshot.expires_at, "status": snapshot.status.value,
            },
        )
        return snapshot

    def _to_domain(self, row: orm.PriceSnapshotModel) -> PriceSnapshot:
        return PriceSnapshot(id=row.id, token=PriceSnapshotToken(row.token), product_variant_id=row.product_variant_id, locked_price=Money(amount=row.locked_price_amount, currency=row.currency), expires_at=row.expires_at, status=PriceSnapshotStatus(row.status))
