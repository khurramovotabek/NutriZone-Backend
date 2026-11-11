"""The consultant layer (advisor/expert.py): strict kinds, budget picks with numbers, "which is better", milk/lactose."""
import uuid
from decimal import Decimal

import pytest

from apps.assistant.infrastructure.advisor import brain, expert, nlu
from apps.assistant.infrastructure.advisor.engine import answer


@pytest.fixture(autouse=True)
def _fresh_index():
    brain._CACHE.clear()
    brain._CACHE["at"] = 0.0
    yield
    brain._CACHE.clear()
    brain._CACHE["at"] = 0.0


def _cat(en, parent=None):
    from apps.products.infrastructure import models as p

    c = p.Category.objects.create(parent=parent)
    for loc, name in (("en", en), ("uz", en)):
        p.CategoryTranslation.objects.create(category=c, locale_code=loc, name=name, slug=f"c-{uuid.uuid4().hex[:8]}")
    return c


def _brand(name):
    from apps.products.infrastructure import models as p

    b = p.Brand.objects.create()
    p.BrandTranslation.objects.create(brand=b, locale_code="uz", name=name, slug=f"b-{uuid.uuid4().hex[:6]}")
    return b


def _product(name, price, category, brand=None, protein=None, servings=None, kg=2.27, desc=""):
    from apps.pricing.infrastructure import models as pricing
    from apps.products.infrastructure import models as p
    from apps.stores.infrastructure import models as st

    extra = {}
    if protein:
        extra = {"supplement_facts_text_uz": f"1 porsiya (30 g) uchun:\n\nOqsil: {protein} g", "nutrition_serving_size_grams": 30,
                 "nutrition_servings_per_container": servings}
    product = p.Product.objects.create(id=uuid.uuid4(), status="published", category=category, brand=brand, **extra)
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}", description=desc)
    v = p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True,
                                        weight_value=kg, weight_unit="kg")
    pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "D", "currency": "UZS", "status": "active"})
    pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=v.id, base_price_amount=Decimal(price))
    store = st.Store.objects.create(kind="warehouse", name=f"W{uuid.uuid4().hex[:4]}", slug=f"w-{uuid.uuid4().hex[:6]}")
    st.StoreProductStock.objects.create(store=store, product_variant=v, quantity=5)
    return product


@pytest.fixture
def shop(db):
    sport = _cat("Sports Nutrition")
    proteins = _cat("Proteins", sport)
    whey, iso, vegan = _cat("Whey Protein", proteins), _cat("Whey Isolate", proteins), _cat("Vegan Protein", proteins)
    creatine = _cat("Creatine", sport)
    on, nobody = _brand("Optimum Nutrition"), _brand("Zorvex")
    return {
        "gold": _product("Gold Standard 100% Whey", 450_000, whey, on, protein=24, servings=74),
        "cheap": _product("Zorvex Whey", 380_000, whey, nobody, protein=25, servings=30, kg=0.9),
        "pricey": _product("Zorvex Whey Big", 900_000, whey, nobody, protein=24, servings=74),
        "iso": _product("Zorvex Isolate", 480_000, iso, nobody, protein=27, servings=60),
        "plant": _product("Zorvex Plant Protein", 350_000, vegan, nobody, protein=21, servings=30, kg=0.9),
        # a protein whose text talks about creatine must never show up for "kreatin"
        "creatine": _product("Zorvex Creatine Monohydrate", 150_000, creatine, nobody, kg=0.3),
        "whey_with_creatine": _product("Zorvex Whey + Creatine", 420_000, whey, nobody, protein=22, servings=40, desc="kreatin qo'shilgan protein creatine"),
    }


def test_budget_lists_only_the_kind_under_budget_with_numbers_and_a_verdict(shop):
    reply, ids, _chips, meta = answer({}, "menga 500 minggacha protein kerak", "uz")
    assert str(shop["pricey"].id) not in ids and str(shop["creatine"].id) not in ids
    assert str(shop["gold"].id) in ids and "Mening tanlovim" in reply and "25 g oqsil" in reply
    assert ids[0] == str(shop["gold"].id)  # best value + flagship brand
    assert meta["last"] == "expert_pick" and meta["last_shown"] == ids and meta["last_kind"] == "protein"


def test_creatine_never_lists_protein(shop):
    _reply, ids, *_ = answer({}, "eng yaxshi kreatin qaysi", "uz")
    assert ids == [str(shop["creatine"].id)]
    assert {x["id"] for x in expert.kind_search("creatine", "uz", limit=8)} == {str(shop["creatine"].id)}
    reply, ids, _c, meta = answer({}, "kreatin kerak", "uz")
    assert ids == [str(shop["creatine"].id)] and meta["last"] == "expert_pick" and "monogidrat" in reply


def test_subtype_narrows_to_its_section(shop):
    reply, ids, *_ = answer({}, "eng arzon izolyat", "uz")
    assert ids == [str(shop["iso"].id)] and "Izolyat" in reply


def test_which_one_is_better_compares_what_was_shown(shop):
    _r, ids, _c, meta = answer({}, "500 minggacha protein", "uz")
    reply, ids2, _c, meta = answer(meta, "qaysi biri yaxshi?", "uz")
    assert meta["last"] == "compare_shown" and set(ids2) == set(ids) and "Mening tanlovim: Gold Standard" in reply
    assert "Eng tejamkori" not in reply or "Gold Standard" in reply.split("Eng tejamkori")[1][:60]


def test_value_maths(shop):
    rows = {r.name: r for r in expert.rows_for([str(shop["gold"].id), str(shop["cheap"].id)], "uz")}
    assert round(rows["Gold Standard 100% Whey"].per_25g) == 6334  # 450 000 / 74 / 24 * 25
    assert round(rows["Zorvex Whey"].per_25g) == 12667


def test_lactose_and_milk_allergy(shop):
    reply, ids, _c, meta = answer({}, "sut mahsulotlari yoqmaydi, qornim shishadi. qaysi proteinni qayerdan olsam bo'ladi?", "uz")
    assert meta["last"] == "dairy" and "Izolyat" in reply and str(shop["iso"].id) in ids and meta["profile"]["lactose_free"]
    reply, ids, _c, meta = answer({}, "у меня аллергия на молоко, какой протеин можно?", "ru")
    assert meta["last"] == "dairy" and "нельзя" in reply and ids == [str(shop["plant"].id)]


def test_where_from_is_not_the_store_address():
    assert nlu.parse("proteinni qayerdan olsam bo'ladi").intent != "faq_stores"
    assert nlu.parse("do'koningiz qayerda").intent == "faq_stores"


def test_brand_tiers():
    assert expert.brand_tier("Optimum Nutrition") == 3 and expert.brand_tier("Nutrex Research") == 2 and expert.brand_tier("Zorvex") == 1
