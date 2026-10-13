"""Dashboard → Telegram botlar markazi: bot cards, previews (private ones for Analitika viewers), live check."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.platform.infrastructure import telegram_center as tc

pytestmark = [pytest.mark.django_db]


def _client(**flags):
    user = get_user_model().objects.create(username=f"t_{uuid.uuid4().hex[:6]}", is_staff=True, **flags)
    c = Client()
    c.force_login(user)
    return c


def _product():
    from apps.products.infrastructure import models as orm

    product = orm.Product.objects.create(id=uuid.uuid4(), status="published")
    orm.ProductTranslation.objects.create(product=product, locale_code="uz", name="Iso Whey <b>", slug=f"p-{uuid.uuid4().hex[:8]}")
    orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True)
    return product


def test_page_shows_the_three_bots_without_tokens(settings):
    settings.TELEGRAM_ORDERS_BOT_TOKEN = "999:SECRET-ORDERS-TOKEN"
    body = _client(is_superuser=True).get("/django-admin/telegram/status/").content.decode()
    assert "Mijozlar boti" in body and "Orders bot" in body and "Analytics bot" in body
    assert "SECRET-ORDERS-TOKEN" not in body
    assert "Xodim botlari obunachilari" in body  # superuser sees the subscriber list


def test_previews_render_the_rich_document_as_safe_page_html():
    _product()
    data = _client(is_superuser=True).get("/django-admin/telegram/preview/?kind=product").json()
    assert data["ok"] and "Iso Whey &lt;b&gt;" in data["html"]  # escaped by the rich helpers
    assert "tg-button" not in data["html"] and "tg://photo" not in data["html"]
    assert data["keyboard"] and data["size"] > 0


def test_private_previews_and_check_need_rights(settings, monkeypatch):
    plain = _client()
    assert plain.get("/django-admin/telegram/preview/?kind=order_post").status_code == 403
    assert plain.get("/django-admin/telegram/preview/?kind=showcase").status_code == 200
    assert plain.post("/django-admin/telegram/check/").status_code == 403
    assert "Xodim botlari obunachilari" not in plain.get("/django-admin/telegram/status/").content.decode()

    settings.TELEGRAM_BOT_TOKEN = "1:shop"
    settings.TELEGRAM_ORDERS_BOT_TOKEN = ""

    class Resp:
        def json(self):
            return {"ok": True, "result": {"username": "nutrizonebot", "first_name": "NutriZone"}}

    monkeypatch.setattr(tc.requests, "get", lambda url, timeout: Resp())
    bots = _client(is_superuser=True).post("/django-admin/telegram/check/").json()["bots"]
    assert bots["shop"] == {"ok": True, "username": "nutrizonebot", "name": "NutriZone"}
    assert bots["orders"]["ok"] is False


def test_to_page_html_converts_telegram_tags():
    from apps.telegram_bot.infrastructure import rich as R

    doc = R.RichDoc()
    doc.image("a", b"png-bytes")
    doc.add(R.collage(["a", "a"]), R.map_block(41.3, 69.2), R.buttons(R.button("Ochish", url="https://nutrizone.uz"), R.button("Savat", callback="menu:cart")))
    html = tc.to_page_html(doc)
    assert 'class="tgp-collage"' in html and "data:image/png;base64," in html and 'class="tgp-map"' in html
    assert '<a class="tgp-btn" href="https://nutrizone.uz"' in html and '<span class="tgp-btn">Savat</span>' in html
