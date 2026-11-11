"""
Shopping intent inside a search query -- the words that are not a product but an instruction.

"arzon kreatin", "chegirmadagi protein", "500 minggacha gainer", "дешевый протеин до 400 тысяч",
"yangi vitaminlar": a shopper writes the order or the filter into the query. Matched as product words
they found nothing useful ("arzon" is in no product's name) or, worse, dragged in fuzzy neighbours.
`parse()` takes those words out and returns them as a sort order and filters, so the product words
search on their own and the page is ordered / filtered the way the shopper asked.

Only unambiguous words are understood. A number becomes a price only next to a price word ("gacha",
"до", "so'm", "ming"...), so "D3 5000 IU" or "Whey 2270 g" stay product words.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.products.infrastructure.smart_search import normalize

# normalized (Latin, apostrophes dropped) word -> what it asks for; prefixes cover inflections ("chegirmadagi", "скидками")
_SORT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("arzon", "price"), ("deshev", "price"), ("nedorog", "price"), ("cheap", "price"), ("budget", "price"), ("byudjet", "price"),
    ("qimmat", "-price"), ("dorog", "-price"), ("expensive", "-price"),
    ("yangi", "-created_at"), ("novink", "-created_at"), ("noviy", "-created_at"), ("novie", "-created_at"),
    ("mashhur", "-popularity"), ("ommabop", "-popularity"), ("populyar", "-popularity"), ("popular", "-popularity"),
    ("bestseller", "-popularity"),
    ("reyting", "-rating"), ("rating", "-rating"), ("otziv", "-rating"),
)
_SORT_EXACT = {"xit": "-popularity", "hit": "-popularity"}
_SALE_PREFIXES = ("chegirma", "aksiya", "aksiy", "akts", "skidk", "sale", "discount", "rasprodaj")
_STOCK_WORDS = {"mavjud", "nalichii", "nalichie", "stock", "instock"}
# filler around those words: "eng arzon", "по скидке", "в наличии", "on sale", "eng ko'p sotilgan"
_FILLER = {"eng", "po", "v", "na", "s", "so", "ko", "kop", "sotilgan", "sotiladigan", "samiy", "samie", "samaya", "most", "top", "dagi", "lar", "larda", "dan"}

_UPTO = {"gacha", "do", "under", "below", "max", "maks", "arzonroq"}
_FROM = {"dan", "ot", "over", "above", "min", "qimmatroq"}
_THOUSAND = {"ming", "tis", "tisyach", "tisyachi", "tisyach", "k"}
_MILLION = {"mln", "million", "millionov", "mil"}
_CURRENCY = {"som", "sum", "sumov", "uzs"}
_PRICE_WORDS = _UPTO | _FROM | _THOUSAND | _MILLION | _CURRENCY


@dataclass
class Intent:
    query: str  # what is left to search for ("" = browse with the filters below)
    sort: str | None = None
    filters: dict = field(default_factory=dict)  # browse filter keys: on_sale, in_stock, price {gte, lte}
    understood: list[str] = field(default_factory=list)  # machine codes for the storefront's "understood" line


def _match(word: str, prefixes) -> str | None:
    for prefix, value in prefixes:
        if word.startswith(prefix):
            return value
    return None


def _price(tokens: list[str], i: int) -> tuple[int, int, str] | None:
    """A price starting at tokens[i] (a number): (amount in so'm, tokens consumed, "lte"|"gte") -- None unless a price word says so."""
    amount = int(tokens[i])
    j = i + 1
    scaled = False
    # "500 000" written with a space
    while j < len(tokens) and tokens[j] == "000":
        amount = amount * 1000
        j += 1
        scaled = True
    if j < len(tokens) and tokens[j] in _THOUSAND:
        amount, j, scaled = amount * 1000, j + 1, True
    elif j < len(tokens) and tokens[j] in _MILLION:
        amount, j, scaled = amount * 1_000_000, j + 1, True
    if j < len(tokens) and tokens[j] in _CURRENCY:
        j += 1
        scaled = True
    direction = None
    if j < len(tokens) and (tokens[j] in _UPTO or tokens[j].endswith("gacha")):
        direction, j = "lte", j + 1
    elif j < len(tokens) and tokens[j] in _FROM:
        direction, j = "gte", j + 1
        if j < len(tokens) and tokens[j] in {"qimmat", "qimmatroq", "yuqori", "kop", "ortiq", "baland"}:
            j += 1
        elif j < len(tokens) and tokens[j] in {"arzon", "arzonroq", "past", "kam", "kamroq"}:
            direction, j = "lte", j + 1
    elif i > 0 and tokens[i - 1] in {"do", "under", "below", "max", "maks"}:
        direction = "lte"
    elif i > 0 and tokens[i - 1] in {"ot", "over", "above", "min"}:
        direction = "gte"
    if direction is None or (not scaled and amount < 1000):
        return None  # "D3 5000 IU" or a bare "2 gacha" is not a price
    if amount < 10_000:  # "500 gacha" in a price context means thousands of so'm
        amount *= 1000
    return amount, j - i, direction


def _split_suffixes(words: list[str]) -> list[str]:
    """Uzbek glues the preposition on: "minggacha" / "so'mgacha" / "mingdan" / "500000gacha" -> "ming gacha" ..."""
    out: list[str] = []
    for w in words:
        for suffix in ("gacha", "dan"):
            base = w[: -len(suffix)]
            if w.endswith(suffix) and (base in _THOUSAND or base in _MILLION or base in _CURRENCY or base in {"min"}):
                out.extend(["ming" if base == "min" else base, suffix])
                break
        else:
            out.append(w)
    return out


def parse(query: str) -> Intent:
    tokens = _split_suffixes(normalize(query).split())
    if not tokens:
        return Intent(query=query or "")
    keep: list[str] = []
    intent = Intent(query="")
    i = 0
    while i < len(tokens):
        word = tokens[i]
        if word.isdigit():
            price = _price(tokens, i)
            if price:
                amount, consumed, direction = price
                intent.filters.setdefault("price", {})[direction] = str(amount)
                intent.understood.append(f"price_{direction}:{amount}")
                # the preposition before ("до 400", "under 300") belonged to the price as well
                if keep and keep[-1] in {"do", "under", "below", "max", "maks", "ot", "over", "above", "min"}:
                    keep.pop()
                i += consumed
                continue
        sort = _SORT_EXACT.get(word) or _match(word, _SORT_PREFIXES)
        if sort and intent.sort is None:
            intent.sort = sort
            intent.understood.append(f"sort:{sort}")
            i += 1
            continue
        if any(word.startswith(p) for p in _SALE_PREFIXES):
            if not intent.filters.get("on_sale"):
                intent.filters["on_sale"] = True
                intent.understood.append("on_sale")
            i += 1
            continue
        if word in _STOCK_WORDS:
            if not intent.filters.get("in_stock"):
                intent.filters["in_stock"] = True
                intent.understood.append("in_stock")
            i += 1
            continue
        keep.append(word)
        i += 1
    if intent.understood:
        intent.query = " ".join(w for w in keep if w not in _FILLER and w not in _PRICE_WORDS)
    else:
        intent.query = query
    return intent
