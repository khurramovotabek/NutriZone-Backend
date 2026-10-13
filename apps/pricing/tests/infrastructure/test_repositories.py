"""
Repository integration tests -- require a real PostgreSQL database.
Matches every prior module's `tests/infrastructure/test_repositories.py`
pattern. Includes explicit database-constraint verification tests, not
just repository round-trip tests.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.pricing.domain.aggregates import Coupon, PriceList
from apps.pricing.domain.enums import CouponType
from apps.pricing.domain.value_objects import CouponCode, DiscountValue, Money, Percentage, PriceListCode
from apps.pricing.infrastructure.repositories import DjangoCouponRepository, DjangoPriceListRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoPriceListRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoPriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        repo.save(price_list)

        fetched = repo.get_by_id(price_list.id)
        assert fetched is not None
        assert fetched.code.value == "DEFAULT-UZS"

    def test_set_price_and_history_round_trip(self):
        repo = DjangoPriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("HIST-UZS"), name="History Test", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        repo.save(price_list)

        fetched = repo.get_by_id(price_list.id)
        assert len(fetched.entries) == 1
        assert len(fetched.history) == 1
        assert fetched.entry_for_variant(variant_id).base_price.amount == Decimal("100.00")

    def test_database_level_sale_price_constraint(self):
        """Verifies the CheckConstraint actually rejects sale_price > base_price at the database layer, bypassing the domain aggregate's own __post_init__ entirely."""
        from apps.pricing.infrastructure import models as orm

        price_list_row = orm.PriceListModel.objects.create(code="CONSTRAINT-TEST", name="X", currency="UZS")
        with pytest.raises(IntegrityError):
            orm.PriceListEntryModel.objects.create(price_list=price_list_row, product_variant_id=uuid.uuid4(), base_price_amount=Decimal("50.00"), sale_price_amount=Decimal("100.00"))

    def test_database_level_compare_at_constraint(self):
        from apps.pricing.infrastructure import models as orm

        price_list_row = orm.PriceListModel.objects.create(code="CONSTRAINT-TEST-2", name="X", currency="UZS")
        with pytest.raises(IntegrityError):
            orm.PriceListEntryModel.objects.create(price_list=price_list_row, product_variant_id=uuid.uuid4(), base_price_amount=Decimal("100.00"), compare_at_price_amount=Decimal("50.00"))

    def test_code_exists_respects_exclusion(self):
        repo = DjangoPriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("EXCL-UZS"), name="Default", currency="UZS")
        repo.save(price_list)
        assert repo.code_exists("EXCL-UZS") is True
        assert repo.code_exists("EXCL-UZS", exclude_id=price_list.id) is False


class TestDjangoCouponRepository:
    def test_database_level_unique_code_constraint(self):
        from apps.pricing.infrastructure import models as orm

        orm.CouponModel.objects.create(code="UNIQUECODE", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("10"))
        with pytest.raises(IntegrityError):
            orm.CouponModel.objects.create(code="UNIQUECODE", coupon_type="promo", discount_value_type="percentage", discount_percentage=Decimal("20"))

    def test_database_level_duplicate_redemption_per_order_constraint(self):
        """Verifies the UniqueConstraint(coupon, order_reference) actually prevents the same coupon being redeemed twice for the same order at the database level -- the real gap identified and closed during Phase 2, verified here to actually hold."""
        from apps.pricing.infrastructure import models as orm

        coupon_row = orm.CouponModel.objects.create(code="NOTWOREDEEMS", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("10"))
        orm.CouponRedemptionModel.objects.create(coupon=coupon_row, redeemed_by=uuid.uuid4(), order_reference="ORDER-DUP", redeemed_at="2026-01-01T00:00:00Z")
        with pytest.raises(IntegrityError):
            orm.CouponRedemptionModel.objects.create(coupon=coupon_row, redeemed_by=uuid.uuid4(), order_reference="ORDER-DUP", redeemed_at="2026-01-01T00:01:00Z")

    def test_save_and_redeem_round_trip(self):
        repo = DjangoCouponRepository()
        coupon = Coupon(id=uuid.uuid4(), code=CouponCode("ROUNDTRIP"), coupon_type=CouponType.COUPON, discount=DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal("15"))))
        coupon.activate()
        repo.save(coupon)

        fetched = repo.get_by_code("ROUNDTRIP")
        import datetime

        fetched.redeem(uuid.uuid4(), "ORDER-RT-001", datetime.datetime.utcnow())
        repo.save(fetched)

        refetched = repo.get_by_code("ROUNDTRIP")
        assert refetched.redemption_count == 1
