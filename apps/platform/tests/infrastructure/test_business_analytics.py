"""Business analytics (dashboard Analitika + NutriZoneAnalyticsBot): periods, one revenue definition, comparisons, page."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.platform.infrastructure import business_analytics as ba

pytestmark = [pytest.mark.django_db]
TZ = ZoneInfo("Asia/Tashkent")


def _sale(when, amount, qty=1, status="completed", branch=None, method="cash", customer=None, refunded=Decimal("0")):
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    sale = SaleModel.objects.create(branch_id=branch or uuid.uuid4(), cashier_id=uuid.uuid4(), status=status, channel="store", completed_at=when,
                                    payment_method=method, payments=[{"method": method, "amount": str(amount * qty - refunded)}], customer_id=customer, refunded_amount=refunded)
    SaleLineItemModel.objects.create(sale=sale, product_id=uuid.uuid4(), quantity=qty, unit_price_amount=amount, unit_price_currency="UZS")
    return sale


def _order(when, amount, status="delivered", qty=1, customer=None):
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

    addr = {f"{k}_{f}": v for k in ("shipping", "billing") for f, v in (("recipient_name", "Test"), ("line1", "Ko'cha 1"), ("city", "Toshkent"), ("country_code", "UZ"))}
    order = OrderModel.objects.create(order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}", status=status, placed_at=when, customer_id=customer, **addr)
    OrderLineItemModel.objects.create(order=order, product_variant_id=uuid.uuid4(), quantity=qty, unit_price_amount=amount)
    return order


NOW = datetime(2026, 10, 12, 15, 30, tzinfo=TZ)


class TestPeriods:
    def test_today_compares_same_elapsed_time_of_yesterday(self):
        p = ba.period("today", now=NOW)
        assert p.start == datetime(2026, 10, 12, 0, 0, tzinfo=TZ)
        assert p.prev_start == datetime(2026, 10, 11, 0, 0, tzinfo=TZ)
        assert p.prev_end == datetime(2026, 10, 11, 15, 30, tzinfo=TZ)
        assert p.running and "15:30 holatiga" in p.range_text()

    def test_tashkent_midnight_boundary(self):
        # 23:30 UTC on the 11th is already 04:30 on the 12th in Tashkent
        p = ba.period("today", now=datetime(2026, 10, 11, 23, 30, tzinfo=ZoneInfo("UTC")))
        assert p.first_day.isoformat() == "2026-10-12"

    def test_last_full_week_and_month(self):
        w = ba.period("week", now=NOW)  # NOW is a Monday
        assert (w.first_day.isoformat(), w.last_day.isoformat()) == ("2026-10-05", "2026-10-11")
        assert w.prev_start == datetime(2026, 9, 28, tzinfo=TZ) and w.prev_end == w.start
        m = ba.period("month", now=NOW)
        assert (m.first_day.isoformat(), m.last_day.isoformat()) == ("2026-09-01", "2026-09-30")
        assert m.prev_start == datetime(2026, 8, 1, tzinfo=TZ) and m.prev_end == m.start

    def test_custom_is_clamped_and_bad_input_falls_back(self):
        p = ba.period("custom", now=NOW, date_from="2026-10-20", date_to="2026-10-01")
        assert p.first_day.isoformat() == "2026-10-01" and p.last_day.isoformat() == "2026-10-12"
        assert ba.period("custom", now=NOW, date_from="x", date_to=None).key == "7d"


class TestChange:
    def test_no_baseline_never_divides_by_zero(self):
        assert ba.change(Decimal("5"), Decimal("0"))["pct"] is None
        assert ba.change(0, 0)["dir"] is None
        assert ba.change(110, 100) == {"pct": 10.0, "diff": Decimal("10"), "dir": "up"}
        assert ba.change(90, 100)["dir"] == "down"


class TestBuild:
    def test_one_revenue_definition_and_exclusions(self):
        now = timezone.now()
        _sale(now - timedelta(minutes=5), Decimal("100000"), qty=2)                      # 200 000
        _sale(now - timedelta(minutes=4), Decimal("50000"), refunded=Decimal("50000"))   # fully returned -> 0
        _sale(now - timedelta(minutes=3), Decimal("70000"), status="voided")             # never revenue
        _order(now - timedelta(minutes=2), Decimal("300000"))                            # delivered -> revenue
        _order(now - timedelta(minutes=2), Decimal("999000"), status="processing")       # pipeline, not revenue
        _order(now - timedelta(minutes=2), Decimal("400000"), status="cancelled")        # lost
        r = ba.build(ba.period("today"))
        ov = r["overview"]
        assert ov["revenue"] == Decimal("500000")
        assert ov["pos_revenue"] == Decimal("200000") and ov["online_revenue"] == Decimal("300000")
        assert ov["purchases"] == 3  # 2 completed receipts + 1 delivered order (the refunded one is 'refunded')
        assert ov["pipeline_value"] == Decimal("999000") and ov["pipeline_orders"] == 1
        assert r["orders"]["cancelled"] == 1
        assert r["finance"]["refunds"] == Decimal("50000")
        assert sum(x["amount"] for x in r["finance"]["payments"]["rows"]) == ov["revenue"]
        assert all(r["sections_ok"].values())

    def test_profit_hidden_without_known_costs(self):
        _sale(timezone.now() - timedelta(minutes=1), Decimal("100000"))
        ov = ba.build(ba.period("today"))["overview"]
        assert ov["gross_profit"] is None and ov["margin"] is None  # no purchase cost known -> never label revenue as profit

    def test_empty_period_is_zero_not_missing(self):
        r = ba.build(ba.period("today"))
        assert r["overview"]["revenue"] == 0 and r["overview"]["average"] is None
        assert r["overview"]["revenue_change"]["dir"] is None

    def test_repeat_customer_counted_once(self):
        cid = uuid.uuid4()
        now = timezone.now()
        _sale(now - timedelta(days=40), Decimal("10000"), customer=cid)
        _sale(now - timedelta(minutes=3), Decimal("10000"), customer=cid)
        _order(now - timedelta(minutes=2), Decimal("10000"), customer=cid)
        c = ba.build(ba.period("today"))["customers"]
        assert c["buyers"] == 1 and c["repeat"] == 1 and c["frequency"] == 2

    def test_failing_section_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(ba, "_chats", lambda: 1 / 0)
        r = ba.build(ba.period("today"))
        assert r["sections_ok"]["Chatlar"] is False
        assert any("Chatlar" in a["text"] for a in r["alerts"])


class TestPage:
    def _client(self, **flags):
        user = get_user_model().objects.create(username=f"nza_{uuid.uuid4().hex[:6]}", is_staff=True, **flags)
        c = Client()
        c.force_login(user)
        return c

    def test_superuser_sees_every_period(self):
        c = self._client(is_superuser=True)
        _sale(timezone.now() - timedelta(minutes=1), Decimal("123000"))
        for q in ("", "?p=yesterday", "?p=7d", "?p=30d", "?p=this_month", "?p=week", "?p=month", "?p=custom&from=2026-09-01&to=2026-09-30", "?p=nonsense"):
            r = c.get(f"/django-admin/analytics/{q}")
            assert r.status_code == 200, q
        r = c.get("/django-admin/analytics/")
        assert "Biznes analitikasi" in r.content.decode() and "123 000 so&#x27;m" in r.content.decode().replace("so'm", "so&#x27;m")

    def test_staff_without_sales_permissions_is_refused(self):
        assert self._client().get("/django-admin/analytics/").status_code == 403

    def test_send_now_is_superuser_only_and_needs_configuration(self, settings):
        settings.TELEGRAM_ANALYTICS_BOT_TOKEN = ""
        user = get_user_model().objects.create(username=f"nza_{uuid.uuid4().hex[:6]}", is_staff=True)
        from django.contrib.auth.models import Permission

        from django.contrib.contenttypes.models import ContentType

        from apps.ordering.infrastructure.models import OrderModel
        from apps.pos.infrastructure.models import SaleModel

        # apps.pos has no top-level models module, so post_migrate never creates its permissions in the test database
        for model in (OrderModel, SaleModel):
            ct = ContentType.objects.get_for_model(model)
            Permission.objects.get_or_create(content_type=ct, codename=f"view_{ct.model}", defaults={"name": f"Can view {ct.model}"})
        user.user_permissions.add(*Permission.objects.filter(codename__in=("view_ordermodel", "view_salemodel")))
        c = Client()
        c.force_login(user)
        assert c.get("/django-admin/analytics/").status_code == 200
        assert c.post("/django-admin/analytics/send/", {"report": "bugun"}).status_code == 403
        su = self._client(is_superuser=True)
        r = su.post("/django-admin/analytics/send/", {"report": "bugun"}, follow=True)
        assert "sozlanmagan" in r.content.decode()


class TestDeeperSections:
    def test_heatmap_sellers_and_previous_line(self):
        now = timezone.now()
        _sale(now - timedelta(minutes=5), Decimal("100000"))
        _sale(now - timedelta(days=1, minutes=5), Decimal("40000"))  # yesterday, same time -> the comparison line
        r = ba.build(ba.period("today"))
        local = timezone.localtime(now - timedelta(minutes=5), TZ)
        assert r["heatmap"]["count"][local.weekday()][local.hour] == 1
        assert r["heatmap"]["peak"]["hour"] == local.hour
        assert sum(r["series"]["previous"]) == 40000.0 and sum(r["series"]["totals"]) == 100000.0
        assert r["sellers"][0]["revenue"] == Decimal("100000") and r["sellers"][0]["count"] == 1

    def test_export_is_a_workbook(self):
        user = get_user_model().objects.create(username=f"nza_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True)
        c = Client()
        c.force_login(user)
        r = c.get("/django-admin/analytics/export.xlsx?p=7d")
        assert r.status_code == 200 and r["Content-Type"].startswith("application/vnd.openxmlformats")
