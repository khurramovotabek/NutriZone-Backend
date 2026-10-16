import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.telegram_bot.infrastructure import channel_autopost
from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings, ProductStockFlag, TelegramPost

pytestmark = pytest.mark.django_db
NOON = datetime(2026, 10, 16, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))


def _product(name="Gold Whey", price=Decimal("500000"), old=None):
    from apps.pricing.infrastructure import models as pricing
    from apps.products.infrastructure import models as p

    product = p.Product.objects.create(id=uuid.uuid4(), status="published")
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
    variant = p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)
    pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=variant.id, base_price_amount=price, compare_at_price_amount=old)
    return product, variant


def _settings(**kw):
    s = ChannelAutoPostSettings.get()
    for k, v in {"enabled": True, "channel": "@nutrizonepit", "enabled_at": timezone.now() - timedelta(days=1), **kw}.items():
        setattr(s, k, v)
    s.save()
    return s


def test_caption_shows_discount_and_price():
    text = channel_autopost.caption("sale", {"name": "Gold <Whey>", "price": "400000", "compare_at_price": "500000", "discount_percent": 20, "stock_status": "in_stock"}, "ON")
    assert "−20%" in text and "<s>500 000</s>" in text and "400 000 so'm" in text and "Gold &lt;Whey&gt;" in text and "ON" in text


def test_quiet_hours_wrap_midnight():
    s = ChannelAutoPostSettings(quiet_from=22, quiet_to=9)
    assert channel_autopost._quiet(s, NOON.replace(hour=23)) and channel_autopost._quiet(s, NOON.replace(hour=3))
    assert not channel_autopost._quiet(s, NOON)


def test_disabled_does_nothing():
    assert channel_autopost.run(NOON) == {"skipped": "disabled"}


def test_events_are_posted_once_and_restock_detected():
    _settings(max_per_run=10)
    product, _v = _product("Sale Whey", Decimal("400000"), Decimal("500000"))
    cards = lambda products, locale: [{"id": str(x.id), "name": "Sale Whey", "slug": "s", "brand_id": None, "price": "400000", "compare_at_price": "500000",  # noqa: E731
                                       "discount_percent": 20, "stock_status": state["stock"], "rating_count": 0} for x in products]
    state = {"stock": "out_of_stock"}
    with patch("apps.products.infrastructure.selectors._cards_with_price_and_rating", side_effect=cards), patch("apps.telegram_bot.infrastructure.posts.queue") as queue:
        assert channel_autopost.run(NOON)["queued"] == 0  # first sight while sold out: only the flag is stored
        assert ProductStockFlag.objects.get(pk=product.id).in_stock is False
        state["stock"] = "in_stock"
        r = channel_autopost.run(NOON)
        assert r["queued"] == 1 and queue.call_count == 1  # back in stock (one post per product per run)
        assert TelegramPost.objects.get(source="restock").to_channel is True
        assert "400 000 so'm" in TelegramPost.objects.get(source="restock").body  # the sale price rides along
        for _ in range(3):
            channel_autopost.run(NOON)
        # "new" (published after enabling) is still announced once; the sale is not repeated -- it was in the restock post
        assert sorted(TelegramPost.objects.values_list("source", flat=True)) == ["new", "restock"]


def test_settings_page_renders(admin_client):
    r = admin_client.get("/django-admin/telegram_bot/channelautopostsettings/", follow=True)
    assert r.status_code == 200 and "Kanal avtopostlari" in r.content.decode()
