from decimal import Decimal
from types import SimpleNamespace

from apps.pricing.infrastructure import repricing as rp
from apps.pricing.infrastructure.coupon_admin import efficiency
from apps.products.infrastructure.price_list_view import margin_kind
from apps.stores.infrastructure.price_change_insights import _median


def e(price, cost):
    return SimpleNamespace(base_price_amount=Decimal(price) if price is not None else None, cost_price_amount=Decimal(cost) if cost is not None else None)


def test_margin_kind():
    assert margin_kind(e(90, 100)) == "loss"
    assert margin_kind(e(105, 100)) == "low"
    assert margin_kind(e(150, 100)) == ""
    assert margin_kind(e(150, None)) == ""
    assert margin_kind(e(None, 100)) == ""


def test_coupon_efficiency():
    x = efficiency(Decimal(1000000), Decimal(50000))
    assert x["roi"] == "20" and x["level"] == "good"
    assert efficiency(Decimal(100000), Decimal(50000))["level"] == "bad"
    assert efficiency(Decimal(100), 0)["roi"] == ""


def test_repricing_target_margin():
    rows = [{"price": Decimal(100000), "cost": Decimal(75000), "compare_at": None}, {"price": Decimal(1), "cost": None, "compare_at": None}]
    out = rp.compute(rows, "margin", Decimal(25), "none", "keep")
    assert out[0]["new_price"] == Decimal(100000)
    assert out[0]["margin_new"] == 25.0
    assert out[1]["warn"] == ["no_cost"] and out[1]["skip"]


def test_median():
    assert _median([3, 1, 2]) == 2
    assert _median([1, 2, 3, 4]) == 2.5
    assert _median([]) == 0.0
