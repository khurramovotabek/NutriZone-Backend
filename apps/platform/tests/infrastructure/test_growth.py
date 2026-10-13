"""Phase 3 (sales growth): customer segments, broadcast segment audience, sales plan, personal picks, pages, /reja."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.platform.infrastructure import sales_plan, segments
from apps.platform.infrastructure.segments import Profile, classify

pytestmark = [pytest.mark.django_db]
NOW = timezone.now()


@pytest.fixture(autouse=True)
def _own_cache(monkeypatch):
    """The test settings share the dev Redis (db 0, also the Celery broker): never write or clear it from here."""
    from django.core.cache.backends.locmem import LocMemCache

    from apps.products.infrastructure import personal

    local = LocMemCache(f"growth-tests-{uuid.uuid4().hex}", {})
    monkeypatch.setattr(segments, "cache", local)
    monkeypatch.setattr(personal, "cache", local)
    return local


def _customer(phone_tail: int):
    from apps.identity.infrastructure.models import User

    return User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{phone_tail:07d}", full_name=f"Mijoz {phone_tail}", status="active", language="uz")


def _sale(customer, days_ago: int, amount=Decimal("100000"), branch=None, product_id=None, variant_id=None):
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    when = timezone.now() - timedelta(days=days_ago)
    sale = SaleModel.objects.create(branch_id=branch or uuid.uuid4(), cashier_id=uuid.uuid4(), status="completed", channel="store", completed_at=when,
                                    customer_id=customer.id if customer else None, payment_method="cash", payments=[{"method": "cash", "amount": str(amount)}])
    SaleLineItemModel.objects.create(sale=sale, product_id=product_id or uuid.uuid4(), product_variant_id=variant_id, quantity=1, unit_price_amount=amount, unit_price_currency="UZS")
    return sale


class TestSegments:
    def test_rules_in_order(self):
        def p(purchases, revenue, first_days, last_days):
            x = Profile(uuid.uuid4(), purchases, Decimal(revenue), NOW - timedelta(days=first_days), NOW - timedelta(days=last_days))
            return x
        profiles = {f"big{i}": p(2, 100, 400, 200) for i in range(12)}
        profiles.update({"vip": p(4, 9_000_000, 300, 5), "loyal": p(3, 300, 200, 10), "new": p(1, 50, 10, 10),
                         "active": p(2, 120, 100, 20), "risk": p(2, 120, 100, 45), "lost": p(2, 120, 300, 90)})
        seg = classify(profiles, NOW)
        assert (seg["vip"], seg["loyal"], seg["new"], seg["active"], seg["risk"], seg["lost"]) == ("vip", "loyal", "new", "active", "at_risk", "lost")

    def test_snapshot_counts_buyers_and_non_buyers_and_feeds_broadcasts(self):
        from apps.notifications.infrastructure import notify

        a, b, c = _customer(1), _customer(2), _customer(3)
        _sale(a, 40)
        _sale(a, 50)
        _sale(b, 5)
        data = segments.snapshot(force=True)
        assert str(a.id) in data["members"]["at_risk"] and str(b.id) in data["members"]["new"] and str(c.id) in data["members"]["no_purchase"]
        assert data["segments"]["at_risk"]["revenue"] == Decimal("200000")
        assert list(notify.audience_queryset("segment", "at_risk").values_list("id", flat=True)) == [a.id]
        assert not notify.audience_queryset("segment", "nonsense").exists()


class TestSalesPlan:
    def test_progress_forecast_and_needed_per_day(self):
        from apps.stores.infrastructure.models import Store

        store = Store.objects.create(name="Olmazor", slug=f"o-{uuid.uuid4().hex[:6]}", status="active")
        month = sales_plan.month_start()
        sales_plan.save_targets(month, {str(store.id): "3 000 000", "company": "10 000 000"}, "Sinov")
        _sale(None, 0, Decimal("500000"), branch=store.id)
        data = sales_plan.progress(month)
        row = next(r for r in data["branches"] if r["name"] == "Olmazor")
        assert row["target"] == Decimal("3000000") and row["done"] == Decimal("500000") and row["pct"] == pytest.approx(16.7, 0.1)
        assert row["needed_per_day"] > 0 and row["today"] == Decimal("500000") and row["state"] in ("ok", "warn", "bad")
        assert data["company"]["target"] == Decimal("10000000")
        sales_plan.save_targets(month, {str(store.id): ""}, "Sinov")  # empty removes it
        assert next(r for r in sales_plan.progress(month)["branches"] if r["name"] == "Olmazor")["target"] is None
        with pytest.raises(ValueError):
            sales_plan.save_targets(month, {"company": "-5"}, "Sinov")

    def test_parse_month_and_telegram_doc(self):
        assert sales_plan.parse_month("2026-03") == date(2026, 3, 1)
        assert sales_plan.parse_month("bad") == sales_plan.month_start()
        doc = sales_plan.telegram_doc()
        assert "Sotuv rejasi" in doc.fallback and "reja kiritilmagan" in doc.html


class TestPersonal:
    def test_bought_together_goal_and_no_recent_repeat(self, monkeypatch):
        from apps.products.infrastructure import co_purchase, personal
        from apps.products.infrastructure import models as orm
        from apps.products.tests.stock_helpers import put_stock


        def product(name, goals=("muscle",), stock=5):
            cat = orm.Category.objects.create(id=uuid.uuid4(), is_active=True)
            p = orm.Product.objects.create(id=uuid.uuid4(), status="published", category=cat, goals=list(goals))
            orm.ProductTranslation.objects.create(product=p, locale_code="uz", name=name, slug=f"p-{uuid.uuid4().hex[:8]}")
            v = orm.ProductVariant.objects.create(id=uuid.uuid4(), product=p, sku=f"S-{uuid.uuid4().hex[:8]}", is_default=True)
            if stock:
                put_stock(v.id, stock)
            return p, v

        whey, whey_v = product("Whey")
        creatine, _ = product("Kreatin")
        shaker, _ = product("Shaker", goals=())
        gainer, _ = product("Gainer")
        me = _customer(9)
        _sale(me, 3, product_id=whey.id, variant_id=whey_v.id)  # bought 3 days ago: not suggested again
        monkeypatch.setattr(co_purchase, "for_basket", lambda ids, limit=8: [shaker.id])
        monkeypatch.setattr(personal, "_popular", lambda limit: [whey.id, creatine.id, gainer.id])
        picks = personal.for_customer(me.id, "uz")
        ids = [c["id"] for c in picks]
        assert str(whey.id) not in ids
        assert picks[0]["id"] == str(shaker.id) and picks[0]["reason"] == "Whey bilan ko'p olinadi"
        goal_pick = next(c for c in picks if c["id"] == str(creatine.id))
        assert goal_pick["reason_code"] == "goal" and "Mushak" in goal_pick["reason"]


class TestPages:
    def test_pages_render_and_plan_save_needs_permission(self):
        su = get_user_model().objects.create(username=f"g_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True)
        c = Client()
        c.force_login(su)
        assert c.get("/django-admin/sales-plan/").status_code == 200
        assert c.get("/django-admin/sales-plan/?m=2026-01").status_code == 200
        r = c.get("/django-admin/segments/?s=new")
        assert r.status_code == 200 and "Mijozlar segmentlari" in r.content.decode()
        assert c.get("/django-admin/segments/export.xlsx?s=new")["Content-Type"].startswith("application/vnd.openxmlformats")
        r = c.post("/django-admin/sales-plan/save/", {"month": "2026-10", "target_company": "50 000 000"})
        assert r.status_code == 302
        from apps.platform.infrastructure.models import SalesTarget

        assert SalesTarget.objects.get(store__isnull=True, month=date(2026, 10, 1)).revenue_target == Decimal("50000000")
        staff = get_user_model().objects.create(username=f"s_{uuid.uuid4().hex[:6]}", is_staff=True)
        c2 = Client()
        c2.force_login(staff)
        assert c2.post("/django-admin/sales-plan/save/", {"month": "2026-10"}).status_code == 403
