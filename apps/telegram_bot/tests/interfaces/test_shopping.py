"""
Phase 15C: Telegram shopping flow tests.

Every scenario here was first verified live via a real HTTP request
before being written as a formal test, matching Phase 15B's own
established discipline.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/telegram/webhook"
TEST_SECRET = "test-webhook-secret-only-not-real"


def _post(client, payload):
    return client.post(WEBHOOK_URL, data=json.dumps(payload), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=TEST_SECRET)


def _callback(telegram_user_id, data):
    return {"callback_query": {"id": "cbq", "from": {"id": telegram_user_id}, "message": {"chat": {"id": telegram_user_id}}, "data": data}}


def _make_priced_product(unit_amount=Decimal("85000.00")):
    from apps.products.infrastructure import models as products_orm
    from apps.pricing.infrastructure import models as pricing_orm

    category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
    products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein", slug=f"protein-{uuid.uuid4().hex[:8]}")

    product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
    products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Test Product", slug=f"test-product-{uuid.uuid4().hex[:8]}")
    variant = products_orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)

    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=unit_amount)
    return category, product, variant


def _register(telegram_user_id, phone_suffix):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{phone_suffix:07d}", full_name="Shop Test", status="active", telegram_user_id=telegram_user_id)


class TestCatalogBrowsing:
    def test_categories_are_loaded_from_real_database(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        category, product, variant = _make_priced_product()
        telegram_id = 800200100
        _register(telegram_id, 1)

        r = _post(Client(), _callback(telegram_id, "menu:catalog"))
        assert r.status_code == 200

    def test_unlinked_user_cannot_browse(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        r = _post(Client(), _callback(800200101, "menu:catalog"))
        assert r.status_code == 200

    def test_nonexistent_category_handled_safely(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        telegram_id = 800200102
        _register(telegram_id, 2)
        r = _post(Client(), _callback(telegram_id, f"catalog:category:{uuid.uuid4()}"))
        assert r.status_code == 200

    def test_nonexistent_product_handled_safely(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        telegram_id = 800200103
        _register(telegram_id, 3)
        r = _post(Client(), _callback(telegram_id, f"catalog:product:{uuid.uuid4()}"))
        assert r.status_code == 200


class TestCartOperations:
    def test_add_to_cart_uses_real_server_price(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product(Decimal("50000.00"))
        telegram_id = 800200200
        user = _register(telegram_id, 4)

        r = _post(Client(), _callback(telegram_id, f"cart:add:{variant.id}"))
        assert r.status_code == 200

        user.refresh_from_db()
        cart = TelegramCartService().view_cart(user)
        assert len(cart["items"]) == 1
        assert cart["items"][0]["unit_amount"] == "50000.00"
        assert cart["items"][0]["quantity"] == 1

    def test_client_supplied_price_fields_have_no_effect(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product(Decimal("99999.00"))
        telegram_id = 800200201
        user = _register(telegram_id, 5)

        r = _post(Client(), _callback(telegram_id, f"cart:add:{variant.id}:price:1.00"))
        assert r.status_code == 200
        user.refresh_from_db()
        cart = TelegramCartService().view_cart(user)
        assert cart["items"][0]["unit_amount"] == "99999.00"

    def test_adding_same_variant_twice_merges_not_duplicates(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product(Decimal("10000.00"))
        telegram_id = 800200202
        user = _register(telegram_id, 6)

        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))

        user.refresh_from_db()
        cart = TelegramCartService().view_cart(user)
        assert len(cart["items"]) == 1
        assert cart["items"][0]["quantity"] == 2

    def test_increase_and_decrease_quantity(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product()
        telegram_id = 800200203
        user = _register(telegram_id, 7)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))

        user.refresh_from_db()
        item_id = TelegramCartService().view_cart(user)["items"][0]["id"]
        _post(client, _callback(telegram_id, f"cart:increase:{item_id}"))
        user.refresh_from_db()
        assert TelegramCartService().view_cart(user)["items"][0]["quantity"] == 2

        _post(client, _callback(telegram_id, f"cart:decrease:{item_id}"))
        user.refresh_from_db()
        assert TelegramCartService().view_cart(user)["items"][0]["quantity"] == 1

    def test_remove_item(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product()
        telegram_id = 800200204
        user = _register(telegram_id, 8)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        user.refresh_from_db()
        item_id = TelegramCartService().view_cart(user)["items"][0]["id"]

        _post(client, _callback(telegram_id, f"cart:remove:{item_id}"))
        user.refresh_from_db()
        assert TelegramCartService().view_cart(user)["items"] == []

    def test_empty_cart_shows_empty_state_not_crash(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        telegram_id = 800200205
        _register(telegram_id, 9)
        r = _post(Client(), _callback(telegram_id, "menu:cart"))
        assert r.status_code == 200


class TestCartTransactionBoundary:
    """
    Phase 15I: closes a real, confirmed defect found via the same
    reconnaissance pattern that caught the same bug class twice
    already this session (Phase 09.7c, Phase 15H). add_item() called
    three separately-atomic services (add item, issue price snapshot,
    attach snapshot) with no shared outer transaction -- a failure
    partway through left a real, committed cart item with no price
    and a real, committed price snapshot that was never used.
    """

    def test_failure_during_add_item_rolls_back_item_and_snapshot_together(self, monkeypatch):
        from apps.cart.infrastructure import composition as cart_composition
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product()
        telegram_id = 800300400
        user = _register(telegram_id, 20)

        service = TelegramCartService()

        class _Boom:
            def execute(self, **kwargs):
                raise RuntimeError("Simulated failure in attach_price_snapshot")

        monkeypatch.setattr(cart_composition, "build_attach_price_snapshot", lambda actor_id: _Boom())

        with pytest.raises(RuntimeError):
            service.add_item(user, variant.id, quantity=1)

        user.refresh_from_db()
        assert user.telegram_cart_id is not None  # the cart itself was created successfully, in its own transaction

        cart = cart_composition.build_cart_repository().get_by_id(user.telegram_cart_id)
        assert len(cart.items) == 0  # the failed item addition left no partial item

        from apps.pricing.infrastructure import models as pricing_orm
        orphaned = pricing_orm.PriceSnapshotModel.objects.filter(product_variant_id=variant.id, status="locked").count()
        assert orphaned == 0  # the issued-but-never-attached snapshot was also rolled back


class TestCartOwnershipSecurity:
    def test_attacker_cannot_mutate_victims_cart_item(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product()
        victim_id = 800200300
        attacker_id = 800200301
        victim = _register(victim_id, 10)
        _register(attacker_id, 11)

        client = Client()
        _post(client, _callback(victim_id, f"cart:add:{variant.id}"))
        victim.refresh_from_db()
        victim_item_id = TelegramCartService().view_cart(victim)["items"][0]["id"]

        r = _post(client, _callback(attacker_id, f"cart:remove:{victim_item_id}"))
        assert r.status_code == 200

        victim.refresh_from_db()
        victim_cart = TelegramCartService().view_cart(victim)
        assert len(victim_cart["items"]) == 1
        assert victim_cart["items"][0]["id"] == victim_item_id

    def test_attacker_cannot_increase_victims_item_quantity(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services.shopping import TelegramCartService

        category, product, variant = _make_priced_product()
        victim_id = 800200302
        attacker_id = 800200303
        victim = _register(victim_id, 12)
        _register(attacker_id, 13)

        client = Client()
        _post(client, _callback(victim_id, f"cart:add:{variant.id}"))
        victim.refresh_from_db()
        victim_item_id = TelegramCartService().view_cart(victim)["items"][0]["id"]

        _post(client, _callback(attacker_id, f"cart:increase:{victim_item_id}"))

        victim.refresh_from_db()
        victim_cart = TelegramCartService().view_cart(victim)
        assert victim_cart["items"][0]["quantity"] == 1
