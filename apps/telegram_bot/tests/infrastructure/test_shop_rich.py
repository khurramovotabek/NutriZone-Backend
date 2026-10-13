"""@nutrizonebot rich shop screens: showcase, product page, cart, my orders / one order, and the po:* buttons."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderChannel, OrderStatus
from apps.ordering.domain.value_objects import OrderNumber
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import _next_order_number, make_address, make_line_item
from apps.telegram_bot.infrastructure import shop_rich
from common.utils.money import Money

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def tg(settings, monkeypatch):
    """The customer bot 'live', every Telegram call recorded instead of sent."""
    from apps.telegram_bot.infrastructure import rich as R

    settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"
    settings.TELEGRAM_BOT_TOKEN = "1:shop"
    calls = []

    def fake_api(token, method, *, data=None, json_body=None, files=None):
        payload = dict(json_body or data or {})
        if "rich_message" in payload:
            payload["html"] = json.loads(payload["rich_message"])["html"]
        calls.append((method, payload))
        return {"message_id": len(calls)}

    monkeypatch.setattr(R, "_api", fake_api)
    return calls


def _customer(lang="uz"):
    from apps.identity.infrastructure.models import User

    tg_id = uuid.uuid4().int % 900_000_000
    return User.objects.create(id=uuid.uuid4(), phone_number=f"+99891{tg_id % 10_000_000:07d}", full_name="Mijoz", status="active", telegram_user_id=tg_id, language=lang)


def _product(name="Gold Whey", price="450000", description="Birinchi qator.\nIkkinchi qator.", old_price=None):
    from apps.pricing.infrastructure import models as pricing_orm
    from apps.products.infrastructure import models as orm

    product = orm.Product.objects.create(id=uuid.uuid4(), status="published", goals=["muscle"])
    orm.ProductTranslation.objects.create(product=product, locale_code="uz", name=name, slug=f"p-{uuid.uuid4().hex[:8]}", description=description)
    variant = orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True)
    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=Decimal(price),
                                                     compare_at_price_amount=Decimal(old_price) if old_price else None)
    return product, variant


def _callback(user, data):
    from apps.telegram_bot.interfaces.callback_router import handle_callback

    handle_callback({"from": {"id": user.telegram_user_id}, "message": {"chat": {"id": user.telegram_user_id}, "message_id": 5}, "data": data})


def test_product_page_has_price_goal_paragraphs_and_cart_buttons():
    product, variant = _product()
    doc = shop_rich.product_doc(product.id, "uz")
    assert "Gold Whey" in doc.html and "450 000 so&#x27;m" in doc.html and "Mushak" in doc.html
    assert "<p>Birinchi qator.</p><p>Ikkinchi qator.</p>" in doc.html  # description lines kept as paragraphs
    assert f'data="po:add:{variant.id}"' in doc.html and f'data="po:buy:{variant.id}"' in doc.html
    assert "Gold Whey" in doc.fallback
    assert shop_rich.product_doc(uuid.uuid4(), "uz") is None


def test_showcase_lists_products_with_open_buttons_in_the_shoppers_language():
    product, _variant = _product("Kreatin 300")
    doc = shop_rich.showcase_doc("ru")
    assert "Витрина NutriZone" in doc.html and "Kreatin 300" in doc.html
    assert f'data="po:open:{product.id}"' in doc.html


def test_order_page_is_only_for_its_owner_and_shows_product_names():
    owner, stranger = _customer(), _customer()
    _p, variant = _product("Omega 3")
    line = make_line_item(product_variant_id=variant.id, unit_price=Money(amount=Decimal("120000.00"), currency="UZS"), quantity=2)
    order = ordering_composition.build_order_repository().save(Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=owner.id, cart_id=uuid.uuid4(),
        shipping_address=make_address(city="Toshkent"), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=datetime.utcnow()))
    number = order.order_number.value
    doc = shop_rich.order_doc(number, owner.id, "uz")
    assert "Omega 3" in doc.html and "240 000" in doc.html and "Toshkent" in doc.html and "To&#x27;lov kutilmoqda" in doc.html
    assert shop_rich.order_doc(number, stranger.id, "uz") is None


def test_showcase_and_open_buttons_go_out_as_rich_messages(tg):
    user = _customer()
    product, variant = _product()
    with patch("apps.telegram_bot.interfaces.callback_router._send") as classic:
        _callback(user, "menu:products")
        _callback(user, f"po:open:{product.id}")
    assert [m for m, _p in tg] == ["sendRichMessage", "sendRichMessage"]
    assert "NutriZone vitrinasi" in tg[0][1]["html"] and "pm:best" in tg[0][1]["reply_markup"]
    assert "Gold Whey" in tg[1][1]["html"]
    classic.assert_not_called()


def test_add_button_puts_the_default_size_in_the_cart(tg):
    from apps.telegram_bot.application.services.shopping import TelegramCartService

    user = _customer()
    _product_row, variant = _product()
    with patch("apps.telegram_bot.interfaces.callback_router._send") as classic:
        _callback(user, f"po:add:{variant.id}")
    assert "menu:cart" in str(classic.call_args)  # the usual "added to cart" note with its buttons
    user.refresh_from_db()
    cart = TelegramCartService().view_cart(user)
    assert [(i["product_variant_id"], i["quantity"]) for i in cart["items"]] == [(str(variant.id), 1)]
    with patch("apps.telegram_bot.interfaces.callback_router._send"):
        _callback(user, "menu:cart")
    assert tg[-1][0] == "sendRichMessage" and "Gold Whey" in tg[-1][1]["html"] and "cart:increase" in tg[-1][1]["reply_markup"]


def test_classic_screen_when_telegram_refuses_the_rich_message(tg, monkeypatch):
    from apps.telegram_bot.infrastructure import rich as R

    user = _customer()
    _product()

    def refuse(*a, **k):
        raise R.RichSendError("sendRichMessage: Bad Request: unsupported")

    monkeypatch.setattr(R, "_api", refuse)
    with patch("apps.telegram_bot.interfaces.callback_router._send") as classic:
        _callback(user, "menu:products")
    assert classic.called  # the plain products menu still arrives


def test_sale_board_lists_only_discounted_products_biggest_saving_first(tg):
    user = _customer()
    _product("Oddiy Whey")
    small, _v1 = _product("Kreatin aksiya", price="90000", old_price="100000")
    big, _v2 = _product("BCAA aksiya", price="50000", old_price="100000")
    assert [c["id"] for c in shop_rich.sale_cards("uz")] == [str(big.id), str(small.id)]
    with patch("apps.telegram_bot.interfaces.callback_router._send") as classic:
        _callback(user, "pm:sale")
    html = tg[-1][1]["html"]
    assert tg[-1][0] == "sendRichMessage" and "Aksiyadagi mahsulotlar" in html and "Oddiy Whey" not in html
    assert "−50%" in html and f'data="po:open:{big.id}"' in html and "pm:salecards" in tg[-1][1]["reply_markup"]
    classic.assert_not_called()


def test_sale_board_says_so_when_nothing_is_discounted(tg):
    user = _customer()
    _product("Oddiy Whey")
    with patch("apps.telegram_bot.interfaces.callback_router._send") as classic:
        _callback(user, "pm:sale")
    assert "aksiyadagi mahsulot yo'q" in classic.call_args[0][1] and not tg
