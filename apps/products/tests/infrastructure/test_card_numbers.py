"""Numbers a card states only in words, and the facts the product page shows from them."""
import uuid
from decimal import Decimal

import pytest

from apps.products.infrastructure.card_numbers import card_facts, text_numbers

FACTS = "1 porsiya (30 g) uchun:\n\nOqsil manbalari — WPC + kazein\n\nPorsiya — 30 g\n\nQadoqdagi porsiyalar soni — 23"


def test_text_numbers_reads_uzbek_russian_english():
    assert text_numbers(FACTS, "~80% oqsil") == {"serving_g": 30.0, "servings": 23.0, "protein": 24.0}
    assert text_numbers("Serving size 31 g, 24 g protein, 74 servings") == {"serving_g": 31.0, "servings": 74.0, "protein": 24.0}
    assert text_numbers("Kuniga 1–3 porsiya") == {}


def test_card_facts_prices_protein_and_lists_what_it_suits():
    f = card_facts(texts=[FACTS, "~80% oqsil"], nutrition={}, price="300000.00", category_path=["Sports Nutrition", "Proteins", "Whey Isolate"], size="700 g")
    assert f["per_serving"] == 13043 and f["per_25g_protein"] == 13587 and f["suits"][:2] == ["low_lactose", "lean"] and f["size"] == "700 g"
    creatine = card_facts(texts=["Qadoqdagi porsiyalar soni — 60"], nutrition={}, price=150000, category_path=["Sports Nutrition", "Creatine"])
    assert creatine["per_25g_protein"] is None and creatine["per_serving"] == 2500 and creatine["suits"] == ["strength"]


@pytest.mark.django_db
def test_product_page_carries_card_facts():
    from apps.pricing.infrastructure import models as pricing
    from apps.products.infrastructure import models as p
    from apps.products.infrastructure.selectors import ProductDetailSelector

    def cat(name, parent=None):
        c = p.Category.objects.create(parent=parent)
        p.CategoryTranslation.objects.create(category=c, locale_code="en", name=name, slug=f"c-{uuid.uuid4().hex[:8]}")
        return c

    iso = cat("Whey Isolate", cat("Proteins"))
    product = p.Product.objects.create(id=uuid.uuid4(), status="published", category=iso, supplement_facts_text_uz=FACTS + "\n\nOqsil — 27 g")
    p.ProductTranslation.objects.create(product=product, locale_code="uz", name="Iso", slug="iso-x")
    v = p.ProductVariant.objects.create(product=product, sku="ISO-1", status="active", is_default=True, weight_value=700, weight_unit="g")
    pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "D", "currency": "UZS", "status": "active"})
    pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=v.id, base_price_amount=Decimal(300000))
    f = ProductDetailSelector().get_by_slug("iso-x", "uz")["card_facts"]
    assert f["servings"] == 23 and f["protein"] == 27 and f["per_25g_protein"] == 12077 and f["size"] == "700 g" and "low_lactose" in f["suits"]
