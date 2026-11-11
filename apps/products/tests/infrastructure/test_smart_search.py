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


class TestRunTogetherAndShorthand:
    """Shoppers glue words, drop spaces and type brand shorthand: "goldstandart" must still be Optimum Nutrition Gold Standard."""

    GSW = _entry("Optimum Nutrition Gold Standard 100% Whey 2.27 kg", brand="Optimum Nutrition", category="Protein", popularity=50)
    MASS = _entry("Optimum Nutrition Serious Mass 5.4 kg", brand="Optimum Nutrition", category="Gainer")
    PRE = _entry("Cellucor C4 Original", brand="Cellucor", category="Pre-workout")
    R1 = _entry("Rule 1 R1 Whey Blend", brand="Rule 1", category="Protein")
    INDEX = [GSW, MASS, PRE, R1]

    @pytest.mark.parametrize("query", ["goldstandart", "goldstandard", "gold standart", "goldstandartwhey", "голд стандарт", "gsw", "on gold"])
    def test_gold_standard_found_however_it_is_typed(self, query):
        assert ss.search(query, self.INDEX).product_ids[0] == self.GSW.id

    def test_run_together_typo_suggests_the_label_spelling(self):
        assert ss.search("goldstandart", self.INDEX).suggestion == "gold standard"

    @pytest.mark.parametrize("query, expected", [("seriousmass", "MASS"), ("preworkout", "PRE"), ("rule one", "R1")])
    def test_glued_category_and_number_words(self, query, expected):
        assert ss.search(query, self.INDEX).product_ids[0] == getattr(self, expected).id

    def test_on_alone_means_optimum_nutrition(self):
        assert set(ss.search("ON", self.INDEX).product_ids) == {self.GSW.id, self.MASS.id}

    def test_one_unknown_word_shows_the_nearest_products_instead_of_nothing(self):
        assert ss.search("gold zzqx", self.INDEX).product_ids == [self.GSW.id]


class TestEditDistanceSpeedups:
    """damerau()'s early exit and the letter pre-filter in _scores_for() are speedups only -- they must never change a score."""

    @staticmethod
    def _reference(a: str, b: str) -> int:
        prev2, prev = None, list(range(len(b) + 1))
        for i in range(1, len(a) + 1):
            cur = [i] + [0] * len(b)
            for j in range(1, len(b) + 1):
                cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
                if prev2 is not None and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                    cur[j] = min(cur[j], prev2[j - 2] + 1)
            prev2, prev = prev, cur
        return prev[-1]

    def test_limited_distance_agrees_with_the_full_table(self):
        import random

        rng = random.Random(7)
        for _ in range(3000):
            a = "".join(rng.choice("aekrtns") for _ in range(rng.randint(0, 9)))
            b = "".join(rng.choice("aekrtns") for _ in range(rng.randint(0, 9)))
            exact = self._reference(a, b)
            for limit in (0, 1, 2, 3):
                got = ss.damerau(a, b, limit)
                assert got == exact if exact <= limit else got > limit, (a, b, limit)
            assert ss.damerau(a, b) == exact

    def test_prefilter_keeps_every_match(self):
        words = ["kreatin", "kreatine", "proteini", "protein", "goldstandard", "gold", "standard", "vitamin", "massa", "mas", "aplied", "pld", "izolat"]
        prepared = ss._Prepared({w: [(0, "name")] for w in words})
        for query in ("kraet", "creatne", "protien", "goldstandart", "vitamini", "massu", "applayd", "izolyat", "xyz"):
            key = ss.phonetic(query)
            expected = {w: ss.word_score(key, w) for w in words if ss.word_score(key, w) > 0 or ss._same_stem(key, w)}
            assert ss._scores_for(prepared, key) == expected, query


def test_cyrillic_bcaa_misspelt_protein_and_sport_nutrition():
    bcaa, whey, stress = _entry("Olimp BCAA Xplode"), _entry("Optimum Gold Standard Whey Protein", popularity=50), _entry("Solaray Vitamin B-Stress")
    index = [bcaa, whey, stress]
    assert ss.search("бцаа", index).product_ids[:1] == [bcaa.id]
    assert ss.search("protien", index).product_ids[:1] == [whey.id]
    assert ss.search("спортивное питание", index).product_ids[:1] == [whey.id]
    assert ss._expand_aliases(["bcaa", "2", "1", "1"]) == ["bcaa", "2", "1", "1"]  # numbers are never collapsed


class TestTypedWordTolerance:
    """"d3" / "b12" are one typed word: splitting them into "d 3" must not unlock the one-missed-word allowance."""

    D3 = _entry("NOW Vitamin D3 2000 IU", brand="NOW Foods", category="Vitamins")
    B12 = _entry("Solgar Vitamin B12 1000 mcg", brand="Solgar", category="Vitamins")
    OMEGA3 = _entry("Omega 3 Fish Oil with Vitamin E", brand="NOW Foods", category="Vitamins")
    IDX = [D3, B12, OMEGA3]

    def test_vitamin_d3_finds_only_d3(self):
        assert ss.search("vitamin d3", self.IDX).product_ids == [self.D3.id]

    def test_three_typed_words_still_tolerate_one_miss(self):
        assert self.D3.id in ss.search("now vitamin d3 kapsula", self.IDX).product_ids
