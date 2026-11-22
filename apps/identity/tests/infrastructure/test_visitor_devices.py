"""
Visitor-device statistics: User-Agent + hints classification, the storefront beacon, the Dashboard panel / list, and the
access-log backfill (script-less crawlers dropped, idempotent).
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.core.management import call_command
from django.test import Client

from apps.identity.infrastructure.models import VisitorDay, VisitorDevice
from apps.identity.infrastructure.visitors import classify, record_visit, stats

pytestmark = pytest.mark.django_db

ANDROID = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36"
ANDROID_MODEL = "Mozilla/5.0 (Linux; Android 13; SM-A536B Build/TP1A.220624.014) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 Mobile/15E148 Safari/604.1"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
TABLET = "Mozilla/5.0 (Linux; Android 14; SM-X210) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"


class TestClassify:
    def test_android_phone_with_client_hints(self):
        d = classify(ANDROID, {"md": "SM-A546E", "pv": "14.0.0", "w": "384", "h": "832"})
        assert (d["device_class"], d["os"], d["os_version"], d["brand"], d["model"], d["screen"], d["browser"]) == \
               ("mobile", "Android", "14", "Samsung", "SM-A546E", "384x832", "Chrome")

    def test_model_from_ua_and_frozen_ua_has_no_model(self):
        assert classify(ANDROID_MODEL)["brand"] == "Samsung"
        assert classify(ANDROID)["model"] == "" and classify(ANDROID)["os_version"] == "10"

    def test_iphone_ipad_tablet_desktop(self):
        assert (classify(IPHONE)["os"], classify(IPHONE)["os_version"], classify(IPHONE)["device_class"], classify(IPHONE)["brand"]) == ("iOS", "18.7", "mobile", "Apple")
        assert classify(MAC)["device_class"] == "desktop"
        ipad = classify(MAC, {"tp": "5"})
        assert (ipad["os"], ipad["device_class"], ipad["model"]) == ("iOS", "tablet", "iPad")
        assert classify(TABLET)["device_class"] == "tablet"

    def test_windows_11_only_from_hints(self):
        assert classify(WIN)["os_version"] == "10/11"
        assert classify(WIN, {"pv": "15.0.0"})["os_version"] == "11"
        assert classify(WIN, {"pv": "10.0.0"})["os_version"] == "10"

    def test_in_app_browsers(self):
        assert classify(IPHONE, {"tg": "1"})["in_app"] == "telegram"
        assert classify(ANDROID + " Telegram-Android/11.5.3")["in_app"] == "telegram"
        assert classify(IPHONE + " Instagram 350.0")["in_app"] == "instagram"
        assert classify(IPHONE.replace(" Safari/604.1", "").replace("Version/18.7 ", ""))["browser"] == "iOS ilova ichida"

    @pytest.mark.parametrize("ua", [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36; compatible; OAI-SearchBot/1.4",
        "Mozilla/5.0 (compatible; CensysInspect/1.1; +https://about.censys.io/)", "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X) Chrome/120 Mobile Safari/537.36 (compatible; Googlebot/2.1)",
        "node", "", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/120.0 Safari/537.36",
    ])
    def test_bots(self, ua):
        assert classify(ua)["is_bot"]

    def test_people_are_not_bots(self):
        assert not any(classify(u)["is_bot"] for u in (ANDROID, IPHONE, MAC, WIN, TABLET))


class TestRecord:
    def test_same_browser_same_day_is_one_device(self):
        record_visit("v" * 20, IPHONE, {"w": "390", "h": "844"})
        record_visit("v" * 20, IPHONE)
        d = VisitorDevice.objects.get()
        assert (d.days, d.hits, d.screen) == (1, 2, "390x844")  # a hit without hints keeps the screen it already knew
        assert VisitorDay.objects.get().hits == 2

    def test_stats_split(self):
        record_visit("a" * 20, IPHONE)
        record_visit("b" * 20, ANDROID, {"md": "2312DRA50G"})
        record_visit("c" * 20, WIN)
        record_visit("d" * 20, "Googlebot/2.1")
        s = stats(30)
        cls = {r["key"]: r for r in s["classes"]}
        assert s["total"] == 3 and s["bots"] == 1
        assert cls["mobile"]["n"] == 2 and cls["mobile"]["pct"] == 66.7 and cls["desktop"]["pct"] == 33.3
        assert {r["key"] for r in s["os"]} == {"iOS", "Android", "Windows"}
        assert {r["key"] for r in s["brands"]} == {"Apple", "Xiaomi"}


class TestBeacon:
    def test_form_beacon_counts_once_a_minute(self):
        c = Client()
        vid = uuid.uuid4().hex
        r = c.post("/api/v1/identity/visits", {"v": vid, "w": 390, "h": 844, "tg": 1}, HTTP_USER_AGENT=IPHONE)
        assert r.status_code == 204
        c.post("/api/v1/identity/visits", {"v": vid}, HTTP_USER_AGENT=IPHONE)
        d = VisitorDevice.objects.get()
        assert (d.os, d.in_app, d.screen, d.hits) == ("iOS", "telegram", "390x844", 1)

    def test_bad_id_ignored(self):
        assert Client().post("/api/v1/identity/visits", {"v": "x"}, HTTP_USER_AGENT=IPHONE).status_code == 204
        assert not VisitorDevice.objects.exists()


class TestDashboard:
    @pytest.fixture
    def boss(self):
        client = Client()
        client.force_login(AuthUser.objects.create_superuser(username=f"boss_{uuid.uuid4().hex[:6]}", password="test-pass-12345"))
        return client

    @pytest.mark.parametrize("url", ["/django-admin/identity/device/", "/django-admin/identity/device/?period=7", "/django-admin/identity/visitordevice/",
                                     "/django-admin/identity/visitordevice/?period=all&device_class=mobile", "/django-admin/identity/visitordevice/?period=1"])
    def test_pages_render_with_panel(self, boss, url):
        record_visit("a" * 20, IPHONE)
        record_visit("b" * 20, WIN)
        r = boss.get(url)
        assert r.status_code == 200
        html = r.content.decode()
        assert "Tashrif buyurgan qurilmalar" in html and "Telefon yoki kompyuter" in html and "50%" in html.replace("50.0%", "50%")

    def test_empty_state(self, boss):
        assert "Hali tashrif ma" in boss.get("/django-admin/identity/device/").content.decode()


class TestLogImport:
    def _log(self, tmp_path):
        lines = []
        for ip, ua, js in (("1.1.1.1", IPHONE, True), ("2.2.2.2", WIN, True), ("3.3.3.3", MAC, False), ("4.4.4.4", "Mozilla/5.0 (compatible; AhrefsBot/7.0)", True)):
            lines.append(f'{ip} - - [21/Nov/2026:10:00:00 +0100] "GET /products/x HTTP/1.1" 200 5000 "-" "{ua}"')
            lines.append(f'{ip} - - [21/Nov/2026:10:00:05 +0100] "GET /ru HTTP/1.1" 200 5000 "-" "{ua}"')
            if js:
                lines.append(f'{ip} - - [21/Nov/2026:10:00:01 +0100] "GET /_next/static/chunks/a.js HTTP/1.1" 200 5000 "-" "{ua}"')
        lines.append('1.1.1.1 - - [21/Nov/2026:10:00:09 +0100] "GET /api/v1/brands HTTP/1.1" 200 5 "-" "node"')
        p = tmp_path / "access.log"
        p.write_text("\n".join(lines) + "\n")
        return str(p)

    def test_import_drops_scriptless_crawlers_and_is_idempotent(self, tmp_path):
        path = self._log(tmp_path)
        call_command("import_visit_log", path)
        call_command("import_visit_log", path)
        assert sorted(VisitorDevice.objects.values_list("os", flat=True)) == ["Windows", "iOS"]
        assert all(d.hits == 2 and d.days == 1 and d.source == "log" for d in VisitorDevice.objects.all())

    def test_until_excludes_beacon_days(self, tmp_path):
        call_command("import_visit_log", self._log(tmp_path), until="2026-11-21")
        assert not VisitorDevice.objects.exists()
