"""Nazorat markazi: suspicious till operations, operational incidents, exactly-once findings, auto-close, Telegram, page."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.platform.infrastructure import control_center as cc
from apps.platform.infrastructure.models import ControlAlert

pytestmark = [pytest.mark.django_db]
TZ = ZoneInfo("Asia/Tashkent")


def _store(**kw):
    from apps.stores.infrastructure.models import Store

    defaults = {"name": "Olmazor", "slug": f"s-{uuid.uuid4().hex[:8]}", "status": "active", "kind": "store"}
    defaults.update(kw)
    return Store.objects.create(**defaults)


def _sale(store, *, amount=Decimal("100000"), discount=Decimal("0"), status="completed", when=None, cashier=None, qty=1):
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    when = when or timezone.now() - timedelta(minutes=5)
    sale = SaleModel.objects.create(branch_id=store.id, cashier_id=cashier or uuid.uuid4(), status=status, channel="store",
                                    completed_at=when if status != "voided" else None, voided_at=when if status == "voided" else None,
                                    discount_amount=discount, receipt_number=f"NZ-{uuid.uuid4().hex[:6]}" if status != "voided" else None,
                                    payments=[{"method": "cash", "amount": str(amount * qty - discount)}])
    SaleLineItemModel.objects.create(sale=sale, product_id=uuid.uuid4(), quantity=qty, unit_price_amount=amount, unit_price_currency="UZS")
    return sale


def _refund(sale, *, after=timedelta(minutes=5), cashier=None, cash=Decimal("100000")):
    from apps.pos.infrastructure.models import SaleRefundModel

    r = SaleRefundModel.objects.create(sale=sale, number=f"R-{uuid.uuid4().hex[:5]}", cashier_id=cashier or sale.cashier_id, value=cash, amount=cash,
                                       split={"cash": str(cash)}, lines=[])
    SaleRefundModel.objects.filter(pk=r.pk).update(created_at=sale.completed_at + after)
    return r


def kinds() -> list[str]:
    return sorted(ControlAlert.objects.values_list("kind", flat=True))


class TestRiskRules:
    def test_big_discount_by_percent_and_amount(self):
        st = _store()
        _sale(st, amount=Decimal("100000"), discount=Decimal("10000"))   # 10 % -- fine
        big = _sale(st, amount=Decimal("100000"), discount=Decimal("20000"))  # 20 % -> warning
        huge = _sale(st, amount=Decimal("100000"), discount=Decimal("40000"))  # 40 % -> critical
        cc.scan()
        rows = {a.key: a for a in ControlAlert.objects.filter(kind="big_discount")}
        assert set(rows) == {f"big_discount:{big.id}", f"big_discount:{huge.id}"}
        assert rows[f"big_discount:{huge.id}"].severity == "critical" and rows[f"big_discount:{big.id}"].severity == "warning"
        assert rows[f"big_discount:{big.id}"].store_id == st.id

    def test_quick_refund_and_refund_burst(self):
        st = _store()
        cashier = uuid.uuid4()
        sales = [_sale(st, cashier=cashier) for _ in range(3)]
        _refund(sales[0], after=timedelta(minutes=10))  # quick
        _refund(sales[1], after=timedelta(hours=2))     # slow, not quick
        _refund(sales[2], after=timedelta(hours=3))
        cc.scan()
        assert kinds().count("quick_refund") == 1
        assert kinds().count("refund_burst") == 1  # 3 returns by one cashier (default threshold 3)

    def test_void_burst_counts_only_receipts_with_items(self):
        st = _store()
        cashier = uuid.uuid4()
        for _ in range(3):
            _sale(st, cashier=cashier, status="voided")
        cc.scan()
        assert kinds() == ["void_burst"]

    def test_cash_shortage_is_critical(self):
        from apps.stores.infrastructure.models import CashSession

        st = _store()
        CashSession.objects.create(store=st, status="closed", closed_at=timezone.now(), expected_cash=Decimal("500000"),
                                   counted_cash=Decimal("400000"), cash_difference=Decimal("-100000"))
        CashSession.objects.create(store=_store(), status="closed", closed_at=timezone.now(), expected_cash=Decimal("500000"),
                                   counted_cash=Decimal("490000"), cash_difference=Decimal("-10000"))  # under the threshold
        cc.scan()
        a = ControlAlert.objects.get()
        assert a.kind == "cash_difference" and a.severity == "critical" and "kamomad" in a.title

    def test_thresholds_come_from_settings(self):
        from apps.platform.infrastructure.models import ControlSettings

        cfg = ControlSettings.load()
        cfg.discount_percent = 50
        cfg.discount_amount = Decimal("1000000")
        cfg.save()
        _sale(_store(), discount=Decimal("20000"))
        cc.scan()
        assert not ControlAlert.objects.exists()


class TestIncidents:
    def test_overdue_shift_closes_itself_once_the_shift_is_closed(self):
        from apps.stores.infrastructure.models import CashSession

        s = CashSession.objects.create(store=_store())
        CashSession.objects.filter(pk=s.pk).update(opened_at=timezone.now() - timedelta(hours=20))
        cc.scan()
        a = ControlAlert.objects.get(kind="shift_overdue")
        assert a.resolved_at is None
        CashSession.objects.filter(pk=s.pk).update(status="closed", closed_at=timezone.now())
        cc.scan()
        a.refresh_from_db()
        assert a.resolved_at is not None and a.resolved_by_name == "Avtomatik"

    def test_shift_missing_only_for_working_kassas_after_grace(self):
        from apps.stores.infrastructure.models import CashSession

        now = datetime(2026, 10, 12, 11, 0, tzinfo=TZ)  # Monday 11:00
        hours = {"mon": {"open": "10:00", "close": "20:00", "closed": False}}
        used = _store(pos_pin_hash="x", working_hours=hours)
        _sale(used, when=now - timedelta(days=2))
        unused = _store(pos_pin_hash="x", working_hours=hours)  # never sold -> not a working kassa
        assert [f["key"] for f in cc.rule_shift_missing(cc.settings_obj(), now, cc._store_map())] == [f"shift_missing:{used.id}:2026-10-12"]
        assert cc.rule_shift_missing(cc.settings_obj(), now - timedelta(minutes=30), cc._store_map()) == []  # 10:30: inside the 45 min grace
        CashSession.objects.create(store=used)
        assert cc.rule_shift_missing(cc.settings_obj(), now, cc._store_map()) == []
        assert unused  # noqa: B018

    def test_special_hours_override_weekly_schedule(self):
        st = _store(working_hours={"mon": {"open": "10:00", "close": "20:00"}}, special_hours=[{"date": "2026-10-12", "closed": True}])
        assert cc.opening_time(st, datetime(2026, 10, 12).date()) == (None, None)
        assert cc.opening_time(st, datetime(2026, 10, 19).date())[0].hour == 10


class TestScan:
    def test_exactly_once_and_one_broken_rule_never_stops_the_rest(self):
        _sale(_store(), discount=Decimal("50000"))
        with mock.patch.object(cc, "OPS_RULES", (lambda *a: 1 / 0,)):
            first = cc.scan()
        assert first["created"] == 1 and first["failed"]
        assert cc.scan()["created"] == 0
        assert ControlAlert.objects.count() == 1

    def test_disabled(self):
        from apps.platform.infrastructure.models import ControlSettings

        ControlSettings.objects.update_or_create(pk=1, defaults={"enabled": False})
        assert cc.scan() == {"skipped": "disabled"}

    def test_resolve_respects_store_scope(self):
        mine, other = _store(), _store()
        _sale(other, discount=Decimal("90000"))
        cc.scan()
        a = ControlAlert.objects.get()
        assert cc.resolve(a.id, "Ega", store_ids={mine.id}) is False
        assert cc.resolve(a.id, "Rahbar") is True
        assert cc.resolve(a.id, "Rahbar") is False  # already closed


class TestTelegram:
    def test_company_gets_everything_owner_only_their_branch_one_message_each(self):
        a_store, b_store = _store(), _store()
        _sale(a_store, discount=Decimal("90000"))
        _sale(b_store, discount=Decimal("90000"))
        cc.scan()
        sent = []
        with mock.patch("apps.telegram_bot.infrastructure.analytics_bot.is_live", return_value=True), \
                mock.patch("apps.telegram_bot.infrastructure.analytics_bot.token", return_value="t"), \
                mock.patch.object(cc, "audience", return_value=[{"chat_id": "1", "store_ids": None}, {"chat_id": "2", "store_ids": {a_store.id}}]), \
                mock.patch("apps.telegram_bot.infrastructure.rich.send", side_effect=lambda token, chat, doc, kb=None: sent.append((chat, doc, kb)) or 1):
            out = cc.notify_pending()
            again = cc.notify_pending()
        assert out == {"pending": 2, "sent": 2, "failed": 0} and again == {"pending": 0}
        by_chat = {c: (doc, kb) for c, doc, kb in sent}
        assert "2 ta yangi signal" in by_chat["1"][0].fallback
        assert any(b.get("callback_data", "").startswith("an:ack:") for row in by_chat["2"][1] for b in row)  # single alert -> ack button

    def test_nothing_is_marked_sent_when_telegram_is_off(self):
        _sale(_store(), discount=Decimal("90000"))
        cc.scan()
        with mock.patch("apps.telegram_bot.infrastructure.analytics_bot.is_live", return_value=False):
            assert cc.notify_pending()["skipped"] == "telegram off"
        assert ControlAlert.objects.filter(notified_at__isnull=True).count() == 1


class TestPage:
    def _client(self, **flags):
        user = get_user_model().objects.create(username=f"nzc_{uuid.uuid4().hex[:6]}", is_staff=True, **flags)
        c = Client()
        c.force_login(user)
        return c

    def test_page_resolve_and_settings(self):
        _sale(_store(name="Chilonzor"), discount=Decimal("90000"))
        cc.scan()
        c = self._client(is_superuser=True)
        r = c.get("/django-admin/control/")
        assert r.status_code == 200 and "Nazorat markazi" in r.content.decode() and "Chilonzor" in r.content.decode()
        a = ControlAlert.objects.get()
        r = c.post("/django-admin/control/resolve/", {"alert": str(a.id), "back": "https://evil.example/"})
        assert r.status_code == 302 and r["Location"] == "/django-admin/control/"
        a.refresh_from_db()
        assert a.resolved_at is not None
        r = c.post("/django-admin/control/settings/", {"enabled": "on", "discount_percent": "25", "discount_amount": "300 000", "quick_refund_minutes": "20",
                                                       "refunds_per_cashier": "4", "voids_per_cashier": "4", "cash_difference": "70000",
                                                       "shift_open_grace_minutes": "30", "shift_max_hours": "15", "payment_errors": "5", "forecast_days": "10"})
        cfg = cc.settings_obj()
        assert r.status_code == 302 and cfg.discount_percent == 25 and cfg.discount_amount == Decimal("300000") and cfg.telegram_enabled is False

    def test_bad_threshold_is_rejected_and_staff_cannot_edit(self):
        c = self._client(is_superuser=True)
        c.post("/django-admin/control/settings/", {"enabled": "on", "discount_percent": "500"})
        assert cc.settings_obj().discount_percent == 15
        assert self._client().get("/django-admin/control/").status_code == 403
        assert self._client().post("/django-admin/control/settings/", {}).status_code == 403


# ---------------------------------------------------------------- phase 2: stock


def _variant():
    from apps.stores.tests.interfaces.test_my_store_products import _make_variant

    return _make_variant(barcode=f"479{uuid.uuid4().int % 10**10:010d}", status="active")


def _put(store, v, qty, batch="", expiry=None):
    from django.db import transaction

    from apps.stores.infrastructure import stock_service

    with transaction.atomic():
        stock_service.move(store, v.id, qty, "receipt", reference="T", mirror=False, batch_number=batch, expiry_date=expiry)


def _sell(store, v, qty, days_ago=1):
    from django.db import transaction

    from apps.stores.infrastructure import stock_service
    from apps.stores.infrastructure.models import StockMovement

    with transaction.atomic():
        m = stock_service.move(store, v.id, -qty, "sale", reference="S", mirror=False)
    from apps.products.tests.stock_helpers import backdate_movement

    backdate_movement(m.pk, timezone.now() - timedelta(days=days_ago))


class TestStockRules:
    def _setup(self):
        from apps.stores.infrastructure.models import ReorderRule

        wh = _store(kind="warehouse", name="Sklad")
        shop = _store(name="Olmazor")
        v = _variant()
        _put(wh, v, 50)
        _put(shop, v, 3)
        ReorderRule.objects.create(store=shop, product_variant_id=v.id, min_quantity=5, target_quantity=20)
        return wh, shop, v

    def test_low_stock_then_transfer_request_creates_one_draft(self):
        from apps.stores.infrastructure.models import StockTransfer

        wh, shop, v = self._setup()
        cc.scan()
        a = ControlAlert.objects.get(kind="low_stock")
        assert a.store_id == shop.id and "3 dona qoldi" in a.title
        res = cc.request_transfer_for_alert(a.id, "Sinov")
        assert res["ok"] and res["units"] == 17 and res["transfer"].source_id == wh.id and res["transfer"].status == "draft"
        again = cc.request_transfer_for_alert(a.id, "Sinov")  # the draft is already counted as "on the way"
        assert again["ok"] is False and StockTransfer.objects.count() == 1
        cc.scan()
        a.refresh_from_db()
        assert a.resolved_at is not None and a.resolved_by_name == "Avtomatik"

    def test_owner_scope_is_enforced(self):
        _wh, shop, _v = self._setup()
        cc.scan()
        a = ControlAlert.objects.get(kind="low_stock")
        assert cc.request_transfer_for_alert(a.id, "Begona", allowed_store_ids={uuid.uuid4()})["ok"] is False

    def test_reopens_when_back_but_a_manual_ack_snoozes_a_day(self):
        from apps.stores.infrastructure.models import ReorderRule

        _wh, shop, v = self._setup()
        cc.scan()
        a = ControlAlert.objects.get(kind="low_stock")
        cc.resolve(a.id, "Rahbar")
        cc.scan()
        a.refresh_from_db()
        assert a.resolved_at is not None  # still low, but acknowledged: quiet for 24 h
        ControlAlert.objects.filter(pk=a.pk).update(resolved_at=timezone.now() - timedelta(hours=25))
        cc.scan()
        a.refresh_from_db()
        assert a.resolved_at is None and a.notified_at is None  # back on the list and sent again
        ReorderRule.objects.filter(store=shop).update(min_quantity=1, target_quantity=5)
        cc.scan()
        a.refresh_from_db()
        assert a.resolved_by_name == "Avtomatik"

    def test_forecast_from_sales_speed(self):
        wh = _store(kind="warehouse", name="Sklad")
        shop = _store(name="Chilonzor")
        v = _variant()
        _put(wh, v, 50)
        _put(shop, v, 100)
        _sell(shop, v, 90)  # 3 a day for 30 days, 10 left -> ~3 days
        found = cc.rule_stock_forecast(cc.settings_obj(), timezone.now(), cc._store_map())
        assert [f["kind"] for f in found] == ["stock_forecast"] and "≈3 kunda" in found[0]["title"]

    def test_expiry_tiers_once_each_and_typo_dates(self):
        wh = _store(kind="warehouse", name="Sklad")
        v = _variant()
        today = timezone.localdate()
        _put(wh, v, 4, "B-SOON", today + timedelta(days=20))
        _put(wh, v, 6, "B-LATER", today + timedelta(days=75))
        _put(wh, v, 2, "B-TYPO", date(2, 5, 1))
        tiers = sorted(f["key"].split(":")[-1] for f in cc.rule_expiry(cc.settings_obj(), timezone.now(), cc._store_map()))
        assert tiers == ["30", "90", "typo"]


class TestReceiptExpiryValidation:
    def test_typo_years_are_refused(self):
        from apps.stores.infrastructure import stock_service
        from common.exceptions import ValidationFailed

        wh = _store(kind="warehouse", name="Sklad")
        v = _variant()
        for bad in ("0002-05-01", "2207-01-01"):
            with pytest.raises(ValidationFailed):
                stock_service.post_receipt(wh, [{"variant_id": str(v.id), "quantity": 1, "expiry": bad}], "Sinov")
        r = stock_service.post_receipt(wh, [{"variant_id": str(v.id), "quantity": 1, "expiry": (timezone.localdate() + timedelta(days=400)).isoformat()}], "Sinov")
        assert r.total_units == 1


class TestStockKeyboard:
    def test_single_stock_alert_offers_transfer_request(self):
        _wh, shop, _v = TestStockRules()._setup()
        cc.scan()
        a = ControlAlert.objects.select_related("store").get(kind="low_stock")
        kb = cc.alert_keyboard([a])
        assert kb[0][0]["callback_data"] == f"an:trq:{a.id}"
        assert any(b.get("callback_data") == f"an:ack:{a.id}" for row in kb for b in row)
