"""
import_catalog_additions: new barcodes become products written like dashboard ones (translations, variant, price,
photo), an extra barcode lands on the existing variant, a product without a bundled photo stays hidden, and a re-run
changes nothing. Runs against a small dataset injected under the catalog_additions package.
"""
from __future__ import annotations

import io
import sys
import types
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.catalog_additions._text import L, product
from apps.products.management.commands import import_catalog_additions as command

pytestmark = pytest.mark.django_db

DATASET = "test_dataset_tmp"


def _named(model, translation_model, fk, name, **fields):
    obj = model.objects.create(**fields)
    for loc in ("uz", "ru", "en"):
        extra = {"slug": f"{name.lower().replace(' ', '-')}-{loc}"} if translation_model is not p_models.FlavourTranslation else {}
        translation_model.objects.create(**{fk: obj}, locale_code=loc, name=name, **extra)
    return obj


@pytest.fixture
def catalogue():
    parent = _named(p_models.Category, p_models.CategoryTranslation, "category", "Proteins")
    _named(p_models.Category, p_models.CategoryTranslation, "category", "Whey Protein", parent=parent)
    brand = _named(p_models.Brand, p_models.BrandTranslation, "brand", "RECKFUL")
    p_models.Package.objects.create(slug="jar")
    ref = p_models.Product.objects.create(brand=brand, status="published", warnings_text_uz="Ogohlantirish", warnings_text_ru="Предупреждение", warnings_text_en="Warning")
    p_models.ProductVariant.objects.create(product=ref, sku="REF-1", barcode="1111111111111", is_default=True)
    return ref


@pytest.fixture
def dataset(tmp_path, monkeypatch, settings):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    photos = tmp_path / "photos" / DATASET
    photos.mkdir(parents=True)
    Image.new("RGB", (400, 400), "white").save(photos / "2222222222222.jpg")
    monkeypatch.setattr(command, "DATA_DIR", tmp_path / "photos")

    def item(barcode, flavour, brand="RECKFUL"):
        return product(
            barcode=barcode, sku="RK-TEST", price=490000, brand=brand, country="RU", category=("Proteins", "Whey Protein"), package="jar",
            size=(900, "g"), flavour=flavour, names=L(f"Test {barcode} uz", f"Test {barcode} ru", f"Test {barcode} en"),
            intro=L("Kirish.", "Введение.", "Intro."), serving=L("30 g", "30 г", "30 g"), facts=[("protein", "23.5 g")], servings=30,
            how=L("Iching.", "Пейте.", "Drink."), warnings_from="1111111111111", goals=["muscle"],
        )

    module = types.ModuleType(f"apps.products.infrastructure.catalog_additions.{DATASET}")
    module.EXTRA_BARCODES = [("3333333333333", "1111111111111")]
    module.NEW_BRANDS = {"Bombbar": {"country": "", "uz": "B", "ru": "B", "en": "B"}}
    module.NEW_FLAVOURS = {"Yuzu": {"uz": "Yuzu", "ru": "Юдзу", "color": "#E8D64A"}}
    module.ITEMS = [item("2222222222222", "Yuzu"), item("4444444444444", None, brand="Bombbar")]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def test_creates_products_like_the_dashboard_and_a_rerun_is_a_no_op(catalogue, dataset):
    from apps.pricing.infrastructure.models import PriceListEntryModel

    call_command("import_catalog_additions", DATASET, stdout=io.StringIO())

    with_photo = p_models.ProductVariant.objects.get(barcode="2222222222222")
    product_row = with_photo.product
    assert product_row.status == "published"
    assert {t.locale_code: t.name for t in product_row.translations.all()} == {"uz": "Test 2222222222222 uz", "ru": "Test 2222222222222 ru", "en": "Test 2222222222222 en"}
    assert product_row.translations.get(locale_code="ru").description.startswith("Введение.")
    assert "Белки — 23,5 г" in product_row.supplement_facts_text_ru
    assert product_row.warnings_text_ru == "Предупреждение"
    assert product_row.goals == ["muscle"]
    assert with_photo.flavour.translations.get(locale_code="ru").name == "Юдзу"
    assert list(product_row.flavours.all()) == [with_photo.flavour]
    assert PriceListEntryModel.objects.get(product_variant_id=with_photo.id).base_price_amount == Decimal("490000")
    assert p_models.ProductMedia.objects.filter(product=product_row, media_role="primary").count() == 1

    hidden = p_models.ProductVariant.objects.get(barcode="4444444444444")
    assert hidden.product.status == "unpublished"
    assert hidden.sku == "RK-TEST-2"  # SKUs stay unique
    assert hidden.product.brand.translations.get(locale_code="en").name == "Bombbar"
    assert p_models.ProductVariantBarcode.objects.get(barcode="3333333333333").variant.barcode == "1111111111111"

    counts = (p_models.Product.objects.count(), p_models.ProductVariantBarcode.objects.count(), p_models.ProductMedia.objects.count())
    out = io.StringIO()
    call_command("import_catalog_additions", DATASET, stdout=out)
    assert "0 products created" in out.getvalue() and "3 already present" in out.getvalue()
    assert (p_models.Product.objects.count(), p_models.ProductVariantBarcode.objects.count(), p_models.ProductMedia.objects.count()) == counts


def test_dry_run_writes_nothing_and_an_unknown_category_stops_the_import(catalogue, dataset):
    before = p_models.Product.objects.count()
    call_command("import_catalog_additions", DATASET, "--dry-run", stdout=io.StringIO())
    assert p_models.Product.objects.count() == before
    assert not p_models.ProductVariantBarcode.objects.exists()

    dataset.ITEMS[0]["category"] = ("Proteins", "Nope")
    with pytest.raises(CommandError, match="no category Proteins > Nope"):
        call_command("import_catalog_additions", DATASET, stdout=io.StringIO())
    assert p_models.Product.objects.count() == before


def test_the_bundled_quyliq_dataset_is_well_formed():
    from apps.products.infrastructure.catalog_additions import quyliq_2026_10 as data

    barcodes = [i["barcode"] for i in data.ITEMS]
    assert len(barcodes) == len(set(barcodes)) == 64
    assert len({i["sku"] for i in data.ITEMS}) == 64
    assert not set(barcodes) & {code for code, _existing in data.EXTRA_BARCODES}
    for item in data.ITEMS:
        assert all(item["names"][loc] and item["descriptions"][loc] for loc in ("uz", "ru", "en")), item["barcode"]
        assert item["price"] > 0
