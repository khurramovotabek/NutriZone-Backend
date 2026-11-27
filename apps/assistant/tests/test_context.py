"""The conversation layer (advisor/context.py), from the failures found by replaying every real question (2026-11-20)."""
import pytest

from apps.assistant.infrastructure.advisor import brain, context, nlu
from apps.assistant.infrastructure.advisor.engine import answer
from apps.assistant.tests.test_expert_choice import _brand, _cat, _product


@pytest.fixture(autouse=True)
def _fresh_index():
    brain._CACHE.clear()
    brain._CACHE["at"] = 0.0
    yield
    brain._CACHE.clear()
    brain._CACHE["at"] = 0.0


@pytest.fixture
def shop(db):
    sport = _cat("Sports Nutrition")
    proteins = _cat("Proteins", sport)
    creatine = _cat("Creatine", sport)
    vitamins = _cat("Vitamins")
    multi = _cat("Multivitamins", vitamins)
    ostro, dyma, on = _brand("OstroVit"), _brand("Dymatize"), _brand("Optimum Nutrition")
    return {
        "ostro_creatine": _product("OstroVit Creatine Monohydrate", 290_000, creatine, ostro, kg=0.5),
        "cheap_creatine": _product("Budget Kreatin Monohidrat", 150_000, creatine, kg=0.3),
        "iso100": _product("Dymatize ISO100 Hydrolyzed", 1_500_000, proteins, dyma, protein=25, servings=71),
        "gold": _product("Optimum Nutrition Gold Standard 100% Whey", 1_200_000, proteins, on, protein=24, servings=74),
        "on_creatine": _product("Optimum Nutrition Micronized Creatine Powder", 340_000, creatine, on, kg=0.6),
        "mens": _product("Rule 1 Train Daily Men's Multivitamin", 320_000, multi),
        "womens": _product("Opti-Women Multivitamin for women", 300_000, multi),
    }


def test_body_facts_said_the_other_way_round():
    assert nlu.extract_facts(nlu.normalize("165 boyim ogirligim 65")) == {"height": 165, "weight": 65}
    assert nlu.extract_facts(nlu.normalize("vazn 50 buy 180"))["height"] == 180
    assert nlu.parse("creatinew nima uchun").concept == "creatine"
    assert nlu.parse("pumplarni vazifasi nima").concept == "preworkout"


def test_callback_request_is_captured(db):
    reply, ids, _c, meta = answer({}, "Большое спасибо. Можете пожалуйста звонить на номер +998903154499", "ru")
    assert meta["last"] == "callback" and meta["_callback"] == "+998903154499" and "90 315 44 99" in reply
    assert context.callback_phone("narxi 90 315 44 99 mi?") is None  # a number without "call me" isn't a callback


def test_delivery_to_a_named_town_is_delivery_not_prices(shop):
    reply, ids, _c, meta = answer({}, "Toshken viloyat olmaliq shaxriga qanchaga keladi", "uz")
    assert meta["last"] == "faq_delivery" and "Olmaliq" in reply


def test_installment_or_card_is_payment_not_a_comparison(shop):
    reply, _ids, _c, meta = answer({}, "nasiya yoki bo'lib to'lash bormi", "uz")
    assert meta["last"] in ("faq_payment", "knowledge") and "nasiya" in reply.lower()
    _reply, _ids, _c, meta = answer({}, "Картадан утказиб бераман", "uz")
    assert meta["last"] == "faq_payment"


def test_region_without_a_branch_says_so(shop):
    reply, _ids, _c, meta = answer({}, "surxondaryoda filial bormi", "uz")
    assert meta["last"] == "faq_stores" and "Surxondaryo" in reply and "yo'q" in reply


def test_follow_up_how_to_take_uses_the_kind_just_discussed(shop):
    _r, _ids, _c, meta = answer({}, "kreatin kerak", "uz")
    assert meta.get("last_kind") == "creatine"
    reply, _ids, _c, meta = answer(meta, "Qanday ichiladi?", "uz")
    assert "3–5 g" in reply


def test_follow_up_without_context_asks_which_product(db):
    reply, _ids, chips, meta = answer({}, "Qanday ichiladi?", "uz")
    assert meta["last"] == "ask_which" and chips


def test_cheaper_chip_finds_a_cheaper_one_of_the_same_kind(shop):
    _r, ids, _c, meta = answer({}, "kreatin kerak", "uz")
    reply, ids, _c, meta = answer(meta, "Arzonroq variant", "uz")
    assert meta["last"] == "expert_pick" and str(shop["cheap_creatine"].id) in ids


def test_effect_time_from_context(shop):
    _r, _ids, _c, meta = answer({}, "kreatin kerak", "uz")
    reply, _ids, _c, meta = answer(meta, "Ta'siri qancha vaqtda seziladi?", "uz")
    assert meta["last"] == "effect" and "3–4 haftada" in reply


def test_a_product_named_by_name_is_shown_itself(shop):
    _r, ids, _c, meta = answer({}, "Ostovip monogidrat kreatin", "uz")
    assert ids and ids[0] == str(shop["ostro_creatine"].id)
    _r, ids, _c, meta = answer({}, "iso100 olmoqchiman", "uz")
    assert ids == [str(shop["iso100"].id)]
    _r, ids, _c, meta = answer({}, "Optimum Nutrition Gold Standard bormi", "uz")
    assert ids == [str(shop["gold"].id)]  # not the ON creatine


def test_off_topic_sentence_gets_no_random_products(shop):
    _r, ids, _c, meta = answer({}, "bugun ob-havo qanday bo'ladi ertaga", "uz")
    assert ids == [] and meta["last"] == "talk_offtopic"  # outside the shop's field: said so, no random tubs


def test_womens_multivitamin_skips_the_mens_formula(shop):
    _r, ids, _c, _meta = answer({}, "multivitamin ayollarniki kerak", "uz")
    assert str(shop["mens"].id) not in ids and str(shop["womens"].id) in ids


def test_arginine_is_arginine(db):
    reply, _ids, _c, meta = answer({}, "menga arginine kerak va u nima uchun", "uz")
    assert meta["last"] == "arginine" and "L-arginin" in reply


def test_why_without_kerak(shop):
    reply, _ids, _c, meta = answer({}, "kreatin nima uchun", "uz")
    assert meta["last"] in ("why", "knowledge") and "Ha, bor" not in reply


def test_brand_plus_kind_shows_that_brands_kind(shop):
    from apps.assistant.infrastructure.advisor import context as ctx

    names = [x["name"] for x in ctx.named_products("OstroVit kreatin", "uz")]
    assert names and all("Creatine" in n for n in names)
