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


def test_numbers_read_from_the_card_text():
    facts = "1 porsiya (30 g) uchun:\n\nPorsiya — 30 g\n\nQadoqdagi porsiyalar soni — 23"
    assert expert.text_numbers(facts, "~80% oqsil") == {"serving_g": 30.0, "servings": 23.0, "protein": 24.0}
    assert expert.text_numbers("Порция 30 г: белок 22 г. Порций в упаковке: 30") == {"serving_g": 30.0, "servings": 30.0, "protein": 22.0}
    assert expert.text_numbers("Kuniga 1–3 porsiya ichiladi") == {}


def test_general_protein_prefers_everyday_whey_over_casein(shop):
    from apps.assistant.tests.test_expert_choice import _cat, _product

    casein = _product("Zorvex Micellar Casein", 200_000, _cat("Casein"), protein=24, servings=74)  # cheapest per gram
    reply, ids, *_ = answer({}, "500 minggacha protein", "uz")
    assert ids[0] != str(casein.id) and "Mening tanlovim: Gold Standard" in reply


@pytest.mark.parametrize("text,loc,word", [
    ("протеин до 500 тысяч", "ru", "Мой выбор"),
    ("какой креатин лучше", "ru", "Мой выбор"),
    ("best protein under 500k", "en", "My pick"),
    ("креатин керак", "uz", "Mening tanlovim"),
])
def test_other_languages_and_cyrillic(shop, text, loc, word):
    reply, ids, *_ = answer({}, text, loc)
    assert word in reply and ids


def test_personal_dose_from_weight_and_goal(shop):
    reply, ids, _c, meta = answer({}, "90 kg, massa olmoqchiman. kreatinni qanday ichaman?", "uz")
    assert meta["last"] == "personal_usage" and "kuniga **5 g**" in reply and ids == [str(shop["creatine"].id)]
    reply, *_r, meta = answer({"profile": {"weight": 70, "goal": "weight_loss"}}, "протеин как принимать", "ru")
    assert "140–168 г белка" in reply


def test_stack_answer_has_a_daily_schedule(shop):
    reply, *_ = answer({}, "180 sm, 75 kg, 25 yosh, massa olmoqchiman", "uz")
    assert "Kun tartibi" in reply and "Mashg'ulotdan keyin" in reply


def test_two_named_products_are_compared_side_by_side(shop):
    reply, ids, _c, meta = answer({}, "Gold Standard 100% Whey va Isolate qaysi yaxshi?", "uz")
    assert meta["last"] == "compare_named" and set(ids) == {str(shop["gold"].id), str(shop["iso"].id)}
    assert "solishtirdim" in reply and "arzonroq" in reply


def test_is_it_needed_question_is_not_a_shopping_list(shop):
    _r, _ids, _c, meta = answer({}, "kreatin kerakmi?", "uz")
    assert meta["last"] != "expert_pick"


def test_vegan_question_shows_vegan_products(shop):
    _r, ids, *_ = answer({}, "vegan protein nima?", "uz")
    assert ids == [str(shop["plant"].id)]


def test_gainer_is_not_priced_per_25g_protein(shop):
    from apps.assistant.tests.test_expert_choice import _cat, _product

    g = _product("Zorvex Mass Gainer", 250_000, _cat("Gainers"), protein=30, servings=20, kg=3)
    rows = expert.rank(expert.rows_for([str(g.id)], "uz"), "gainer")
    assert "25 g oqsil" not in expert._numbers(rows[0], "uz") and "porsiyasi" in expert._numbers(rows[0], "uz")


@pytest.mark.parametrize("text,yes", [
    ("kreatin kerak", True), ("eng yaxshi izolyat", True), ("sut ko'tarmayman qornim shishadi", True), ("Gold Standard va Iso100 qaysi yaxshi", True),
    ("протеин до 400 тысяч", True), ("whey protein", False), ("kreatin", False), ("salom", False),
])
def test_telegram_sends_consultant_questions_to_the_advisor(text, yes):
    assert expert.wants_consultant(text) is yes


@pytest.fixture
def more(shop):
    pre, burn = _cat("Pre-Workout"), _cat("Fat Burners")
    return {
        "pump": _product("Zorvex Stim-Free Pump", 260_000, pre, kg=0.3),
        "blast": _product("Zorvex Caffeine Blast Pre-Workout", 240_000, pre, kg=0.3),
        "caff": _product("Zorvex Caffeine 200 mg", 90_000, burn, kg=0.1),
        "carn": _product("Zorvex L-Carnitine 3000", 200_000, burn, kg=0.5),
        "amino": _product("Zorvex BCAA 2:1:1", 150_000, _cat("Amino Acids"), kg=0.3),
        "eaa": _product("Zorvex EAA", 160_000, _cat("Amino Acids"), kg=0.3),
    }


def test_stim_free_pre_workout_has_no_caffeine(more):
    reply, ids, _c, meta = answer({}, "pre workout tavsiya qiling kofeinsiz", "uz")
    assert meta["last"] == "expert_pick" and ids == [str(more["pump"].id)] and "Kofeinsiz" in reply


def test_carnitine_is_not_any_fat_burner(more):
    _r, ids, _c, meta = answer({}, "какой л-карнитин лучше для похудения", "ru")
    assert ids == [str(more["carn"].id)]


def test_sugar_free_protein_means_isolate(shop):
    reply, ids, _c, meta = answer({}, "протеин без сахара есть?", "ru")
    assert meta["last"] == "expert_pick" and ids == [str(shop["iso"].id)] and "без сахара" in reply


def test_two_kinds_are_explained_not_two_tubs(more):
    _r, _ids, _c, meta = answer({}, "bcaa yoki eaa qaysi yaxshi", "uz")
    assert meta["last"] not in ("compare_named", "expert_pick")


def test_sore_muscles_are_not_a_mass_goal():
    assert nlu.parse("mushak og'riyapti trenirovkadan keyin nima ichay").goal is None
    assert nlu.parse("mushak massasi uchun nima ichay").goal == "muscle"


def test_diabetes_protein_gets_a_real_answer(shop):
    reply, ids, _c, meta = answer({}, "qandli diabet bor protein ichsa bo'ladimi", "uz")
    assert meta["last"] == "health" and "izolyat" in reply and ids == [str(shop["iso"].id)]


def test_kidneys_are_not_kids(db):
    assert "child" not in brain.understand("is creatine safe for kidneys").health
    assert "child" in brain.understand("can my kids take protein").health


def test_fat_loss_protein_is_an_isolate(shop):
    reply, ids, _c, meta = answer({}, "ozish uchun eng yaxshi protein qaysi", "uz")
    assert meta["last"] == "expert_pick" and ids == [str(shop["iso"].id)] and "Ozish uchun — izolyat" in reply
