"""
Building a supplement "stack" for a goal from NutriZone's live catalogue -- and learning which picks work.

For each goal a short, evidence-based stack of product kinds (protein + creatine for muscle, ...) is searched in the
catalogue (in stock only, budget aware, lactose-free / vegan aware). Candidates are ranked by search relevance,
rating, and the learned score in AdvisorSignal: products shoppers liked (👍), bought after a recommendation or added
to the cart rise; disliked ones sink. The learning is plain counting -- transparent and free.
"""
from __future__ import annotations

from apps.assistant.infrastructure import tools

# goal -> ordered product kinds (first = most important). gainer only for underweight shoppers (see stack()).
STACKS = {
    "muscle": ["protein", "creatine", "gainer"],
    "weight_loss": ["protein", "carnitine", "vitamin"],
    "endurance": ["bcaa", "creatine", "vitamin"],
    "health": ["vitamin", "omega", "collagen"],
}
QUERIES = {
    "protein": "whey protein", "creatine": "creatine", "gainer": "gainer", "bcaa": "bcaa", "carnitine": "carnitine",
    "vitamin": "multivitamin", "omega": "omega 3", "collagen": "collagen", "preworkout": "pre workout",
    "vitamin_d": "vitamin d3", "vitamin_c": "vitamin c", "vitamin_b12": "vitamin b12", "magnesium": "magnesium", "zinc": "zinc",
    "iron": "iron", "calcium": "calcium", "electrolytes": "electrolytes", "glutamine": "glutamine", "beta_alanine": "beta alanine",
    "citrulline": "citrulline", "caffeine": "caffeine", "test_booster": "testosterone", "ashwagandha": "ashwagandha", "zma": "zma",
    "melatonin": "melatonin", "probiotic": "probiotic", "glucosamine": "glucosamine",
}
BUDGET_SHARE = {"protein": 0.55, "creatine": 0.25, "gainer": 0.45, "bcaa": 0.35, "carnitine": 0.3, "vitamin": 0.25, "omega": 0.3, "collagen": 0.3, "preworkout": 0.3}


def learned_scores(product_ids) -> dict:
    from apps.assistant.infrastructure.models import AdvisorSignal

    out = {}
    for s in AdvisorSignal.objects.filter(product_id__in=list(product_ids)):
        out[str(s.product_id)] = (2 * s.liked + 3 * s.purchased + s.carted - 2 * s.disliked) / (s.shown + 5)
    return out


def best_for(concept: str, profile: dict, locale: str, budget_left: int | None, exclude: set) -> dict | None:
    query = QUERIES.get(concept, concept)
    if concept == "protein" and profile.get("vegan"):
        query = "plant protein"
    elif concept == "protein" and (profile.get("lactose_free") or profile.get("goal") == "weight_loss"):
        query = "isolate protein"
    args = {"query": query, "limit": 8, "in_stock_only": True}
    if budget_left:
        args["max_price"] = int(budget_left)
    found = tools.search_products(args, locale)["products"]
    if not found and query != QUERIES.get(concept, concept):  # e.g. no isolate in stock -> any protein
        found = tools.search_products({**args, "query": QUERIES.get(concept, concept)}, locale)["products"]
    if not found and budget_left:  # nothing that cheap -> show the cheapest one anyway, the text explains
        found = sorted(tools.search_products({**args, "max_price": None}, locale)["products"], key=lambda p: p.get("price_uzs") or 0)[:3]
    found = [p for p in found if p["id"] not in exclude and p.get("in_stock")]
    if not found:
        return None
    learned = learned_scores(p["id"] for p in found)
    goal_label = profile.get("goal")

    def score(idx_p):
        idx, p = idx_p
        relevance = 1 - idx / max(len(found), 1)
        rating = (p.get("rating") or 0) / 5 * min((p.get("reviews") or 0) / 3, 1)
        goal_fit = 0.3 if goal_label and p.get("goals") else 0
        return relevance + 0.6 * rating + goal_fit + 1.5 * learned.get(p["id"], 0)

    return max(enumerate(found), key=score)[1]


def stack(profile: dict, locale: str, needs=None) -> list[tuple[str, dict]]:
    goal = profile.get("goal") or "health"
    kinds = list(STACKS.get(goal, STACKS["health"]))
    if goal == "muscle" and not (needs and needs.bmi_band == "under"):
        kinds.remove("gainer")
    if (profile.get("age") or 99) < 18:
        kinds = [k for k in kinds if k in ("protein", "vitamin", "omega")]  # no creatine / stimulants for minors
    budget = profile.get("budget")
    picks: list[tuple[str, dict]] = []
    spent = 0
    for kind in kinds:
        left = int(budget * BUDGET_SHARE.get(kind, 0.3)) if budget else None
        if budget and spent >= budget:
            break
        p = best_for(kind, profile, locale, left, {x["id"] for _k, x in picks})
        if p:
            picks.append((kind, p))
            spent += p.get("price_uzs") or 0
    return picks


def record_shown(product_ids) -> None:
    from django.db.models import F

    from apps.assistant.infrastructure.models import AdvisorSignal

    for pid in product_ids:
        obj, created = AdvisorSignal.objects.get_or_create(product_id=pid, defaults={"shown": 1})
        if not created:
            AdvisorSignal.objects.filter(pk=pid).update(shown=F("shown") + 1)


def record_feedback(product_ids, value: str | None, old: str | None) -> None:
    """A 👍 / 👎 on an answer counts for every product it showed (changing the vote moves the count)."""
    from django.db.models import F

    from apps.assistant.infrastructure.models import AdvisorSignal

    delta = {"liked": (value == "up") - (old == "up"), "disliked": (value == "down") - (old == "down")}
    for pid in product_ids:
        AdvisorSignal.objects.get_or_create(product_id=pid)
        AdvisorSignal.objects.filter(pk=pid).update(**{k: F(k) + v for k, v in delta.items() if v})
