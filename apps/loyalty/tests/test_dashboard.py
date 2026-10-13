"""
Dashboard → Loyalty & Wallet: every page renders with its premium layout, the wallet card adjusts coins / pins a
tier only through the services (reason required), the ledger exports what is filtered, settings save, referral
codes show results and pending referrals can be voided.
"""
from __future__ import annotations

import io
import uuid
from decimal import Decimal

import pytest

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure import services
from apps.loyalty.infrastructure.models import LoyaltySettings, LoyaltyTier, Referral, ReferralCode, TierChange, Wallet, WalletTransaction

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _ladder():
    import importlib

    seed = importlib.import_module("apps.loyalty.infrastructure.migrations.0004_eight_tier_ladder")
    for slug, name, lo, hi, pct, icon, color, desc in seed.LADDER:
        LoyaltyTier.objects.update_or_create(slug=slug, defaults={"name": name, "min_spend": Decimal(lo), "max_spend": Decimal(hi) if hi else None,
                                                                  "percent": Decimal(pct), "icon": icon, "color": color, "description": desc})


def _customer(name="Dilshod Qodirov"):
    return User.objects.create(phone_number=f"+99891{uuid.uuid4().int % 10_000_000:07d}", full_name=name)


def _wallet_with(coins: int, name="Dilshod Qodirov"):
    user = _customer(name)
    services.adjust(user.id, coins, "test", actor="test")
    return Wallet.objects.get(user=user)


class TestPages:
    @pytest.mark.parametrize("url", ["/django-admin/loyalty/wallet/", "/django-admin/loyalty/wallettransaction/", "/django-admin/loyalty/loyaltytier/",
                                     "/django-admin/loyalty/referralcode/", "/django-admin/loyalty/referral/", "/django-admin/loyalty/wallet/add/"])
    def test_every_list_renders(self, admin_client, url):
        _wallet_with(5000)
        assert admin_client.get(url).status_code == 200

    def test_settings_redirects_to_the_single_row_and_renders(self, admin_client):
        r = admin_client.get("/django-admin/loyalty/loyaltysettings/")
        assert r.status_code == 302
        html = admin_client.get(r["Location"]).content.decode()
        assert "Mijoz uchun qanday" in html and "1 000 000 so&#x27;mlik buyurtma" in html

    def test_wallet_list_and_card(self, admin_client):
        w = _wallet_with(12000, "Malika Tursunova")
        assert "Malika Tursunova" in admin_client.get("/django-admin/loyalty/wallet/?coins=has").content.decode()
        html = admin_client.get(f"/django-admin/loyalty/wallet/{w.pk}/change/").content.decode()
        assert "Coin harakatlari" in html and "Qo&#x27;lda tuzatish" in html and "12 000" in html

    def test_tier_page_shows_the_ladder_and_editor(self, admin_client):
        html = admin_client.get("/django-admin/loyalty/loyaltytier/").content.decode()
        assert "Darajalar zinapoyasi" in html and 'name="form-TOTAL_FORMS"' in html and "data-nzl-pct" in html


class TestWalletCard:
    def test_adjust_needs_a_reason_and_writes_the_ledger(self, admin_client):
        w = _wallet_with(1000)
        r = admin_client.post(f"/django-admin/loyalty/wallet/{w.pk}/change/", {"adjust_amount": "500", "adjust_note": "", "set_tier": "", "tier_reason": ""})
        assert r.status_code == 200 and "sabab yozilishi shart" in r.content.decode()
        r = admin_client.post(f"/django-admin/loyalty/wallet/{w.pk}/change/", {"adjust_amount": "500", "adjust_note": "Shikoyat uchun bonus", "set_tier": "", "tier_reason": ""})
        assert r.status_code == 302
        w.refresh_from_db()
        assert w.balance == 1500
        assert WalletTransaction.objects.filter(wallet=w, kind="adjustment", amount=500, note="Shikoyat uchun bonus").exists()

    def test_cannot_go_negative(self, admin_client):
        w = _wallet_with(100)
        r = admin_client.post(f"/django-admin/loyalty/wallet/{w.pk}/change/", {"adjust_amount": "-500", "adjust_note": "x", "set_tier": "", "tier_reason": ""})
        assert r.status_code == 200 and "manfiy" in r.content.decode()

    def test_pin_a_tier(self, admin_client):
        w = _wallet_with(100)
        gold = LoyaltyTier.objects.get(slug="gold")
        r = admin_client.post(f"/django-admin/loyalty/wallet/{w.pk}/change/", {"adjust_amount": "", "adjust_note": "", "set_tier": gold.pk, "tier_reason": "Hamkor"})
        assert r.status_code == 302
        w.refresh_from_db()
        assert w.tier_override_id == gold.pk and TierChange.objects.filter(wallet=w, kind="manual").exists()


class TestLedger:
    def test_filters_by_kind_and_exports_xlsx(self, admin_client):
        _wallet_with(700, "Export Mijoz")
        html = admin_client.get("/django-admin/loyalty/wallettransaction/?kind__exact=adjustment").content.decode()
        assert "Export Mijoz" in html and "Qo&#x27;lda tuzatish" in html
        r = admin_client.get("/django-admin/loyalty/wallettransaction/export.xlsx?kind__exact=adjustment")
        assert r.status_code == 200 and r["Content-Type"].startswith("application/vnd.openxmlformats")
        from openpyxl import load_workbook

        rows = list(load_workbook(io.BytesIO(r.content)).active.values)
        assert rows[0][0] == "Sana" and any(row[1] == "Export Mijoz" and row[4] == 700 for row in rows[1:])

    def test_ledger_is_read_only(self, admin_client):
        t = WalletTransaction.objects.filter(wallet=_wallet_with(10)).first()
        assert admin_client.post(f"/django-admin/loyalty/wallettransaction/{t.pk}/delete/").status_code == 403


class TestSettingsAndReferrals:
    def test_settings_save(self, admin_client):
        obj = LoyaltySettings.load()
        data = {f.name: getattr(obj, f.name) for f in LoyaltySettings._meta.fields if f.name not in ("id", "updated_at")}
        data.update({"max_redeem_percent": 40, "redeem_enabled": "on", "referral_enabled": "on", "telegram_notifications": "on"})
        r = admin_client.post(f"/django-admin/loyalty/loyaltysettings/{obj.pk}/change/", data)
        assert r.status_code == 302
        assert LoyaltySettings.load().max_redeem_percent == 40

    def test_referral_code_results_and_void(self, admin_client):
        owner, friend = _customer("Taklifchi"), _customer("Do'st")
        ReferralCode.objects.create(user=owner, code="NZTEST01")
        ref = Referral.objects.create(referrer=owner, referee=friend, code="NZTEST01", channel="telegram")
        html = admin_client.get("/django-admin/loyalty/referralcode/").content.decode()
        assert "NZTEST01" in html and "?ref=NZTEST01" in html
        html = admin_client.get("/django-admin/loyalty/referral/?status__exact=pending").content.decode()
        assert "Taklifchi" in html and "Telegram bot" in html
        admin_client.post("/django-admin/loyalty/referral/", {"action": "void_selected", "_selected_action": [ref.pk], "index": 0})
        ref.refresh_from_db()
        assert ref.status == "void"
