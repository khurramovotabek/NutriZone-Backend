"""
Smart product search -- typo-tolerant, prefix-aware, language-agnostic.

Why not Postgres FTS + trigram alone (the previous engine): it matched
only the requester's own locale, only whole stemmed words ("crea" and
"aplied" found nothing), and "kreatin" / "креатин" / "creatine" were
three unrelated strings. A shopper types however they type -- partial,
misspelled, Latin or Cyrillic, Uzbek/Russian/English -- and still means
the same product.

How a query is matched, per word:

1. **normalize** -- lowercase, strip accents, transliterate Russian and
   Uzbek Cyrillic to Latin, drop Uzbek apostrophes (o', g'), split
   "250g" into "250 g". "креатин" -> "kreatin".
2. **phonetic key** -- fold letters that sound alike across the three
   languages' spellings: c/k/q -> k, y -> i, w -> v, h -> g ("hydrate" /
   "гидрат"), ph -> f, doubled letters -> one. "creatine", "kreatin",
   "креатин" all become "kreatin(e)".
3. **word match**, best of:
   exact key (1.0) > key prefix, "crea" -> "creatine" (0.9-1.0) >
   prefix within 1-2 typos, "kraet" -> "kreatin" (~0.8) > whole-word
   Damerau-Levenshtein similarity (~0.7-0.85) > consonant skeleton,
   "applayd" / "applied" both "pld" (0.65).
4. **product score** -- every query word must match something in the
   product's index (names in all three languages, brand, category,
   SKU/barcode); with 3+ words one unmatched word is tolerated. Ranked by
   match quality, a whole-phrase bonus, then popularity (units sold
   online + at the POS) and availability -- so "kreatin" recommends the
   best-selling creatines first.

5. **meaning, not just spelling** -- a product is also indexed under the
   shopper's vocabulary for what it *is* (CONCEPTS: whey/protein/oqsil/
   протеин/белок are one thing), what it is *for* (its training goals:
   "ozish", "похудение", "massa"...), its tags and flavours. Filler words
   ("uchun", "для", "for") are ignored, so "ozish uchun" means "ozish".

The index (all published products) is built once and cached; any
catalog write bumps its version (see `invalidate_index`, wired to
model signals in apps.py). Plain Python over an in-memory index: the
catalog is thousands of products, not millions, and this keeps the
matching rules explicit and testable.
"""
from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass, field

from django.core.cache import cache

# --------------------------------------------------------------------------
# Text normalization
# --------------------------------------------------------------------------

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "j", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Uzbek Cyrillic
    "ў": "o", "қ": "k", "ғ": "g", "ҳ": "h",
}
_APOSTROPHES = "'`’‘ʻʼ"
_WORD_RE = re.compile(r"[a-z0-9]+")
_SPLIT_DIGIT_LETTER = re.compile(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)")


def normalize(text: str) -> str:
    """Lowercase Latin-only text, words separated by single spaces."""
    text = (text or "").lower()
    text = "".join(_CYRILLIC.get(ch, ch) for ch in text)
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    for mark in _APOSTROPHES:
        text = text.replace(mark, "")
    text = _SPLIT_DIGIT_LETTER.sub(" ", text)
    return " ".join(_WORD_RE.findall(text))


def phonetic(word: str) -> str:
    """Spelling-insensitive key for one normalized word (numbers pass through)."""
    if word.isdigit():
        return word
    w = word
    for src, dst in (("sh", "\x01"), ("ch", "\x02"), ("ph", "f"), ("ck", "k"), ("kh", "g"), ("ts", "s"), ("x", "ks")):
        w = w.replace(src, dst)
    w = w.translate(str.maketrans({"c": "k", "q": "k", "y": "i", "w": "v", "h": "g", "j": "j"}))
    w = w.replace("\x01", "sh").replace("\x02", "ch")
    return re.sub(r"(.)\1+", r"\1", w)


def skeleton(key: str) -> str:
    """Consonants of a phonetic key -- survives vowel typos ("applayd" ~ "applied")."""
    return re.sub(r"[aeiou]", "", key)


def damerau(a: str, b: str, limit: int | None = None) -> int:
    """Optimal-string-alignment edit distance (insert/delete/substitute/adjacent swap)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if limit is not None and abs(la - lb) > limit:
        return limit + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


def _allowed_typos(length: int) -> int:
    return 0 if length < 4 else 1 if length < 7 else 2


def _prefix_typo_score(query_key: str, word_key: str) -> float:
    """The typed word is the start of the indexed word, within 1-2 typos ("kraet" -> "kreatin")."""
    ql, wl = len(query_key), len(word_key)
    typos = _allowed_typos(ql)
    if not typos or wl < ql:
        return 0.0
    best = 0.0
    d = damerau(query_key, word_key[:ql], typos)
    if d <= typos:
        best = 0.82 - 0.08 * d
    if wl > ql:  # one inserted/deleted letter inside the typed prefix
        d = damerau(query_key, word_key[: ql + 1], typos)
        if d <= typos:
            best = max(best, 0.8 - 0.08 * d)
    return best


def _whole_word_score(query_key: str, word_key: str) -> float:
    """Whole-word Damerau-Levenshtein similarity ("creatne" -> "creatine")."""
    if len(query_key) < 4:
        return 0.0
    longest = max(len(query_key), len(word_key))
    similarity = 1 - damerau(query_key, word_key, max(2, longest // 3)) / longest
    return 0.85 * similarity if similarity >= 0.7 else 0.0


def _skeleton_score(query_key: str, word_key: str) -> float:
    """Same consonants, different vowels ("applayd" -> "applied")."""
    sq, sw = skeleton(query_key), skeleton(word_key)
    if len(sq) >= 3 and (sw == sq or sw.startswith(sq)) and abs(len(query_key) - len(word_key)) <= max(3, len(word_key) // 2):
        return 0.65
    return 0.0


def word_score(query_key: str, word_key: str) -> float:
    """How well one query word matches one indexed word, 0..1 (0 = no match)."""
    if not query_key or not word_key:
        return 0.0
    if query_key == word_key:
        return 1.0
    if query_key.isdigit() or word_key.isdigit():
        # numbers (weights, sizes) match exactly or as a prefix, never fuzzily
        return 0.85 if query_key.isdigit() and word_key.isdigit() and word_key.startswith(query_key) else 0.0
    if len(word_key) > len(query_key) >= 2 and word_key.startswith(query_key):
        return 0.88 + 0.12 * (len(query_key) / len(word_key))
    return max(_prefix_typo_score(query_key, word_key), _whole_word_score(query_key, word_key), _skeleton_score(query_key, word_key))


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------

_CACHE_VERSION_KEY = "smart_search:index_version"
_CACHE_TTL = 60 * 30
_FIELD_WEIGHTS = {"name": 1.0, "brand": 0.97, "category": 0.9, "code": 1.0, "tag": 0.9, "concept": 0.86, "goal": 0.84}

# What shoppers call each kind of product, in Uzbek / Russian / English (any script -- normalize() handles it).
# A product whose own name/category/tags contain any word of a group is indexed under the whole group.
CONCEPTS: tuple[tuple[str, ...], ...] = (
    ("protein", "proteini", "whey", "vey", "izolyat", "isolate", "kazein", "casein", "oqsil", "протеин", "белок", "сывороточный", "изолят", "казеин"),
    ("kreatin", "creatine", "креатин"),
    ("gainer", "geyner", "гейнер", "углеводы", "carbs"),
    ("bcaa", "eaa", "amino", "aminokislota", "aminokislotalar", "аминокислоты", "глютамин", "glutamine", "glutamin"),
    ("vitamin", "vitaminlar", "multivitamin", "витамин", "витамины", "мультивитамины"),
    ("omega", "omega3", "baliq", "fish", "oil", "омега", "рыбий"),
    ("preworkout", "predtren", "предтрен", "предтреник", "предтренировочный", "pump", "pamp"),
    ("karnitin", "carnitine", "карнитин", "burner", "жиросжигатель", "yogyoqar", "termogenik", "thermogenic"),
    ("kollagen", "collagen", "коллаген", "bogim", "суставы", "joint"),
    ("magniy", "magnesium", "магний", "rux", "zinc", "цинк", "mineral", "minerallar", "минералы"),
    ("batonchik", "bar", "bars", "батончик", "батончики"),
)

# Training goals (goals.py codes) -> how people ask for them.
GOAL_TERMS: dict[str, tuple[str, ...]] = {
    "muscle": ("mushak", "mushaklar", "massa", "muscle", "mass", "bulk", "мышцы", "мышечная", "масса", "набор", "рост"),
    "weight_loss": ("ozish", "ozdirish", "ozg'in", "vazn", "yog'", "yoqish", "weight", "loss", "fat", "slim", "похудение", "похудеть", "сжигание", "жира", "сушка"),
    "endurance": ("chidamlilik", "energiya", "kuch", "endurance", "energy", "stamina", "выносливость", "энергия", "сила"),
    "health": ("salomatlik", "sog'liq", "immunitet", "health", "immunity", "wellness", "здоровье", "иммунитет"),
}

# Words that carry no product meaning in a query ("ozish uchun", "протеин для массы", "protein for women" keeps "women").
STOPWORDS = frozenset({"uchun", "va", "bilan", "eng", "yaxshi", "ham", "для", "и", "с", "лучший", "for", "and", "with", "the", "best", "of", "a"})
MATCH_THRESHOLD = 0.6


@dataclass
class IndexedProduct:
    id: str
    # (phonetic key, field) pairs; a word may appear under several fields
    words: list[tuple[str, str]] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)  # normalized full names, for the whole-phrase bonus
    display_words: dict[str, str] = field(default_factory=dict)  # phonetic key -> a readable normalized word
    popularity: int = 0
    in_stock: bool = False


def _fresh_version() -> int:
    # Never restarts at a small number: if the cache is flushed/restarted, a process's in-memory copy of an old
    # "v1" must not match the new "v1" (see _LOCAL) -- a millisecond timestamp is new every time.
    return int(time.time() * 1000)


def invalidate_index(**_kwargs) -> None:
    """Signal receiver: any catalog write makes the next search rebuild the index."""
    try:
        cache.incr(_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(_CACHE_VERSION_KEY, _fresh_version(), None)


def _index_cache_key() -> str:
    version = cache.get(_CACHE_VERSION_KEY)
    if version is None:
        version = _fresh_version()
        if not cache.add(_CACHE_VERSION_KEY, version, None):  # another process set it first -- use theirs
            version = cache.get(_CACHE_VERSION_KEY) or version
    return f"smart_search:index:v{version}"


_LOCAL: dict = {}  # this process's copy of the current index version -- unpickling thousands of entries per search is the slow part


def get_index() -> list[IndexedProduct]:
    key = _index_cache_key()
    if _LOCAL.get("key") == key:
        return _LOCAL["index"]
    index = cache.get(key)
    if index is None:
        index = build_index()
        cache.set(key, index, _CACHE_TTL)
    _LOCAL.clear()
    _LOCAL.update(key=key, index=index)
    return index


@dataclass
class _Prepared:
    """An inverted view of one index: each distinct word -> the (entry position, field) pairs it appears under."""

    postings: dict[str, list[tuple[int, str]]]
    token_scores: dict[str, dict[str, float]] = field(default_factory=dict)  # memo: query word -> {matching word: raw score}


_PREPARED: dict = {}


def _prepared(index: list[IndexedProduct]) -> _Prepared:
    if _PREPARED.get("index") is not index:
        postings: dict[str, list[tuple[int, str]]] = {}
        for i, entry in enumerate(index):
            for wk, field_name in entry.words:
                postings.setdefault(wk, []).append((i, field_name))
        _PREPARED.clear()
        _PREPARED.update(index=index, prepared=_Prepared(postings))
    return _PREPARED["prepared"]


def _scores_for(prepared: _Prepared, token_key: str) -> dict[str, float]:
    """Every indexed word the query word matches, scored once per distinct word (not once per product)."""
    scores = prepared.token_scores.get(token_key)
    if scores is None:
        scores = {}
        for wk in prepared.postings:
            s = word_score(token_key, wk)
            if s > 0 or _same_stem(token_key, wk):
                scores[wk] = s
        if len(prepared.token_scores) > 2000:
            prepared.token_scores.clear()
        prepared.token_scores[token_key] = scores
    return scores


def _units_sold_by_product() -> dict[str, int]:
    """Real sales volume -- confirmed online orders plus completed POS sales."""
    from django.db.models import Sum

    from apps.products.infrastructure import models as orm

    sold: dict[str, int] = {}
    try:
        from apps.ordering.infrastructure.models import OrderLineItemModel

        rows = (
            OrderLineItemModel.objects.filter(order__status__in=["confirmed", "processing", "shipped", "delivered", "completed"])
            .values("product_variant_id")
            .annotate(total=Sum("quantity"))
        )
        variant_to_product = dict(orm.ProductVariant.objects.filter(id__in=[r["product_variant_id"] for r in rows]).values_list("id", "product_id"))
        for r in rows:
            product_id = variant_to_product.get(r["product_variant_id"])
            if product_id:
                sold[str(product_id)] = sold.get(str(product_id), 0) + (r["total"] or 0)
    except Exception:  # noqa: BLE001 -- popularity is a ranking hint; search must work without it
        pass
    try:
        from apps.pos.infrastructure.models import SaleLineItemModel

        for r in SaleLineItemModel.objects.filter(sale__status="completed").values("product_id").annotate(total=Sum("quantity")):
            sold[str(r["product_id"])] = sold.get(str(r["product_id"]), 0) + (r["total"] or 0)
    except Exception:  # noqa: BLE001
        pass
    return sold


def _in_stock_products(product_ids: list) -> set[str]:
    from apps.products.infrastructure import models as orm
    from apps.stores.infrastructure.availability import sellable

    product_by_variant = dict(orm.ProductVariant.objects.filter(product_id__in=product_ids).values_list("id", "product_id"))
    return {str(product_by_variant[v]) for v, units in sellable(list(product_by_variant)).items() if units > 0}


def build_index() -> list[IndexedProduct]:
    from apps.products.domain.enums import ProductStatus
    from apps.products.infrastructure import models as orm

    products = list(
        orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value)
        .select_related("brand", "category")
        .prefetch_related("translations", "variants", "brand__translations", "category__translations", "tag_links__tag__translations", "flavours__translations")
    )
    sold = _units_sold_by_product()
    stocked = _in_stock_products([p.id for p in products])

    return [_index_entry(p, sold.get(str(p.id), 0), str(p.id) in stocked) for p in products]


def _searchable_texts(product):
    """(text, field) pairs: name and slug in every locale, brand and category names in every locale, SKUs and barcodes."""
    for t in product.translations.all():
        yield t.name, "name"
        yield t.slug.replace("-", " "), "name"
    brand_translations = product.brand.translations.all() if product.brand_id else []
    category_translations = product.category.translations.all() if product.category_id else []
    yield from ((t.name, "brand") for t in brand_translations)
    yield from ((t.name, "category") for t in category_translations)
    for v in product.variants.all():
        yield from ((code, "code") for code in (v.sku, v.barcode) if code)
    for link in product.tag_links.all():
        yield from ((t.name, "tag") for t in link.tag.translations.all())
    for flavour in product.flavours.all():
        yield from ((t.name, "tag") for t in flavour.translations.all())


def _index_entry(product, popularity: int, in_stock: bool) -> IndexedProduct:
    """Every searchable word of one product, each kept under its highest-weight field."""
    entry = IndexedProduct(id=str(product.id), popularity=popularity, in_stock=in_stock)
    entry.phrases = [normalize(t.name) for t in product.translations.all() if t.name]
    best_field: dict[str, str] = {}
    for text, field_name in _searchable_texts(product):
        keys = [phonetic(word) for word in normalize(text).split()]
        if field_name == "code":
            keys.append(normalize(text).replace(" ", ""))  # the whole code, typed with or without its punctuation
        for key, word in zip(keys, normalize(text).split() + [""], strict=False):
            entry.display_words.setdefault(key, word or key)
        for key in keys:
            if key not in best_field or _FIELD_WEIGHTS[field_name] > _FIELD_WEIGHTS[best_field[key]]:
                best_field[key] = field_name

    def add(keys, field_name):
        for key in keys:
            if key not in best_field:
                best_field[key] = field_name  # no display word: a vocabulary match is never offered as a "did you mean"

    for group in {_CONCEPT_OF[k] for k in list(best_field) if k in _CONCEPT_OF}:
        add(_CONCEPT_KEYS[group], "concept")
    for goal in product.goals or []:
        add(_GOAL_KEYS.get(goal, ()), "goal")
    entry.words = list(best_field.items())
    return entry


def _keys(phrases) -> tuple[str, ...]:
    return tuple(dict.fromkeys(phonetic(w) for phrase in phrases for w in normalize(phrase).split()))


_CONCEPT_KEYS = [_keys(group) for group in CONCEPTS]
_CONCEPT_OF = {key: i for i, keys in enumerate(_CONCEPT_KEYS) for key in keys}
_GOAL_KEYS = {goal: _keys(terms) for goal, terms in GOAL_TERMS.items()}
_VOCAB_FIELDS = frozenset({"concept", "goal"})
_ENDING = re.compile(r"[aeiou]+$")


def _same_stem(a: str, b: str) -> bool:
    """Same word up to a final-vowel ending -- Russian/Uzbek inflection: "massi"/"massu" ~ "massa", "vitamini" ~ "vitamin"."""
    stem_a, stem_b = _ENDING.sub("", a), _ENDING.sub("", b)
    return len(stem_a) >= 3 and stem_a == stem_b
_STOP_KEYS = frozenset(phonetic(normalize(w)) for w in STOPWORDS if normalize(w))


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


@dataclass
class SearchOutcome:
    product_ids: list[str]
    suggestion: str | None


def search(query: str, index: list[IndexedProduct] | None = None) -> SearchOutcome:
    """Ranked product ids for `query`, plus a "did you mean" suggestion when the query only matched fuzzily."""
    normalized = normalize(query)
    tokens = normalized.split()
    meaningful = [t for t in tokens if phonetic(t) not in _STOP_KEYS]
    if meaningful and len(meaningful) < len(tokens):
        tokens = meaningful
        normalized = " ".join(tokens)
    if not tokens:
        return SearchOutcome([], None)
    index = get_index() if index is None else index
    token_keys = [phonetic(t) for t in tokens]
    joined_code = normalized.replace(" ", "")

    prepared = _prepared(index)
    # Per query word: entry position -> its best (word, weighted score), built from the postings of the words it matches.
    best_by_token: list[dict[int, tuple[str, float]]] = []
    for tk in token_keys:
        best: dict[int, tuple[str, float]] = {}
        for wk, raw in _scores_for(prepared, tk).items():
            for i, field_name in prepared.postings[wk]:
                r = raw
                if field_name in _VOCAB_FIELDS and r < 0.9:
                    if not _same_stem(tk, wk):
                        continue  # vocabulary words match as typed, a prefix, or an inflection -- a typo of "olish" is not "ozish"
                    r = 0.95
                weighted = r * _FIELD_WEIGHTS[field_name]
                if weighted > best.get(i, ("", 0.0))[1]:
                    best[i] = (wk, weighted)
        best_by_token.append(best)
    # an exact SKU/barcode typed with its punctuation ("an-crea-250")
    exact_code = {i for i, f in prepared.postings.get(joined_code, []) if f == "code"} if joined_code else set()

    scored: list[tuple[float, IndexedProduct, list[tuple[str, float]]]] = []
    for i in sorted(set().union(*best_by_token) | exact_code):  # index order, so equal scores rank as before
        entry = index[i]
        per_token = [best.get(i, ("", 0.0)) for best in best_by_token]
        if i in exact_code:
            per_token = [(joined_code, 1.0)] * len(token_keys)

        matched = [s for _, s in per_token if s >= MATCH_THRESHOLD]
        tolerated_misses = 1 if len(token_keys) >= 3 else 0
        if len(matched) < len(token_keys) - tolerated_misses or not matched:
            continue

        relevance = sum(s for _, s in per_token) / len(per_token)
        if len(tokens) > 1 and any(normalized in phrase for phrase in entry.phrases):
            relevance += 0.15
        score = relevance * 100 + 3 * math.log1p(entry.popularity) + (1.5 if entry.in_stock else 0)
        scored.append((score, entry, per_token))

    scored.sort(key=lambda row: row[0], reverse=True)
    return SearchOutcome([entry.id for _, entry, _ in scored], _suggestion(tokens, scored))


def _suggestion(tokens: list[str], scored) -> str | None:
    """The top result's own spelling of each word the shopper mistyped -- offered only when something was actually corrected."""
    if not scored:
        return None
    _, top, per_token = scored[0]
    corrected = []
    changed = False
    for original, (word_key, score) in zip(tokens, per_token, strict=True):
        display = top.display_words.get(word_key, original)
        if score >= MATCH_THRESHOLD and score < 0.88 and phonetic(display) != phonetic(original):
            corrected.append(display)
            changed = True
        else:
            corrected.append(original)
    return " ".join(corrected) if changed else None
