"""The Telegram bot obeys the same stock rule as the website: no sold-out sizes in the cart, no growing past the shelf."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.cart.infrastructure.stock_guard import OutOfStock
from apps.identity.infrastructure import models as identity_orm
from apps.products.infrastructure import models as p_models
from apps.stores.infrastructure.models import Store, StoreProductStock
from apps.telegram_bot.application.services.shopping import TelegramCartService

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _user():
    return identity_orm.User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name="Bot", status="active",
                                            telegram_user_id=880000000 + uuid.uuid4().int % 100000)


def _variant(units: int):
    owner = _user()
    store = Store.objects.create(id=uuid.uuid4(), owner=owner, name="Filial", slug=f"f-{uuid.uuid4().hex[:6]}")
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", weight_value=1, weight_unit="kg")
    StoreProductStock.objects.create(store=store, product_variant=variant, quantity=units)
    return variant


@override_settings(CART_STOCK_GUARD=True)
def test_sold_out_size_is_refused_in_the_bot():
    with pytest.raises(OutOfStock) as exc:
        TelegramCartService().add_item(_user(), _variant(0).id, quantity=1)
    assert exc.value.available == 0


@override_settings(CART_STOCK_GUARD=True)
def test_bot_cart_can_not_grow_past_the_shelf(monkeypatch):
    from apps.pricing.infrastructure import composition as pricing_composition

    variant = _variant(1)
    user = _user()

    class _Snap:
        id = uuid.uuid4()

        class locked_price:
            amount = Decimal("100000")
            currency = "UZS"

    monkeypatch.setattr(pricing_composition, "build_issue_variant_price_snapshot", lambda _uid: type("S", (), {"execute": lambda self, **kw: _Snap()})())
    TelegramCartService().add_item(user, variant.id, quantity=1)
    user.refresh_from_db()
    with pytest.raises(OutOfStock):
        TelegramCartService().add_item(user, variant.id, quantity=1)
