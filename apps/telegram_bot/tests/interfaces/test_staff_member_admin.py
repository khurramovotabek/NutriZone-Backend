"""Dashboard → Telegram → Xodimlar (Orders bot): TelegramStaffMember list/add/edit, superusers only."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber, TelegramStaffMember

pytestmark = pytest.mark.django_db
LIST = "/django-admin/telegram_bot/telegramstaffmember/"


@pytest.fixture
def root():
    c = Client()
    c.force_login(get_user_model().objects.create_superuser("root_sm", "r@example.com", "x"))
    return c


def test_staff_without_superuser_is_refused():
    c = Client()
    c.force_login(get_user_model().objects.create_user("staff_sm", password="x", is_staff=True))
    assert c.get(LIST).status_code == 403
    assert c.post(LIST + "add/", {"telegram_user_id": 5, "is_active": "on"}).status_code == 403
    assert not TelegramStaffMember.objects.exists()


def test_list_shows_members_and_bot_state(root):
    TelegramStaffMember.objects.create(telegram_user_id=1323573501, full_name="Otabek")
    TelegramBotSubscriber.objects.create(bot="orders", chat_id=1323573501, telegram_user_id=1323573501, display_name="Otabek", username="otabek")
    TelegramStaffMember.objects.create(telegram_user_id=42, full_name="Menejer", is_active=False)
    html = root.get(LIST).content.decode()
    assert "Otabek" in html and "@otabek" in html and "Ulangan" in html and "Menejer" in html and "/start bosmagan" in html


def test_add_by_picking_an_orders_bot_subscriber(root):
    TelegramBotSubscriber.objects.create(bot="orders", chat_id=777, telegram_user_id=777, display_name="Kassir Ali")
    assert "Kassir Ali" in root.get(LIST + "add/").content.decode()
    r = root.post(LIST + "add/", {"pick": "777", "telegram_user_id": "", "full_name": "", "is_active": "on"})
    assert r.status_code == 302, r.content.decode()[:3000]
    m = TelegramStaffMember.objects.get(pk=777)
    assert m.full_name == "Kassir Ali" and m.is_active


def test_add_manually_validates_ids(root):
    assert root.post(LIST + "add/", {"telegram_user_id": "-100123", "is_active": "on"}).status_code == 200
    assert root.post(LIST + "add/", {"telegram_user_id": "", "is_active": "on"}).status_code == 200
    assert not TelegramStaffMember.objects.exists()
    assert root.post(LIST + "add/", {"telegram_user_id": "555", "full_name": "Sardor", "is_active": "on"}).status_code == 302
    assert root.post(LIST + "add/", {"telegram_user_id": "555", "is_active": "on"}).status_code == 200  # duplicate refused
    assert TelegramStaffMember.objects.get(pk=555).full_name == "Sardor"


def test_edit_and_deactivate(root):
    TelegramStaffMember.objects.create(telegram_user_id=900, full_name="Old")
    page = root.get(LIST + "900/change/")
    assert page.status_code == 200
    assert root.post(LIST + "900/change/", {"full_name": "New", "telegram_user_id": "900"}).status_code == 302
    m = TelegramStaffMember.objects.get(pk=900)
    assert m.full_name == "New" and not m.is_active
    r = root.post(LIST, {"action": "activate", "_selected_action": ["900"]})
    assert r.status_code == 302 and TelegramStaffMember.objects.get(pk=900).is_active
