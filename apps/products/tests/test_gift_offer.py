"""Sovg'a aksiyasi: the free NutriZone shaker on 1 mln+ orders with a protein / gainer (products/infrastructure/gift_offer.py)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.products.tests.stock_helpers import put_stock
from apps.products.tests.test_pdp_extras import _product

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _cat(slug, parent=None):
    from apps.products.infrastructure import models as orm

    c = orm.Category.objects.create(parent=parent)
    orm.CategoryTranslation.objects.create(category=c, locale_code="uz", name=slug, slug=slug if parent else f"{slug}-{uuid.uuid4().hex[:4]}")
    return c


@pytest.fixture()
def shop():
    """Sport → Proteinlar / Geynerlar / Kreatin; Aksessuarlar → Shakerlar; the gift = a shaker with 5 in stock."""
    from apps.products.infrastructure import models as orm

    sport, acc = _cat("sport"), _cat("acc")
    cats = {"protein": _cat("proteinlar", sport), "gainer": _cat("geynerlar", sport), "creatine": _cat("kreatin", sport), "shakers": _cat("shakerlar", acc)}
    shaker, sv = _product("NutriZone sheykeri", 30_000, category=cats["shakers"], stock=5)
    whey, wv = _product("Whey", 1_100_000, category=_cat("izolyat", cats["protein"]))  # a leaf under Proteinlar still counts
    mass, mv = _product("Mass", 600_000, category=cats["gainer"])
    crea, cv = _product("Creatine", 1_200_000, category=cats["creatine"])
    orm.GiftOfferSettings.objects.update_or_create(pk=1, defaults={"enabled": True, "gift_variant_id": sv.id, "min_goods_amount": Decimal("1000000")})
    return {"shaker": shaker, "sv": sv, "whey": whey, "wv": wv.id, "mass": mass, "mv": mv.id, "crea": crea, "cv": cv.id, **cats}


def _order():
    from apps.ordering.infrastructure.models import OrderModel

    return OrderModel.objects.create(order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}", status="confirmed", currency="UZS", placed_at=timezone.now(),
                                     shipping_recipient_name="A", shipping_line1="x", shipping_city="Toshkent", shipping_country_code="UZ",
                                     billing_recipient_name="A", billing_line1="x", billing_city="Toshkent", billing_country_code="UZ")


def test_protein_order_over_threshold_gets_the_shaker_free(shop):
    from apps.products.infrastructure import gift_offer

    o = _order()
    assert gift_offer.attach(o.id, [shop["wv"]], Decimal("1100000"))
    line = o.lines.get(is_gift=True)
    assert (line.product_variant_id, line.quantity, line.unit_price_amount, line.status) == (shop["sv"].id, 1, Decimal("0"), "active")
    assert not gift_offer.attach(o.id, [shop["wv"]], Decimal("1100000"))  # once per order
    assert gift_offer.gift_line_ids([o.id]) == {line.id}


def test_no_gift_below_threshold_without_protein_or_out_of_stock(shop):
    from apps.products.infrastructure import gift_offer
    from apps.stores.infrastructure.models import StoreProductStock

    assert not gift_offer.attach(_order().id, [shop["mv"]], Decimal("999999"))          # gainer, but under 1 mln
    assert gift_offer.attach(_order().id, [shop["mv"], shop["cv"]], Decimal("1800000"))  # gainer + creatine, over 1 mln
    assert not gift_offer.attach(_order().id, [shop["cv"]], Decimal("1200000"))          # creatine only: not qualifying
    StoreProductStock.objects.filter(product_variant_id=shop["sv"].id).update(quantity=0)
    assert not gift_offer.attach(_order().id, [shop["wv"]], Decimal("1100000"))          # no shaker left: nothing promised


def test_status_tells_what_is_missing(shop):
    from apps.products.infrastructure import gift_offer

    st = gift_offer.status([shop["mv"]], Decimal("600000"))
    assert st["items_qualify"] and not st["earned"] and st["missing"] == "400000" and st["threshold"] == "1000000"
    assert st["gift"]["name"] == "NutriZone sheykeri" and st["gift"]["value"] == "30000"
    assert gift_offer.status([shop["wv"]], Decimal("1100000"))["earned"]
    assert not gift_offer.status([shop["cv"]], Decimal("1200000"))["items_qualify"]


def test_disabled_offer_does_nothing(shop):
    from apps.products.infrastructure import gift_offer
    from apps.products.infrastructure import models as orm

    orm.GiftOfferSettings.objects.filter(pk=1).update(enabled=False)
    gift_offer.invalidate()
    assert gift_offer.status([shop["wv"]], Decimal("1100000")) is None
    assert not gift_offer.attach(_order().id, [shop["wv"]], Decimal("1100000"))
    assert gift_offer.pdp_card(shop["whey"].id) is None


def test_pdp_recommends_the_shaker_on_protein_and_gainer_only(shop):
    from apps.products.infrastructure.pdp_extras import extras

    card = extras(shop["whey"].id, locale="uz")["gift"]
    assert card["variant_id"] == str(shop["sv"].id) and card["threshold"] == "1000000" and card["value"] == "30000"
    assert extras(shop["mass"].id, locale="uz")["gift"]["product_id"] == str(shop["shaker"].id)
    assert extras(shop["crea"].id, locale="uz")["gift"] is None
    assert extras(shop["shaker"].id, locale="uz")["gift"] is None


def test_pickup_needs_the_shaker_at_that_branch(shop):
    from apps.products.infrastructure import gift_offer
    from apps.products.tests.stock_helpers import location

    branch = location("Chilonzor")
    assert not gift_offer.attach(_order().id, [shop["wv"]], Decimal("1100000"), store_id=branch.id)
    put_stock(shop["sv"].id, 2, store=branch)
    assert gift_offer.attach(_order().id, [shop["wv"]], Decimal("1100000"), store_id=branch.id)


def test_order_api_and_channel_post_label_the_gift(shop):
    from apps.ordering.infrastructure import composition as ordering_composition
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.ordering.interfaces.api.v1.views import _order_payload
    from apps.products.infrastructure import gift_offer
    from apps.telegram_bot.infrastructure import orders_post

    o = _order()
    OrderLineItemModel.objects.create(order=o, product_variant_id=shop["wv"], quantity=1, unit_price_amount=Decimal("1100000"))
    gift_offer.attach(o.id, [shop["wv"]], Decimal("1100000"))
    order = ordering_composition.build_order_repository().get_by_id(o.id)
    lines = _order_payload(order)["lines"]
    assert sorted(ln["is_gift"] for ln in lines) == [False, True]
    assert order.compute_total().grand_total.amount == Decimal("1100000")  # the gift adds nothing to pay
    text = orders_post.build(order)["text"]
    assert "SOVG‘A" in text and "NutriZone sheykeri" in text


@pytest.mark.integration
def test_guest_checkout_adds_the_gift_line_and_preview_shows_it(shop):
    from apps.cart.tests.interfaces.test_guest_checkout import _guest_cart, _order
    from apps.ordering.infrastructure.models import OrderModel

    c, cart = _guest_cart(shop["wv"])
    r = c.get(f"/api/v1/cart/{cart['code']}/guest-preview", HTTP_X_CART_TOKEN=cart["token"])
    assert r.status_code == 200, r.json()
    gift = r.json()["data"]["gift"]
    assert gift["earned"] and gift["gift"]["variant_id"] == str(shop["sv"].id)
    r = _order(c, cart, "94-205-20-41")
    assert r.status_code == 201, r.json()
    order = OrderModel.objects.get(order_number=r.json()["data"]["order_number"])
    gifts = list(order.lines.filter(is_gift=True))
    assert len(gifts) == 1 and gifts[0].unit_price_amount == 0 and gifts[0].product_variant_id == shop["sv"].id


def test_bundle_never_pairs_the_gift_shaker(shop, monkeypatch):
    """The page already has the gift card -- "Birga arzonroq" must not offer the same shaker a second time."""
    from apps.products.infrastructure import bundles

    monkeypatch.setattr("apps.products.infrastructure.selectors.RecommendationSelector.for_product", lambda self, pid, limit=12, locale=None: [])
    offer = bundles.offer_for(shop["whey"].id)
    assert offer is None or offer["companion_product_id"] != str(shop["shaker"].id)
