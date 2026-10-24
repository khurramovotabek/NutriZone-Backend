"""Narxlarni qayta baholash: rules, rounding, the builder, apply (with price history), schedule and revert."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.pricing.infrastructure import repricing as rp
from apps.pricing.infrastructure.models import PriceHistoryEntryModel, PriceListEntryModel, RepricingModel
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"rp_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


def _variant(name: str, price: str, cost: str | None = None, brand=None):
    from apps.products.infrastructure.admin import _get_or_create_default_price_list
    from apps.pricing.infrastructure import composition

    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand)
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}")
    v = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
    pl = _get_or_create_default_price_list()
    composition.build_set_price().execute(price_list_id=pl.id, product_variant_id=v.id, base_amount=Decimal(price), currency="UZS",
                                          cost_amount=Decimal(cost) if cost else None)
    return v


def _price(v) -> Decimal:
    return PriceListEntryModel.objects.get(product_variant_id=v.id, price_list__status="active").base_price_amount


class TestRules:
    @pytest.mark.parametrize("amount,mode,expected", [
        ("123456", "1000", "123000"), ("123500", "1000", "124000"), ("149120", "900", "149900"), ("150000", "900", "149900"),
        ("12345", "100", "12300"), ("123456", "none", "123456"), ("123456", "5000", "125000"),
    ])
    def test_rounding(self, amount, mode, expected):
        assert rp.round_price(Decimal(amount), mode) == Decimal(expected)

    def test_percent_amount_markup_fixed_and_warnings(self):
        rows = [{"price": Decimal("100000"), "cost": Decimal("80000"), "compare_at": None}, {"price": Decimal("50000"), "cost": None, "compare_at": Decimal("60000")}]
        out = rp.compute([dict(r) for r in rows], "percent", Decimal("10"), "none", "keep")
        assert [r["new_price"] for r in out] == [Decimal("110000"), Decimal("55000")]
        assert out[1]["new_compare"] == Decimal("60000")  # still above the new price -> kept
        out = rp.compute([dict(r) for r in rows], "amount", Decimal("-30000"), "none", "current")
        assert out[0]["new_price"] == Decimal("70000") and "below_cost" in out[0]["warn"] and not out[0]["skip"]
        assert out[0]["new_compare"] == Decimal("100000")  # shown as a discount
        out = rp.compute([dict(r) for r in rows], "markup", Decimal("50"), "1000", "keep")
        assert out[0]["new_price"] == Decimal("120000") and out[1]["new_price"] is None and out[1]["skip"]
        out = rp.compute([dict(r) for r in rows], "fixed", Decimal("99000"), "none", "clear")
        assert {r["new_price"] for r in out} == {Decimal("99000")} and all(r["new_compare"] is None for r in out)


class TestApply:
    def test_candidates_by_brand_apply_history_and_revert(self):
        brand = p_models.Brand.objects.create(id=uuid.uuid4())
        a = _variant("Whey A", "200000", "150000", brand=brand)
        b = _variant("Whey B", "300000", brand=brand)
        _variant("Other", "100000")
        f = rp.Filters(brands=[str(brand.id)], categories=[])
        rows = rp.compute(rp.candidates(f), "percent", Decimal("10"), "1000", "keep")
        assert {r["variant_id"] for r in rows} == {a.id, b.id}
        lines = [{"variant_id": r["variant_id"], "old_price": r["price"], "new_price": r["new_price"], "old_compare": r["compare_at"], "new_compare": r["new_compare"], "cost": r["cost"]} for r in rows]
        doc = rp.create(lines, "Test +10%", {"mode": "percent", "value": "10"}, "tester")
        assert doc.number == "RP-000001" and doc.status == "draft" and doc.lines_count == 2
        res = rp.apply(doc, "tester")
        assert res == {"ok": 2, "failed": 0}
        assert _price(a) == Decimal("220000") and _price(b) == Decimal("330000")
        assert PriceHistoryEntryModel.objects.filter(product_variant_id=a.id, new_amount=Decimal("220000"), reason="rule_applied").exists()
        with pytest.raises(rp.RepricingError):
            rp.apply(doc, "tester")
        back = rp.revert(doc, "tester")
        assert back.reverts_id == doc.id and back.status == "applied"
        assert _price(a) == Decimal("200000") and _price(b) == Decimal("300000")
        with pytest.raises(rp.RepricingError):
            rp.revert(doc, "tester")

    def test_scheduled_document_applies_when_due(self):
        a = _variant("Creatine", "100000")
        doc = rp.create([{"variant_id": a.id, "old_price": Decimal("100000"), "new_price": Decimal("90000"), "old_compare": None, "new_compare": None}],
                        "Sale", {}, "tester", scheduled_for=timezone.now() + timedelta(hours=1))
        assert doc.status == "scheduled"
        assert rp.apply_due() == 0 and _price(a) == Decimal("100000")
        assert rp.apply_due(timezone.now() + timedelta(hours=2)) == 1 and _price(a) == Decimal("90000")

    def test_nothing_to_change_is_refused(self):
        a = _variant("Same", "100000")
        with pytest.raises(rp.RepricingError):
            rp.create([{"variant_id": a.id, "old_price": Decimal("100000"), "new_price": Decimal("100000"), "old_compare": None, "new_compare": None}], "x", {}, "t")


class TestPages:
    def test_builder_preview_save_apply_and_document(self, staff_client):
        a = _variant("Gainer Mass", "250000", "200000")
        assert staff_client.get("/django-admin/pricing/repricingmodel/").status_code == 200
        assert staff_client.get("/django-admin/pricing/repricingmodel/add/").status_code == 200
        form = {"q": "Gainer", "mode": "percent", "value": "-20", "rounding": "1000", "compare": "current", "preview": "1"}
        page = staff_client.post("/django-admin/pricing/repricingmodel/add/", form).content.decode()
        assert "Gainer Mass" in page and "200000" in page and "nzr-flag is-bad" not in page  # 200 000 == cost, not below
        form.pop("preview")
        form.update({"save": "1", "when": "now", "title": "Aksiya", f"on_{a.id}": "1", f"new_{a.id}": "199 000"})
        res = staff_client.post("/django-admin/pricing/repricingmodel/add/", form)
        doc = RepricingModel.objects.get()
        assert res.status_code == 302 and doc.status == "applied"
        assert _price(a) == Decimal("199000")
        assert PriceListEntryModel.objects.get(product_variant_id=a.id, price_list__status="active").compare_at_price_amount == Decimal("250000")
        page = staff_client.get(f"/django-admin/pricing/repricingmodel/{doc.id}/doc/")
        assert page.status_code == 200 and "Gainer Mass" in page.content.decode()
        x = staff_client.get(f"/django-admin/pricing/repricingmodel/{doc.id}/export.xlsx")
        assert x.status_code == 200 and "spreadsheet" in x["Content-Type"]
        staff_client.post(f"/django-admin/pricing/repricingmodel/{doc.id}/act/", {"action": "revert"})
        assert _price(a) == Decimal("250000")

    def test_draft_then_cancel(self, staff_client):
        a = _variant("Omega", "80000")
        staff_client.post("/django-admin/pricing/repricingmodel/add/", {"q": "Omega", "mode": "amount", "value": "5000", "rounding": "none", "compare": "keep",
                                                                       "save": "1", "when": "draft", f"on_{a.id}": "1"})
        doc = RepricingModel.objects.get()
        assert doc.status == "draft" and _price(a) == Decimal("80000")
        staff_client.post(f"/django-admin/pricing/repricingmodel/{doc.id}/act/", {"action": "cancel"})
        doc.refresh_from_db()
        assert doc.status == "cancelled"
