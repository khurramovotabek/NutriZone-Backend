"""
Pricing health checks -- registered against `core.health.registry`
from `apps/pricing/apps.py`'s `ready()` hook.
"""
from __future__ import annotations


def check_pricing_repository() -> tuple[bool, str]:
    try:
        from apps.pricing.infrastructure import models as orm

        orm.PriceListModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_pricing_cache() -> tuple[bool, str]:
    try:
        from core.caching import get_redis_client

        client = get_redis_client()
        client.set("_health_check:pricing:probe", "ok", ex=5)
        result = client.get("_health_check:pricing:probe")
        client.delete("_health_check:pricing:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_pricing_calculation_engine() -> tuple[bool, str]:
    """Exercises `PriceCalculationEngine` against a synthetic, in-memory example -- verifies the deterministic core actually runs correctly, not just that the module imports."""
    try:
        from decimal import Decimal

        from apps.pricing.domain.enums import DiscountSourceType, DiscountValueType, StackingMode
        from apps.pricing.domain.services import DiscountSource, PriceCalculationEngine
        from apps.pricing.domain.value_objects import DiscountValue, Money, Percentage

        base = Money(amount=Decimal("100.00"), currency="UZS")
        source = DiscountSource(source_type=DiscountSourceType.PRICING_RULE.value, source_id=None, label="health check", discount=DiscountValue(value_type=DiscountValueType.PERCENTAGE.value, percentage=Percentage(value=Decimal("10"))), stacking_mode=StackingMode.STACKABLE.value)
        result = PriceCalculationEngine.calculate(base, [source])
        if result.final_price.amount != Decimal("90.00"):
            return False, f"calculation engine produced unexpected result: {result.final_price.amount}"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_pricing_snapshots() -> tuple[bool, str]:
    try:
        from django.utils import timezone as django_timezone

        from apps.pricing.infrastructure import models as orm

        overdue = orm.PriceSnapshotModel.objects.filter(status="locked", expires_at__lt=django_timezone.now()).count()
        if overdue > 10:
            return False, f"{overdue} price snapshots are past expiration and not yet swept"
        return True, f"ok ({overdue} pending sweep)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_pricing_campaigns() -> tuple[bool, str]:
    try:
        from django.utils import timezone as django_timezone

        from apps.pricing.infrastructure import models as orm

        overdue = orm.CampaignModel.objects.filter(status="active", validity_ends_at__isnull=False, validity_ends_at__lt=django_timezone.now()).count()
        if overdue > 0:
            return False, f"{overdue} campaign(s) are past their end date but not yet marked ended"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
