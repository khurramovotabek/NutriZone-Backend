"""
Smart product search (infrastructure/smart_search.py): prefix, typo,
transliteration and cross-language matching, popularity-aware ranking,
and "did you mean" suggestions.
"""
from __future__ import annotations

import uuid

import pytest

from apps.products.infrastructure import smart_search as ss


def _entry(name: str, *, brand: str = "", category: str = "", codes=(), popularity: int = 0, in_stock: bool = True, other_names=(), tags=(), goals=()):
    """A synthetic index entry built through the same code path as the real index."""

    class _T:
        def __init__(self, name):
            self.name, self.slug = name, ""

    class _Qs(list):
        def all(self):
            return self

    class _V:
        def __init__(self, code):
            self.sku, self.barcode = code, None

    product = type("P", (), {})()
    product.id = uuid.uuid4()
    product.translations = _Qs(_T(n) for n in (name, *other_names))
    product.brand_id = brand or None
    product.brand = type("B", (), {"translations": _Qs([_T(brand)])})() if brand else None
    product.category_id = category or None
    product.category = type("C", (), {"translations": _Qs([_T(category)])})() if category else None
    product.variants = _Qs(_V(c) for c in codes)
    product.tag_links = _Qs(type("L", (), {"tag": type("G", (), {"translations": _Qs([_T(t)])})()})() for t in tags)
    product.flavours = _Qs()
    product.goals = list(goals)
    return ss._index_entry(product, popularity, in_stock)


CREATINE_AN = _entry("Applied Nutrition Creatine Monohydrate 250 g", brand="Applied Nutrition", category="Sports Nutrition", codes=["AN-CREA-250"], popularity=40, other_names=["Applied Nutrition Креатин Моногидрат 250 г"])
CREATINE_ON = _entry("Optimum Nutrition Micronized Creatine Powder 300 g", brand="Optimum Nutrition", category="Sports Nutrition", popularity=120)
CREATINE_CHEAP = _entry("Kreatin monogidrat 500 g", brand="NoName", category="Sports Nutrition", popularity=2)
WHEY = _entry("Gold Standard 100% Whey 2.27 kg", brand="Optimum Nutrition", category="Protein", popularity=300, other_names=["Gold Standard 100% Сывороточный протеин"])
INDEX = [CREATINE_AN, CREATINE_ON, CREATINE_CHEAP, WHEY]
CREATINES = {CREATINE_AN.id, CREATINE_ON.id, CREATINE_CHEAP.id}


def _ids(query):
    return ss.search(query, INDEX).product_ids


class TestNormalization:
    @pytest.mark.parametrize("raw, expected", [
        ("Креатин", "kreatin"),
        ("O‘zbekiston G'isht", "ozbekiston gisht"),
        ("250g", "250 g"),
        ("  Whey-Protein!! ", "whey protein"),
        ("Қатиқ ҳамма", "katik hamma"),
    ])
    def test_normalize(self, raw, expected):
        assert ss.normalize(raw) == expected

    def test_spellings_of_creatine_share_one_phonetic_key(self):
        keys = {ss.phonetic(ss.normalize(w)) for w in ("creatin", "kreatin", "креатин", "kreattin")}
        assert len(keys) == 1


class TestWordScore:
    def test_exact_and_prefix(self):
        assert ss.word_score("kreatin", "kreatin") == 1.0
        assert ss.word_score("krea", "kreatine") >= 0.88

    def test_typos_within_a_prefix_and_a_whole_word(self):
        assert ss.word_score(ss.phonetic("kraet"), ss.phonetic("kreatine")) >= ss.MATCH_THRESHOLD
        assert ss.word_score(ss.phonetic("creatne"), ss.phonetic("creatine")) >= ss.MATCH_THRESHOLD

    def test_vowel_typos_via_consonant_skeleton(self):
        assert ss.word_score(ss.phonetic("applayd"), ss.phonetic("applied")) >= ss.MATCH_THRESHOLD

    def test_unrelated_words_do_not_match(self):
        assert ss.word_score(ss.phonetic("whey"), ss.phonetic("creatine")) < ss.MATCH_THRESHOLD
        assert ss.word_score("250", "300") == 0.0


class TestSearch:
    @pytest.mark.parametrize("query", ["crea", "creat", "creatin", "creatine", "kreatin", "креатин", "КРЕАТИН", "kreattin", "creatne"])
    def test_every_spelling_of_creatine_finds_all_creatines_and_nothing_else(self, query):
        assert set(_ids(query)) == CREATINES

    def test_generic_query_ranks_best_sellers_first(self):
        assert _ids("kreatin")[0] == CREATINE_ON.id  # 120 sold, the most popular creatine

    @pytest.mark.parametrize("query", ["applayd creat", "applied creatine", "aplied kreatin", "applied nutrtion creatne 250g", "applied креатин"])
    def test_misspelled_brand_plus_product_finds_that_exact_product_first(self, query):
        assert _ids(query)[0] == CREATINE_AN.id

    def test_brand_query_returns_that_brands_products(self):
        assert set(_ids("optimum")) == {CREATINE_ON.id, WHEY.id}

    def test_cross_language_names(self):
        assert _ids("протеин") == [WHEY.id]
        assert _ids("whey")[0] == WHEY.id

    def test_exact_sku_with_or_without_punctuation(self):
        assert _ids("AN-CREA-250")[0] == CREATINE_AN.id
        assert _ids("an crea 250")[0] == CREATINE_AN.id

    def test_nonsense_finds_nothing(self):
        assert _ids("xyzzy") == []
        assert _ids("") == []

    def test_one_noise_word_tolerated_in_a_long_query(self):
        assert _ids("applied creatine blablabla")[0] == CREATINE_AN.id

    def test_in_stock_breaks_a_tie(self):
        a = _entry("Test Creatine A", popularity=0, in_stock=False)
        b = _entry("Test Creatine B", popularity=0, in_stock=True)
        assert ss.search("test creatine", [a, b]).product_ids[0] == b.id


class TestSuggestion:
    def test_suggests_the_correct_spelling_of_mistyped_words(self):
        assert ss.search("applayd creat", INDEX).suggestion == "applied creat"
        assert ss.search("applied nutrtion creatne", INDEX).suggestion == "applied nutrition creatine"

    def test_no_suggestion_when_nothing_was_corrected(self):
        assert ss.search("applied creatine", INDEX).suggestion is None
        assert ss.search("crea", INDEX).suggestion is None


@pytest.mark.django_db
class TestSearchApi:
    """End to end through GET /api/v1/products/search with real rows, the cache, and the index invalidation signals."""

    def _product(self, names: dict[str, str]):
        from apps.products.infrastructure import models as p_models

        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        for locale, name in names.items():
            p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code=locale, name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=True)
        return product

    @pytest.mark.parametrize("query, locale", [("crea", "uz"), ("креатин", "en"), ("kreatin", "ru"), ("zorbastic krea", "uz")])
    def test_finds_across_languages_regardless_of_requested_locale(self, client, query, locale):
        suffix = uuid.uuid4().hex[:6]
        product = self._product({"en": f"Zorbastic{suffix} Creatine 300 g", "ru": f"Zorbastic{suffix} Креатин 300 г"})
        query = query.replace("zorbastic", f"zorbastic{suffix}")

        response = client.get("/api/v1/products/search", {"q": query, "filter[locale]": locale})

        assert response.status_code == 200
        assert str(product.id) in [row["id"] for row in response.json()["data"]]

    def test_newly_created_product_is_searchable_immediately(self, client):
        suffix = uuid.uuid4().hex[:6]
        client.get("/api/v1/products/search", {"q": "warmup"})  # build + cache the index first
        product = self._product({"en": f"Quixotal{suffix} Glutamine"})

        response = client.get("/api/v1/products/search", {"q": f"quixotal{suffix} glutamin"})

        assert str(product.id) in [row["id"] for row in response.json()["data"]]

    def test_suggestion_is_returned_in_meta(self, client):
        suffix = "".join(chr(ord("a") + int(c, 16) % 26) for c in uuid.uuid4().hex[:5])  # letters only: digits would be split off as their own word
        self._product({"en": f"Vexamine{suffix} Creatine"})
        response = client.get("/api/v1/products/search", {"q": f"vexamine{suffix} creatne"})
        assert response.json()["meta"]["suggestion"] == f"vexamine{suffix} creatine"


class TestMeaningVocabulary:
    """Shoppers ask for what a product is and what it is for, in any of the three languages."""

    WHEY = _entry("Gold Standard 100%", brand="Optimum Nutrition", codes=("ON-WHEY-227",), goals=("muscle",))
    BURNER = _entry("Lipo Shred", tags=("L-Carnitine",), goals=("weight_loss",))
    CREATINE = _entry("Creatine Monohydrate 250 g", goals=("muscle", "endurance"))
    INDEX = [WHEY, BURNER, CREATINE]

    @pytest.mark.parametrize("query", ["protein", "протеин", "oqsil", "белок", "whey"])
    def test_product_kind_synonyms_find_the_whey(self, query):
        assert ss.search(query, self.INDEX).product_ids[:1] == [self.WHEY.id]

    @pytest.mark.parametrize("query", ["ozish uchun", "похудение", "weight loss", "карнитин"])
    def test_weight_loss_words_find_only_the_burner(self, query):
        assert ss.search(query, self.INDEX).product_ids == [self.BURNER.id]

    def test_goal_words_find_every_product_for_that_goal(self):
        assert set(ss.search("massa", self.INDEX).product_ids) == {self.WHEY.id, self.CREATINE.id}

    def test_filler_words_are_ignored_but_a_lone_filler_is_kept(self):
        assert ss.search("kreatin для массы", self.INDEX).product_ids == [self.CREATINE.id]
        assert ss.search("uchun", self.INDEX).product_ids == []

    def test_vocabulary_is_not_typo_matched(self):
        assert self.WHEY.id not in ss.search("olish", self.INDEX).product_ids  # "olish" is not "ozish"/"massa olish"

    def test_no_suggestion_for_a_correctly_spelled_vocabulary_word(self):
        assert ss.search("massa", self.INDEX).suggestion is None

    def test_inflected_vocabulary_word_matches_without_a_suggestion(self):
        outcome = ss.search("протеин для массы", self.INDEX)
        assert outcome.product_ids == [self.WHEY.id] and outcome.suggestion is None
