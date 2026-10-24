"""
The assistant's tools -- the ONLY way it learns about products, prices, stock and stores. Each returns compact JSON
built from the same selectors the storefront uses (catalog_browse ranking + filters, product detail, WMS
availability), so the assistant can't quote a price or a stock level the site wouldn't show.

Inputs come from the model: every function validates its arguments itself and answers a bad call with an error the
model can read (never an exception). Product text (descriptions, directions) is shop data handed to the model as
data -- the system prompt tells it to treat instructions found there as text, not commands.
"""
from __future__ import annotations

import json
import re
import uuid
from contextvars import ContextVar
from decimal import Decimal

from apps.products.infrastructure import goals as goal_book

# The signed-in customer of the turn being answered (set by the engine; None for guests).
CURRENT_CUSTOMER: ContextVar = ContextVar("assistant_customer", default=None)

MAX_RESULTS = 8
MAX_SHOW = 4
TEXT_LIMIT = 1200

TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Search NutriZone's catalogue (sports nutrition and supplements). Returns up to `limit` published products "
            "with id, name, brand, category, price in UZS, discount, stock, rating and the training goals they serve. "
            "Use it before recommending or naming any product. `query` is free text in any language (product kind, brand, "
            "ingredient, e.g. 'whey protein', 'kreatin', 'BCAA'); `goal` narrows to products tagged for a training goal. "
            "Leave `query` empty to browse a goal. Search again with simpler words if nothing fits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search, may be empty."},
                "goal": {"type": "string", "enum": list(goal_book.GOALS), "description": "Training goal filter."},
                "max_price": {"type": "integer", "description": "Highest price in UZS (so'm)."},
                "in_stock_only": {"type": "boolean", "description": "Only products that can be bought now (default true)."},
                "limit": {"type": "integer", "description": "1-8, default 6."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_product_details",
        "description": (
            "Full details of one product by id: description, how to use (directions), warnings, supplement facts, "
            "servings, every size/flavour variant with its price and stock, and the NutriZone branches that have it. "
            "Use it before answering questions about a specific product's use, ingredients or availability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "string", "description": "Product id from search_products."}},
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "show_products",
        "description": (
            "Display product cards (photo, price, stock, add-to-cart button) to the customer under your answer. Call it "
            "whenever you recommend products, with 1-4 ids you got from search_products or get_product_details, best "
            "match first. Never mention a product as a recommendation without showing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"product_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_SHOW}},
            "required": ["product_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_store_info",
        "description": (
            "NutriZone's branches (address, district, phones, opening hours, map link) and the shop's contact details. "
            "Use for questions about where to buy, the nearest branch, a branch's location or phone, pickup or contacting "
            "the shop. Pass `city` (e.g. 'Samarqand') or the customer's coordinates to get the closest branches first "
            "with their distance. Give the branch's map_url when the customer asks where it is."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City or district to filter by, any spelling (Toshkent, Chilonzor, Samarkand...)."},
                "latitude": {"type": "number", "description": "Customer latitude, when known."},
                "longitude": {"type": "number", "description": "Customer longitude, when known."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "browse_catalog",
        "description": (
            "Lists what the catalogue has: `brands`, `categories` or `flavours` (taste options such as Gourmet Chocolate, "
            "French Vanilla), each with how many published products carry it. Use for questions like 'which brands do you "
            "have', 'what flavours does protein come in', or to find the right word before search_products."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["brands", "categories", "flavours"]}},
            "required": ["kind"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_knowledge",
        "description": "Search NutriZone's own knowledge base, written by the shop: policies (delivery, payment, returns, originality, coins), promotions, branch notes and usage guidance. Call it for any question about how the shop works, how to take a product type, or anything the product tools don't cover. Its answers are the shop's official wording -- prefer them over general knowledge.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "The customer's question in their own words (any language)."}}, "required": ["query"]},
    },
    {
        "name": "get_customer_profile",
        "description": "The signed-in customer's profile for personal advice: first name, height, weight, age, goal, loyalty tier and coin balance, and products they bought recently. Returns signed_in=false for guests. Use it before recommending when the customer asks for something personal ('what should I take', 'for me'), and never repeat questions the profile already answers.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_category_info",
        "description": "What a catalogue category is about (e.g. whey protein, creatine, omega-3): the shop's description, subcategories and how many products it has. Use for 'what is X / what is the difference between X and Y' questions.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string", "description": "Category name in any language."}}, "required": ["name"]},
    },
    {
        "name": "get_brand_info",
        "description": "A brand the shop sells: its description, country and how many products the shop has from it.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string", "description": "Brand name."}}, "required": ["name"]},
    },
]


class ToolError(Exception):
    """A bad tool call -- returned to the model as an is_error tool_result."""


def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"'{value}' is not a valid product id -- use an id from search_products.") from exc


def _int(value, name: str, lo: int, hi: int, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float) or not lo <= value <= hi:
        raise ToolError(f"{name} must be a whole number between {lo} and {hi}.")
    return int(value)


def _money(v) -> int | None:
    return int(Decimal(str(v))) if v not in (None, "") else None


def _clip(text, limit: int = TEXT_LIMIT) -> str:
    text = re.sub(r"\n{3,}", "\n\n", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _names(model, ids, locale: str) -> dict:
    """{id: localized name} for brands / categories (uz fallback)."""
    from apps.products.infrastructure import models as orm

    trans = orm.BrandTranslation if model == "brand" else orm.CategoryTranslation
    key = "brand_id" if model == "brand" else "category_id"
    out: dict = {}
    for row in trans.objects.filter(**{f"{key}__in": [i for i in ids if i]}).values(key, "locale_code", "name"):
        cur = out.get(row[key])
        if cur is None or row["locale_code"] == locale or (row["locale_code"] == "uz" and cur[0] != locale):
            out[row[key]] = (row["locale_code"], row["name"])
    return {k: v[1] for k, v in out.items()}


def _stock(variant_ids) -> dict:
    from apps.stores.infrastructure import availability

    return availability.sellable(list(variant_ids))


def cards(product_ids, locale: str) -> list[dict]:
    """The storefront card for each published product (order kept): what the chat UI renders and add-to-cart uses."""
    from apps.products.infrastructure import models as orm
    from apps.products.infrastructure.selectors import (
        _bulk_default_variant_ids,
        _bulk_default_variant_prices,
        _bulk_rating_summary,
        _product_card,
    )

    ids = list(product_ids)
    rows = {r.id: r for r in orm.Product.objects.filter(id__in=ids, status="published").prefetch_related("translations", "media", "variants")}
    ordered = [rows[i] for i in ids if i in rows]
    variants = _bulk_default_variant_ids(ordered)
    prices = _bulk_default_variant_prices(ordered)
    ratings = _bulk_rating_summary([r.id for r in ordered])
    all_variants = {r.id: [v.id for v in sorted(r.variants.all(), key=lambda v: (not v.is_default, v.created_at)) if v.status == "active"] for r in ordered}
    stock = _stock([v for vs in all_variants.values() for v in vs])
    brands = _names("brand", [r.brand_id for r in ordered], locale)
    out = []
    for r in ordered:
        c = _product_card(r, locale=locale, price_info=prices.get(r.id), rating_info=ratings.get(str(r.id)), default_variant_id=variants.get(r.id))
        # add-to-cart needs a variant that can be bought: the default one if it has stock, else the first that has
        buyable = next((v for v in all_variants.get(r.id, []) if stock.get(v, 0) > 0), None)
        if buyable is not None:
            variants[r.id] = buyable
        units = stock.get(variants.get(r.id), 0)
        out.append({
            "id": str(r.id), "slug": c.get("slug"), "name": c.get("name"), "brand": brands.get(r.brand_id, ""), "image": c.get("primary_image_path"),
            "price": c.get("price"), "compare_at_price": c.get("compare_at_price"), "discount_percent": c.get("discount_percent"), "currency": c.get("currency") or "UZS",
            "rating": c.get("rating_average"), "rating_count": c.get("rating_count") or 0, "variant_id": str(variants.get(r.id) or ""), "in_stock": units > 0,
        })
    return out


# ---------------------------------------------------------------- tool functions (sync: called through sync_to_async)


def search_products(args: dict, locale: str) -> dict:
    from apps.products.infrastructure.selectors import DjangoProductSearchBackend

    query = str(args.get("query") or "").strip()[:120]
    goal = args.get("goal")
    if goal is not None and goal not in goal_book.GOALS:
        raise ToolError(f"goal must be one of {', '.join(goal_book.GOALS)}.")
    limit = _int(args.get("limit"), "limit", 1, MAX_RESULTS, 6)
    max_price = _int(args.get("max_price"), "max_price", 1, 1_000_000_000)
    filters: dict = {}
    if goal:
        filters["goals"] = [goal]
    if max_price:
        filters["price"] = {"lte": str(max_price)}
    if args.get("in_stock_only", True) is not False:
        filters["in_stock"] = True
    page = DjangoProductSearchBackend().search(query, filters, 1, limit, "relevance" if query else "-popularity", locale)
    rows = page["results"]
    brands = _names("brand", [_safe_uuid(r.get("brand_id")) for r in rows], locale)
    categories = _names("category", [_safe_uuid(r.get("category_id")) for r in rows], locale)
    stock = _stock([_safe_uuid(r.get("default_variant_id")) for r in rows])
    goals = _goal_map([r["id"] for r in rows])
    return {
        "total_found": page["total_count"],
        "products": [{
            "id": str(r["id"]), "name": r.get("name"), "brand": brands.get(_safe_uuid(r.get("brand_id")), ""),
            "category": categories.get(_safe_uuid(r.get("category_id")), ""), "price_uzs": _money(r.get("price")),
            "old_price_uzs": _money(r.get("compare_at_price")), "discount_percent": r.get("discount_percent"),
            "in_stock": stock.get(_safe_uuid(r.get("default_variant_id")), 0) > 0, "rating": r.get("rating_average"), "reviews": r.get("rating_count") or 0,
            "goals": [goal_book.label(g, locale) for g in goals.get(str(r["id"]), [])],
        } for r in rows],
        "note": "" if rows else "Nothing matched. Try other words, drop the price limit, or browse by goal.",
    }


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _goal_map(product_ids) -> dict:
    from apps.products.infrastructure import models as orm

    return {str(pid): goal_book.clean(g) for pid, g in orm.Product.objects.filter(id__in=product_ids).values_list("id", "goals")}


def get_product_details(args: dict, locale: str) -> dict:
    from apps.products.infrastructure.selectors import ProductDetailSelector
    from apps.stores.infrastructure import availability

    pid = _uuid(args.get("product_id"))
    d = ProductDetailSelector().get_by_id(pid, locale)
    if d is None:
        raise ToolError("No published product with this id.")
    variants = d.get("variants") or []
    vids = [_safe_uuid(v.get("id")) for v in variants]
    stock = _stock(vids)
    where = availability.branches([v for v in vids if v])
    branches: dict = {}
    for v in vids:
        for b in where.get(v, []):
            if b["available_quantity"] > 0:
                branches[b["name"]] = b.get("address") or b.get("district") or ""
    nutrition = {k: v for k, v in (d.get("nutrition") or {}).items() if v not in (None, "")}
    return {
        "id": str(pid), "name": d.get("name"), "brand": _names("brand", [_safe_uuid(d.get("brand_id"))], locale).get(_safe_uuid(d.get("brand_id")), ""),
        "price_uzs": _money(d.get("price")), "old_price_uzs": _money(d.get("compare_at_price")), "rating": d.get("rating_average"), "reviews": d.get("rating_count") or 0,
        "goals": [goal_book.label(g, locale) for g in goal_book.clean(d.get("goals"))],
        "description": _clip(d.get("description")), "directions": _clip(d.get("directions"), 600), "warnings": _clip(d.get("warnings"), 600),
        "supplement_facts": _clip(d.get("supplement_facts"), 800) if isinstance(d.get("supplement_facts"), str) else d.get("supplement_facts"),
        "nutrition": nutrition,
        "flavours": [f.get("name") for f in d.get("flavours") or [] if isinstance(f, dict) and f.get("name")],
        "variants": [{
            "size": f"{v.get('weight_value'):g} {v.get('weight_unit')}" if v.get("weight_value") else "", "sku": v.get("sku"),
            "price_uzs": _money(v.get("price")), "in_stock": stock.get(_safe_uuid(v.get("id")), 0) > 0,
        } for v in variants if v.get("status", "active") == "active"],
        "branches_with_stock": [{"name": n, "address": a} for n, a in list(branches.items())[:6]],
    }


def _norm_place(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(ch for ch in text if ch.isalnum())
    # common Latin/Russian spellings of the same place
    for a, b in (("tashkent", "toshkent"), ("ташкент", "toshkent"), ("samarkand", "samarqand"), ("самарканд", "samarqand"),
                 ("andijan", "andijon"), ("андижан", "andijon"), ("termez", "termiz"), ("термиз", "termiz"), ("chirchik", "chirchiq"),
                 ("чирчик", "chirchiq"), ("chilanzar", "chilonzor"), ("чиланзар", "chilonzor"), ("yunusabad", "yunusobod"),
                 ("юнусабад", "yunusobod"), ("sergeli", "sergeli"), ("сергели", "sergeli"), ("almazar", "olmazor"), ("алмазар", "olmazor")):
        text = text.replace(a, b)
    return text


def _distance_km(lat1, lon1, lat2, lon2) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def get_store_info(args: dict, locale: str) -> dict:
    from apps.stores.infrastructure.models import Store

    lat, lon = args.get("latitude"), args.get("longitude")
    near = isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and -90 <= lat <= 90 and -180 <= lon <= 180
    place = _norm_place(args.get("city") or "")
    out = []
    for s in Store.objects.filter(kind="store", status="active").order_by("name")[:60]:
        if place and place not in _norm_place(f"{s.city} {s.district} {s.name} {s.address}"):
            continue
        hours = {day: ("closed" if h.get("closed") else f"{h['open']}-{h['close']}") for day, h in (s.working_hours or {}).items()
                 if isinstance(h, dict) and (h.get("closed") or (h.get("open") and h.get("close")))}
        row = {"name": s.name, "address": ", ".join(x for x in (s.city, s.district, s.address) if x), "landmark": s.landmark,
               "phones": s.phone_numbers[:2], "hours": hours, "pickup": s.pickup_enabled}
        if s.latitude is not None and s.longitude is not None:
            row["map_url"] = f"https://maps.google.com/?q={s.latitude:.6f},{s.longitude:.6f}"
            if near:
                row["distance_km"] = round(_distance_km(lat, lon, s.latitude, s.longitude), 1)
        out.append(row)
    if near:
        out.sort(key=lambda r: r.get("distance_km", 1e9))
        out = out[:5]
    contact = {}
    try:
        from apps.platform.infrastructure.models import SiteSettings

        site = SiteSettings.objects.first()
        if site is not None:
            contact = {k: getattr(site, k) for k in ("support_phone", "support_email", "address", "working_hours", "telegram_username", "telegram_channel_url", "instagram_url") if getattr(site, k, "")}
    except Exception:  # noqa: BLE001 - contact details are a nice-to-have
        contact = {}
    result = {"branches": out, "contact": contact, "online": "Delivery across Uzbekistan from the website; payment by Payme, Click, Uzum, card or cash on delivery."}
    if place and not out:
        result["note"] = "No branch in that place -- offer delivery or the closest city's branches."
    return result


def browse_catalog(args: dict, locale: str) -> dict:
    from django.db.models import Count, Q

    from apps.products.infrastructure import models as orm

    kind = args.get("kind")
    published = Q(products__status="published")
    if kind == "brands":
        rows = orm.Brand.objects.annotate(n=Count("products", filter=published, distinct=True)).filter(n__gt=0).values_list("id", "n")
        names = _names("brand", [r[0] for r in rows], locale)
    elif kind == "categories":
        rows = orm.Category.objects.annotate(n=Count("products", filter=published, distinct=True)).filter(n__gt=0).values_list("id", "n")
        names = _names("category", [r[0] for r in rows], locale)
    elif kind == "flavours":
        rows = orm.Flavour.objects.filter(is_active=True).annotate(n=Count("products", filter=published, distinct=True)).values_list("id", "n")
        # the customer's language first, then the name printed on the tub (en), then anything
        rank = {locale: 0, "en": 1}
        best: dict = {}
        for t in orm.FlavourTranslation.objects.filter(flavour_id__in=[r[0] for r in rows]).values("flavour_id", "locale_code", "name"):
            r = rank.get(t["locale_code"], 2)
            if t["flavour_id"] not in best or r < best[t["flavour_id"]][0]:
                best[t["flavour_id"]] = (r, t["name"])
        names = {k: v[1] for k, v in best.items()}
    else:
        raise ToolError("kind must be brands, categories or flavours.")
    items = sorted(({"name": names.get(i, ""), "products": n} for i, n in rows if names.get(i)), key=lambda r: (-r["products"], r["name"]))
    return {"kind": kind, "items": items[:80], "total": len(items)}


def show_products(args: dict, locale: str) -> dict:
    raw = args.get("product_ids")
    if not isinstance(raw, list) or not raw:
        raise ToolError("product_ids must be a non-empty list of ids.")
    ids = []
    for value in raw[:MAX_SHOW]:
        pid = _safe_uuid(value)
        if pid is not None and pid not in ids:
            ids.append(pid)
    shown = cards(ids, locale)
    if not shown:
        raise ToolError("None of these ids is a published product. Use ids from search_products.")
    return {"shown": [c["name"] for c in shown], "cards": shown}



def search_knowledge(args: dict, locale: str) -> dict:
    from apps.assistant.infrastructure import knowledge

    q = _clip(args.get("query") or "", 300).strip()
    if not q:
        raise ToolError("query is required.")
    hits = knowledge.search(q, limit=3)
    knowledge.mark_used([h.entry for h in hits])
    return {"results": [{"title": h.entry.title, "topic": h.entry.topic, "answer": _clip(h.entry.answer(locale), 1500)} for h in hits],
            "note": "" if hits else "Nothing in the shop's knowledge base matches; answer from the product tools or general guidance, or suggest contacting the shop."}


def get_customer_profile(args: dict, locale: str) -> dict:
    from apps.assistant.infrastructure.advisor.engine import account_facts
    from apps.identity.infrastructure.models import User

    cid = CURRENT_CUSTOMER.get()
    user = User.objects.filter(pk=cid).only("id", "full_name").first() if cid else None
    if user is None:
        return {"signed_in": False}
    out = {"signed_in": True, "first_name": (user.full_name or "").split(" ")[0], **account_facts(user.id)}
    try:
        from apps.loyalty.infrastructure import services as loyalty
        from apps.loyalty.infrastructure.models import Wallet

        wallet = Wallet.objects.filter(user_id=user.id).only("balance").first()
        out["coins"] = int(wallet.balance) if wallet else 0
        spend, _n = loyalty.qualifying_spend(user.id)
        rule = loyalty.tier_for(user.id, spend, loyalty.active_tier_rules())
        if rule is not None:
            out["tier"] = {"name": getattr(rule, "name", ""), "cashback_percent": float(getattr(rule, "percent", 0) or 0)}
    except Exception:  # noqa: BLE001 -- loyalty is a nice-to-have in the profile
        pass
    out["recent_purchases"] = _recent_purchases(user.id, locale)
    return out


def _recent_purchases(customer_id, locale: str) -> list[str]:
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure.models import SaleLineItemModel
    from apps.stores.infrastructure.stock_service import variant_infos

    vids = list(OrderLineItemModel.objects.filter(order__customer_id=customer_id, order__status__in=("delivered", "completed"), status="active")
                .order_by("-order__placed_at").values_list("product_variant_id", flat=True)[:8])
    vids += list(SaleLineItemModel.objects.filter(sale__customer_id=customer_id, sale__status="completed", product_variant_id__isnull=False)
                 .order_by("-sale__completed_at").values_list("product_variant_id", flat=True)[:8])
    infos = variant_infos(set(vids), locale)
    seen, out = set(), []
    for v in vids:
        i = infos.get(v)
        if i and i.name not in seen:
            seen.add(i.name)
            out.append(f"{i.name} ({i.size})" if i.size else i.name)
    return out[:6]


def _find(trans_model, key: str, name: str):
    name = (name or "").strip()
    if not name:
        raise ToolError("name is required.")
    row = trans_model.objects.filter(name__iexact=name).values(key).first() or trans_model.objects.filter(name__icontains=name).values(key).first()
    return row[key] if row else None


def _text(trans_model, key: str, obj_id, locale: str) -> tuple[str, str]:
    rows = {r["locale_code"]: r for r in trans_model.objects.filter(**{key: obj_id}).values("locale_code", "name", "description")}
    r = rows.get(locale) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), {"name": "", "description": ""})
    return r["name"], _clip(r.get("description") or "", 1500)


def get_category_info(args: dict, locale: str) -> dict:
    from apps.products.infrastructure import models as orm

    cid = _find(orm.CategoryTranslation, "category_id", args.get("name"))
    if cid is None:
        return {"found": False}
    name, desc = _text(orm.CategoryTranslation, "category_id", cid, locale)
    children = list(orm.Category.objects.filter(parent_id=cid, deleted_at__isnull=True).values_list("id", flat=True))
    kids = _names("category", children, locale)
    count = orm.Product.objects.filter(category_id__in=[cid, *children], status="published", deleted_at__isnull=True).count()
    return {"found": True, "name": name, "description": desc, "subcategories": list(kids.values())[:15], "products": count}


def get_brand_info(args: dict, locale: str) -> dict:
    from apps.products.infrastructure import models as orm

    bid = _find(orm.BrandTranslation, "brand_id", args.get("name"))
    if bid is None:
        return {"found": False}
    name, desc = _text(orm.BrandTranslation, "brand_id", bid, locale)
    brand = orm.Brand.objects.filter(pk=bid).select_related("country").first()
    count = orm.Product.objects.filter(brand_id=bid, status="published", deleted_at__isnull=True).count()
    return {"found": True, "name": name, "description": desc, "country": str(brand.country) if brand and brand.country else "", "products": count}

HANDLERS = {
    "search_products": search_products, "get_product_details": get_product_details, "show_products": show_products,
    "get_store_info": get_store_info, "browse_catalog": browse_catalog, "search_knowledge": search_knowledge,
    "get_customer_profile": get_customer_profile, "get_category_info": get_category_info, "get_brand_info": get_brand_info,
}


def run(name: str, args, locale: str) -> tuple[dict, bool]:
    """(result, is_error) for one tool call."""
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool {name}."}, True
    if not isinstance(args, dict):
        return {"error": "Tool input must be an object."}, True
    try:
        return handler(args, locale), False
    except ToolError as exc:
        return {"error": str(exc)}, True


def as_text(result: dict) -> str:
    """Tool results go back to the model as compact JSON (cards for the UI are stripped from show_products' result)."""
    data = {k: v for k, v in result.items() if k != "cards"}
    return json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))
