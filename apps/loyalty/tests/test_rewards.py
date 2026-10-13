"""Earning, reversal, idempotency, API -- against the real database and the real post_save signal."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure import services
from apps.loyalty.infrastructure.models import LoyaltyTier, Wallet, WalletTransaction
from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

pytestmark = pytest.mark.django_db(transaction=True)  # transaction=True so on_commit signal handlers actually run


@pytest.fixture(autouse=True)
def _launch_date(settings):
    settings.LOYALTY_EARN_SINCE = ""


@pytest.fixture(autouse=True)
def _ladder():
    """transaction=True flushes the DB between tests, which also wipes the 0002 data-migration seed -- recreate the same ladder."""
    import importlib

    seed = importlib.import_module("apps.loyalty.infrastructure.migrations.0004_eight_tier_ladder")
    for slug, name, lo, hi, pct, icon, color, desc in seed.LADDER:
        LoyaltyTier.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "min_spend": Decimal(lo), "max_spend": Decimal(hi) if hi else None, "percent": Decimal(pct), "icon": icon, "color": color, "description": desc},
        )


@pytest.fixture
def customer():
    return User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10_000_000:07d}", full_name="Test Customer")


def _order(customer, amount: str, status: str = "confirmed", **extra) -> OrderModel:
    order = OrderModel.objects.create(
        order_number=f"ORD-{uuid.uuid4().hex[:10]}", customer_id=customer.id, currency="UZS", status=status,
        shipping_recipient_name="A", shipping_line1="B", shipping_city="Tashkent", shipping_country_code="UZ",
        billing_recipient_name="A", billing_line1="B", billing_city="Tashkent", billing_country_code="UZ",
        placed_at=timezone.now(), **extra,
    )
    OrderLineItemModel.objects.create(order=order, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal(amount))
    return order


def _set_status(order: OrderModel, status: str) -> None:
    order.status = status
    order.save()


def _balance(customer) -> int:
    return Wallet.objects.get(user_id=customer.id).balance


def test_seeded_ladder_exists():
    assert list(LoyaltyTier.objects.order_by("min_spend").values_list("slug", "percent")) == [
        ("bronze", Decimal("1")), ("silver", Decimal("2")), ("gold", Decimal("3")), ("platinum", Decimal("4")),
        ("diamond", Decimal("5")), ("elite", Decimal("6")), ("legend", Decimal("7")), ("vip", Decimal("8")),
    ]


def test_first_order_earns_bronze_one_percent_on_delivery(customer):
    order = _order(customer, "1000000")
    assert not Wallet.objects.filter(user_id=customer.id, balance__gt=0).exists()  # nothing until fulfilled (the empty wallet exists from sign-up)

    _set_status(order, "delivered")

    assert _balance(customer) == 10_000
    tx = WalletTransaction.objects.get(order_id=order.id)
    assert (tx.kind, tx.tier_slug, tx.tier_percent, tx.balance_after) == ("earn", "bronze", Decimal("1.00"), 10_000)


def test_tier_comes_from_spend_before_the_order(customer):
    # 12 earlier orders totalling 14 000 000 -> Diamond (10M–20M) -> next 1 000 000 order earns 5% = 50 000.
    for _ in range(12):
        _order(customer, "1166667", status="completed")
    order = _order(customer, "1000000")
    _set_status(order, "completed")

    tx = WalletTransaction.objects.get(order_id=order.id, kind="earn")
    assert tx.tier_slug == "diamond"
    assert tx.amount == 50_000


def test_signal_and_reconcile_never_double_pay(customer):
    order = _order(customer, "2000000")
    _set_status(order, "delivered")
    _set_status(order, "completed")  # second fulfilled status
    services.sync_order(order.id)
    services.reconcile()

    assert WalletTransaction.objects.filter(order_id=order.id, kind="earn").count() == 1
    assert _balance(customer) == 20_000


def test_cancel_after_reward_reverses_it(customer):
    order = _order(customer, "1000000")
    _set_status(order, "delivered")
    _set_status(order, "returned")

    assert _balance(customer) == 0
    kinds = sorted(WalletTransaction.objects.filter(order_id=order.id).values_list("kind", flat=True))
    assert kinds == ["earn", "reversal"]


def test_reversal_never_drives_balance_negative(customer):
    order = _order(customer, "1000000")
    _set_status(order, "delivered")  # +10 000
    services.adjust(customer.id, -7_000, "spent on promo")
    _set_status(order, "cancelled")

    assert _balance(customer) == 0
    assert WalletTransaction.objects.get(order_id=order.id, kind="reversal").amount == -3_000


def test_orders_before_launch_count_for_tier_but_do_not_earn(customer, settings):
    settings.LOYALTY_EARN_SINCE = (timezone.now() + timedelta(days=1)).isoformat()
    order = _order(customer, "1000000")
    _set_status(order, "delivered")

    assert not WalletTransaction.objects.filter(order_id=order.id).exists()
    assert services.summary(customer.id).total_spend == Decimal("1000000")


def test_adjust_rejects_overdraft(customer):
    with pytest.raises(ValueError):
        services.adjust(customer.id, -1, "overdraft")


def test_summary_progress(customer):
    _set_status(_order(customer, "4500000"), "completed")  # spend 4.5M -> Gold (3M–6M), halfway to Platinum
    s = services.summary(customer.id)
    assert s.current_tier.slug == "gold"
    assert s.next_tier.slug == "platinum"
    assert s.amount_to_next == Decimal("1500000")
    assert s.progress_percent == 50


def test_tiers_api_is_public(client):
    body = client.get("/api/v1/loyalty/tiers").json()
    assert body["success"] is True
    assert [t["slug"] for t in body["data"]] == ["bronze", "silver", "gold", "platinum", "diamond", "elite", "legend", "vip"]
    assert body["data"][2]["percent"] == "3"
    assert body["data"][-1]["max_spend"] is None
    assert body["data"][-1]["icon"] == "vip"


def test_me_requires_authentication(client):
    assert client.get("/api/v1/loyalty/me").status_code in (401, 403)


def _ladder_post(tiers, overrides):
    data = {"form-TOTAL_FORMS": str(len(tiers)), "form-INITIAL_FORMS": str(len(tiers)), "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000", "_save": "Save"}
    for i, t in enumerate(tiers):
        row = {"id": str(t.id), "min_spend": str(t.min_spend), "max_spend": "" if t.max_spend is None else str(t.max_spend), "percent": str(t.percent), "is_active": "on"}
        row.update(overrides.get(t.slug, {}))
        for k, v in row.items():
            if not (k == "is_active" and v is None):
                data[f"form-{i}-{k}"] = v
    return data


def test_admin_bulk_edit_shifts_neighbouring_ranges_together(admin_client):
    tiers = list(LoyaltyTier.objects.order_by("min_spend"))
    # Move the Silver/Gold boundary from 3M to 2.5M -- valid only when both rows change together.
    res = admin_client.post("/django-admin/loyalty/loyaltytier/", _ladder_post(tiers, {"silver": {"max_spend": "2500000", "percent": "2.5"}, "gold": {"min_spend": "2500000"}}))
    assert res.status_code == 302, res.content[:2000]
    assert LoyaltyTier.objects.get(slug="silver").max_spend == Decimal("2500000")
    assert LoyaltyTier.objects.get(slug="silver").percent == Decimal("2.5")
    assert LoyaltyTier.objects.get(slug="gold").min_spend == Decimal("2500000")


def test_admin_bulk_edit_rejects_overlap(admin_client):
    tiers = list(LoyaltyTier.objects.order_by("min_spend"))
    res = admin_client.post("/django-admin/loyalty/loyaltytier/", _ladder_post(tiers, {"silver": {"max_spend": "4000000"}}))
    assert res.status_code == 200  # re-rendered with the formset error
    assert "ustma-ust" in res.content.decode()
    assert LoyaltyTier.objects.get(slug="silver").max_spend == Decimal("3000000")
