"""Grouping products that differ only by size and flavour into one family (product_grouping.py)."""
from __future__ import annotations

import uuid

import pytest

from apps.products.infrastructure import models as orm
from apps.products.infrastructure.product_grouping import base_name, group_suggestions, merge_products, parse_size, preview_group
from apps.products.infrastructure.selectors import ProductDetailSelector, merged_product_target

pytestmark = pytest.mark.django_db


def _flavour(en, uz, hex_="#7b3f00"):
    f = orm.Flavour.objects.create(slug=f"{en.lower().replace(' ', '-')}-{uuid.uuid4().hex[:4]}", color_hex=hex_)
    orm.FlavourTranslation.objects.create(flavour=f, locale_code="en", name=en)
    orm.FlavourTranslation.objects.create(flavour=f, locale_code="uz", name=uz)
    return f


def _product(brand, name, sku, weight=None, unit="g", flavour=None):
    p = orm.Product.objects.create(brand=brand, status="published")
    slug = f"{name.lower().replace(' ', '-').replace('.', '-')}-{uuid.uuid4().hex[:4]}"
    for loc in ("uz", "ru", "en"):
        orm.ProductTranslation.objects.create(product=p, locale_code=loc, name=name, slug=slug)
    orm.ProductVariant.objects.create(product=p, sku=sku, weight_value=weight, weight_unit=unit, is_default=True)
    if flavour:
        orm.ProductFlavour.objects.create(product=p, flavour=flavour)
    return p


@pytest.fixture
def olimp():
    brand = orm.Brand.objects.create(is_active=True)
    orm.BrandTranslation.objects.create(brand=brand, locale_code="uz", name="Olimp", slug=f"olimp-{uuid.uuid4().hex[:4]}")
    choc, coco, straw, caramel = _flavour("Chocolate", "Shokolad"), _flavour("Coconut Cream", "Kokos kremi"), _flavour("Strawberry", "Qulupnay"), _flavour("Salted Caramel", "Sho'r karamel")
    products = [
        _product(brand, "Olimp Complex Whey 2.27 kg Chocolate", "OL-CW-2270-CH", 2.27, "kg", choc),
        _product(brand, "Olimp Complex Whey 1.8 kg Coconut Cream", "OL-CW-1800-CC"),          # no tag, no weight: from the name
        _product(brand, "Olimp Complex Whey 700 g strawberry", "OL-CW-700-ST", 700, "g"),
        _product(brand, "Olimp Complex Whey 350 g Salted Caramel", "OL-CW-350-SC", 350, "g", caramel),
    ]
    other = _product(brand, "Olimp Creatine Monohydrate 250 g", "OL-CR-250", 250, "g")
    return {"brand": brand, "products": products, "other": other, "flavours": (choc, coco, straw, caramel)}


def test_name_parsing():
    assert parse_size("Olimp Complex Whey 2.27 kg Chocolate") == (2.27, "kg")
    assert parse_size("ON Gold Standard 5 lb") == (2.27, "kg")
    assert parse_size("Omega-3 120 caps") == (120.0, "capsule")
    assert base_name("Olimp Complex Whey 2.27 kg Chocolate", [("chocolate", 1)]) == "Olimp Complex Whey"
    assert base_name("Olimp Complex Whey (700 g) - Strawberry", [("strawberry", 1)]) == "Olimp Complex Whey"


def test_suggests_the_family_but_not_other_products(olimp):
    groups = group_suggestions()
    assert len(groups) == 1
    g = groups[0]
    assert g["name"] == "Olimp Complex Whey" and len(g["product_ids"]) == 4
    assert str(olimp["other"].id) not in g["product_ids"]


def test_preview_detects_size_and_flavour(olimp):
    preview = preview_group([p.id for p in olimp["products"]])
    by_sku = {v.sku: v for v in preview.variants}
    assert by_sku["OL-CW-1800-CC"].size_value == 1.8 and by_sku["OL-CW-1800-CC"].size_unit == "kg"
    assert by_sku["OL-CW-1800-CC"].flavour_name == "Kokos kremi"  # found in the name
    assert by_sku["OL-CW-700-ST"].flavour_name == "Qulupnay"  # lower-case "strawberry" in the name
    assert preview.missing_flavour == 0 and not preview.duplicates
    assert preview.names["uz"] == "Olimp Complex Whey"


def test_merge_makes_one_family_and_redirects_old_links(olimp):
    target = olimp["products"][0]
    old = olimp["products"][2]
    old_slug = old.translations.get(locale_code="uz").slug
    result = merge_products(target.id, [p.id for p in olimp["products"]])
    assert result["merged"] == 3
    variants = orm.ProductVariant.objects.filter(product=target)
    assert variants.count() == 4 and variants.filter(is_default=True).count() == 1
    assert set(variants.values_list("flavour__translations__name", flat=True)) >= {"Chocolate", "Coconut Cream", "Strawberry", "Salted Caramel"}
    assert set(orm.ProductFlavour.objects.filter(product=target).values_list("flavour_id", flat=True)) == {f.id for f in olimp["flavours"]}
    assert target.translations.get(locale_code="uz").name == "Olimp Complex Whey"
    assert not orm.Product.objects.filter(id=old.id).exists()  # archived + soft-deleted
    moved = merged_product_target(old_slug)
    assert moved["slug"] == target.translations.get(locale_code="uz").slug
    assert moved["variant_id"] == str(orm.ProductVariant.objects.get(sku="OL-CW-700-ST").id)
    card = ProductDetailSelector().get_by_slug(moved["slug"], locale="en")
    assert {o["name"] for o in card["flavours"]} == {"Chocolate", "Coconut Cream", "Strawberry", "Salted Caramel"}
    assert all(o["product_slug"] == card["slug"] for o in card["flavours"])
    assert {v["flavour"]["name"] for v in card["variants"]} == {"Chocolate", "Coconut Cream", "Strawberry", "Salted Caramel"}
    assert group_suggestions() == []


def test_editor_corrections_win(olimp):
    target = olimp["products"][0]
    straw = olimp["flavours"][2]
    v = orm.ProductVariant.objects.get(sku="OL-CW-1800-CC")
    merge_products(target.id, [p.id for p in olimp["products"]], variant_flavours={str(v.id): str(straw.id)}, variant_sizes={str(v.id): (2.0, "kg")},
                   names={"uz": "Olimp Complex Whey Protein"})
    v.refresh_from_db()
    assert v.flavour_id == straw.id and v.weight_value == 2.0
    assert target.translations.get(locale_code="uz").name == "Olimp Complex Whey Protein"


def test_dashboard_grouping_pages(olimp):
    from django.contrib.auth import get_user_model
    from django.test import Client

    user = get_user_model().objects.create(username="grouping_admin", is_staff=True, is_superuser=True)
    c = Client()
    c.force_login(user)
    html = c.get("/django-admin/products/grouping/", HTTP_ACCEPT_LANGUAGE="uz").content.decode()
    assert "Olimp Complex Whey" in html and "Ko&#x27;rib chiqish" in html or "Ko'rib chiqish" in html
    ids = ",".join(str(p.id) for p in olimp["products"])
    page = c.get(f"/django-admin/products/grouping/?ids={ids}", HTTP_ACCEPT_LANGUAGE="uz").content.decode()
    assert "OL-CW-1800-CC" in page and 'name="flavour_' in page
    target = olimp["products"][0]
    resp = c.post("/django-admin/products/grouping/", {"ids": ids, "target": str(target.id), "name_uz": "Olimp Complex Whey"})
    assert resp.status_code == 302 and str(target.id) in resp["Location"]
    assert orm.ProductVariant.objects.filter(product=target).count() == 4
    # the changelist action opens the review screen
    resp = c.post("/django-admin/products/product/", {"action": "group_selected", "_selected_action": [str(olimp["other"].id), str(target.id)]})
    assert resp.status_code == 302 and "/products/grouping/?ids=" in resp["Location"]


def _priced_family(olimp):
    """The Olimp family grouped, with a price per variant: 2.27 kg 890 000 ... 350 g 190 000."""
    from decimal import Decimal

    from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

    target = olimp["products"][0]
    merge_products(target.id, [p.id for p in olimp["products"]])
    pl = PriceListModel.objects.filter(status="active").first() or PriceListModel.objects.create(name="Asosiy", currency="UZS", status="active")
    for sku, price in {"OL-CW-2270-CH": 890000, "OL-CW-1800-CC": 760000, "OL-CW-700-ST": 340000, "OL-CW-350-SC": 190000}.items():
        PriceListEntryModel.objects.create(price_list=pl, product_variant_id=orm.ProductVariant.objects.get(sku=sku).id, base_price_amount=Decimal(price))
    return target


def _ids(result):
    return [str(i) for i in result["ordered_ids"]]


def test_catalog_filters_judge_one_variant_at_a_time(olimp):
    from apps.products.infrastructure.catalog_browse import browse

    target = _priced_family(olimp)
    choc, coco, straw, caramel = olimp["flavours"]
    run = lambda filters: browse(None, filters, "-created_at", 1, 50, "uz")  # noqa: E731

    # price: any variant in range counts (the default variant is 890 000)
    assert str(target.id) in _ids(run({"price": {"lte": "200000"}}))
    assert str(target.id) not in _ids(run({"price": {"gte": "900000"}}))
    # size + flavour must be the same variant: 350 g exists only as Salted Caramel
    assert str(target.id) not in _ids(run({"sizes": ["350g"], "flavour_ids": [str(choc.id)]}))
    assert str(target.id) in _ids(run({"sizes": ["350g"], "flavour_ids": [str(caramel.id)]}))
    # flavour + price together: Chocolate is only 890 000
    assert str(target.id) not in _ids(run({"flavour_ids": [str(choc.id)], "price": {"lte": "500000"}}))
    # facets follow the chosen flavour: sizes and price range of Strawberry only
    facets = run({"flavour_ids": [str(straw.id)]})["facets"]
    assert [s["id"] for s in facets["size"]] == ["700g"]
    facets = run({})["facets"]
    assert facets["price_range"]["min"] == "190000.00" and facets["price_range"]["max"] == "890000.00"


def test_price_sort_uses_the_from_price(olimp):
    from decimal import Decimal

    from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel
    from apps.products.infrastructure.catalog_browse import browse

    target = _priced_family(olimp)
    other = olimp["other"]
    pl = PriceListModel.objects.filter(status="active").first()
    PriceListEntryModel.objects.create(price_list=pl, product_variant_id=other.variants.first().id, base_price_amount=Decimal(250000))
    order = _ids(browse(None, {}, "price", 1, 50, "uz"))
    assert order.index(str(target.id)) < order.index(str(other.id))  # 190 000 "from" < 250 000


def test_grouping_confirmation_is_translated(olimp, settings):
    from django.contrib.auth import get_user_model
    from django.test import Client

    settings.ADMIN_PHRASES_ENABLED = True
    user = get_user_model().objects.create(username="grouping_admin_en", is_staff=True, is_superuser=True)
    c = Client()
    c.force_login(user)
    c.cookies["django_language"] = "en"
    ids = ",".join(str(p.id) for p in olimp["products"])
    html = c.get(f"/django-admin/products/grouping/?ids={ids}", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert 'data-confirm="Merge the products into one?' in html
    assert "birlashtirilsinmi" not in html
