"""
Product grouping: products of one brand that differ only by size and flavour become ONE product family with one
variant per size x flavour -- "Olimp Complex Whey 2.27 kg Chocolate", "… 1.8 kg Coconut Cream", "… 700 g Strawberry"
→ "Olimp Complex Whey" with four variants. The shopper then picks size and flavour on one page.

* `group_suggestions()` -- candidate groups: same brand + the same name once sizes ("2.27 kg", "5 lb", "60 caps")
  and known flavour names are taken out.
* `preview_group(ids)` -- what grouping would do: the family name, and each variant's size and flavour (detected from
  the product's flavour tag, else its name; the editor can correct it).
* `merge_products(...)` -- does it, in one transaction: variants (with their SKU, barcode, prices, stock, sales history)
  move to the family product, photos move with them, reviews / wishlists / POS sales history follow; the emptied
  products are archived with `merged_into`, so their old links redirect to the right variant.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.products.infrastructure import models as orm

# ------------------------------------------------------------------------------------------------ name parsing

_UNITS = {
    "kg": "kg", "кг": "kg", "g": "g", "gr": "g", "gram": "g", "grams": "g", "г": "g", "гр": "g",
    "lb": "lb", "lbs": "lb", "фунт": "lb", "фунта": "lb", "фунтов": "lb", "oz": "oz",
    "ml": "ml", "мл": "ml", "l": "l", "л": "l", "ltr": "l",
    "caps": "capsule", "cap": "capsule", "capsules": "capsule", "kapsula": "capsule", "капс": "capsule", "капсул": "capsule",
    "tabs": "tablet", "tab": "tablet", "tablets": "tablet", "tabletka": "tablet", "таб": "tablet", "таблеток": "tablet",
    "softgels": "capsule", "softgel": "capsule", "gummies": "gummy", "chewables": "chewable",
}
_SIZE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True)) + r")\.?(?![\w])", re.I)
_SERVINGS = re.compile(r"(?<![\w])\d+\s*(?:servings?|serv|порц\w*|porsiya)\b", re.I)
_EDGES = re.compile(r"^[\s\-–—,/|:;·•+(]+|[\s\-–—,/|:;·•+)]+$")


def parse_size(text: str) -> tuple[float, str] | None:
    """(value, WeightUnit value) from a product name -- "2.27 kg", "700g", "5 lb" (→ 2.27 kg), "60 caps"."""
    m = _SIZE.search(text or "")
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    unit = _UNITS[m.group(2).lower()]
    if unit == "lb":
        return round(value * 0.45359237, 2), "kg"
    if unit == "oz":
        return round(value * 28.3495), "g"
    return value, unit


def _flavour_index() -> list[tuple[str, int]]:
    """
    (lower-case name, flavour id) for every flavour name in every language, longest first -- the names in the
    database plus the standard names of the reference list (reference_catalog.FLAVOURS), so a flavour whose name an
    editor changed is still recognised in product names.
    """
    from apps.products.infrastructure.reference_catalog import FLAVOURS

    out: dict[str, uuid.UUID] = {}
    by_slug = dict(orm.Flavour.objects.values_list("slug", "id"))
    for slug, en, uz, ru, _color in FLAVOURS:
        if slug in by_slug:
            for name in (en, uz, ru):
                out[name.lower()] = by_slug[slug]
    rows = orm.FlavourTranslation.objects.filter(flavour__is_deleted=False).values_list("name", "flavour_id")
    out.update({(n or "").strip().lower(): fid for n, fid in rows if n and len(n.strip()) >= 3})
    return sorted(out.items(), key=lambda kv: -len(kv[0]))


def _find_flavour(text: str, index) -> tuple[uuid.UUID | None, str]:
    low = f" {(text or '').lower()} "
    for name, fid in index:
        if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", low):
            return fid, name
    return None, ""


def base_name(name: str, index=None) -> str:
    """The family name: sizes, serving counts and flavour names removed -- "Olimp Complex Whey 2.27 kg Chocolate" → "Olimp Complex Whey"."""
    text = _SIZE.sub(" ", name or "")
    text = _SERVINGS.sub(" ", text)
    for flavour, _fid in (index if index is not None else _flavour_index()):
        text = re.sub(rf"(?<![\w]){re.escape(flavour)}(?![\w])", " ", text, flags=re.I)
    text = re.sub(r"\(\s*\)|\[\s*\]", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    previous = None
    while previous != text:
        previous, text = text, _EDGES.sub("", text).strip()
    return text


def _names(product) -> dict[str, str]:
    return {t.locale_code: t.name for t in product.translations.all()}


def _main_name(product) -> str:
    n = _names(product)
    return n.get("uz") or n.get("en") or n.get("ru") or next(iter(n.values()), str(product.id))


def detect_flavour(product, index=None) -> uuid.UUID | None:
    """The product's single flavour tag; else a flavour name found in its name (any language)."""
    links = list(product.flavour_links.all())
    if len(links) == 1:
        return links[0].flavour_id
    index = index if index is not None else _flavour_index()
    for text in _names(product).values():
        fid, _ = _find_flavour(text, index)
        if fid:
            return fid
    return None


# ------------------------------------------------------------------------------------------------ suggestions


def _candidates():
    return (
        orm.Product.objects.filter(merged_into__isnull=True)
        .exclude(status="archived")
        .select_related("brand")
        .prefetch_related("translations", "brand__translations", "flavour_links", "variants__flavour__translations")
    )


def group_suggestions(limit: int = 200) -> list[dict]:
    """[{brand, name, products: [...]}] -- 2+ products of one brand sharing a family name."""
    index = _flavour_index()
    buckets: dict[tuple, list] = defaultdict(list)
    for p in _candidates():
        if p.brand_id is None:
            continue
        key = (p.brand_id, re.sub(r"[^\w]+", " ", base_name(_main_name(p), index).lower()).strip())
        if key[1]:
            buckets[key].append(p)
    groups = []
    for (brand_id, _key), products in buckets.items():
        if len(products) < 2:
            continue
        products.sort(key=lambda p: (-(p.variants.count()), p.created_at))
        brand = products[0].brand
        brand_names = {t.locale_code: t.name for t in brand.translations.all()} if brand else {}
        groups.append({
            "brand": brand_names.get("uz") or brand_names.get("en") or next(iter(brand_names.values()), ""),
            "name": base_name(_main_name(products[0]), index),
            "product_ids": [str(p.id) for p in products],
            "products": [_main_name(p) for p in products],
            "variant_count": sum(p.variants.count() for p in products),
        })
    groups.sort(key=lambda g: (-len(g["product_ids"]), g["brand"], g["name"]))
    return groups[:limit]


# ------------------------------------------------------------------------------------------------ preview + merge


@dataclass
class VariantPlan:
    variant_id: str
    product_id: str
    product_name: str
    sku: str
    size_value: float | None
    size_unit: str | None
    size_from_name: bool
    flavour_id: str | None
    flavour_name: str
    flavour_detected: bool


@dataclass
class GroupPreview:
    target_id: str
    names: dict[str, str]
    variants: list[VariantPlan] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)  # "2.27 kg · Chocolate" appearing twice
    missing_flavour: int = 0
    brands: int = 1


def _flavour_name(fid, locale="uz") -> str:
    if not fid:
        return ""
    rows = dict(orm.FlavourTranslation.objects.filter(flavour_id=fid).values_list("locale_code", "name"))
    return rows.get(locale) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), "")


def preview_group(product_ids: list, target_id=None) -> GroupPreview:
    products = list(
        orm.Product.objects.filter(id__in=product_ids)
        .prefetch_related("translations", "flavour_links", "variants__flavour__translations")
    )
    if len(products) < 2:
        raise ValueError("Guruhlash uchun kamida 2 ta mahsulot tanlang.")
    products.sort(key=lambda p: (str(p.id) != str(target_id), -p.variants.count(), p.created_at))
    target = products[0]
    index = _flavour_index()
    names = {}
    for p in products:
        for loc, n in _names(p).items():
            names.setdefault(loc, base_name(n, index))
    preview = GroupPreview(target_id=str(target.id), names=names, brands=len({p.brand_id for p in products}))
    seen = defaultdict(int)
    for p in products:
        product_flavour = detect_flavour(p, index)
        main = _main_name(p)
        size_guess = parse_size(main)
        for v in p.variants.all():
            fid = v.flavour_id or product_flavour
            value, unit, from_name = v.weight_value, v.weight_unit, False
            if not value and size_guess and len(p.variants.all()) == 1:
                value, unit, from_name = size_guess[0], size_guess[1], True
            plan = VariantPlan(
                variant_id=str(v.id), product_id=str(p.id), product_name=main, sku=v.sku,
                size_value=value, size_unit=unit if value else None, size_from_name=from_name,
                flavour_id=str(fid) if fid else None, flavour_name=_flavour_name(fid), flavour_detected=bool(fid and not v.flavour_id),
            )
            preview.variants.append(plan)
            seen[(value, unit, fid)] += 1
            if not fid:
                preview.missing_flavour += 1
    for (value, unit, fid), n in seen.items():
        if n > 1:
            size = f"{value:g} {unit}" if value else "—"
            preview.duplicates.append(f"{size} · {_flavour_name(fid) or '—'}")
    return preview


def _unique_slug(locale: str, base: str, own_product_id) -> str:
    from apps.geo.infrastructure.reference_data import slugify_uz

    slug = (slugify_uz(base) or "mahsulot")[:200]
    candidate, n = slug, 2
    while orm.ProductTranslation.objects.filter(locale_code=locale, slug=candidate).exclude(product_id=own_product_id).exists():
        candidate, n = f"{slug}-{n}", n + 1
    return candidate


def sync_product_flavours(product) -> None:
    """Product.flavours = the flavours its variants carry (catalog filters and search read the product-level tags)."""
    wanted = set(product.variants.filter(flavour__isnull=False).values_list("flavour_id", flat=True))
    if not wanted:
        return
    current = set(orm.ProductFlavour.objects.filter(product=product).values_list("flavour_id", flat=True))
    orm.ProductFlavour.objects.filter(product=product).exclude(flavour_id__in=wanted).delete()
    orm.ProductFlavour.objects.bulk_create([orm.ProductFlavour(product=product, flavour_id=f) for f in wanted - current])


def merge_products(target_id, product_ids: list, *, names: dict | None = None, variant_flavours: dict | None = None,
                   variant_sizes: dict | None = None) -> dict:
    """
    Groups `product_ids` into `target_id`. `variant_flavours` / `variant_sizes` ({variant id: flavour id / (value, unit)})
    carry the editor's corrections from the preview; anything not given is detected as in `preview_group`.
    """
    variant_flavours = {str(k): v for k, v in (variant_flavours or {}).items()}
    variant_sizes = {str(k): v for k, v in (variant_sizes or {}).items()}
    preview = preview_group(product_ids, target_id)
    plans = {p.variant_id: p for p in preview.variants}
    target_uuid = uuid.UUID(preview.target_id)
    moved_products = 0
    with transaction.atomic():
        target = orm.Product.objects.select_for_update().get(id=target_uuid)
        sources = list(orm.Product.objects.filter(id__in=[i for i in product_ids if str(i) != str(target_uuid)]).prefetch_related("variants"))
        all_products = [target, *sources]
        # variants: flavour + size, then onto the family
        for product in all_products:
            single = list(product.variants.all())
            for v in single:
                plan = plans.get(str(v.id))
                fid = variant_flavours.get(str(v.id)) if str(v.id) in variant_flavours else (plan.flavour_id if plan else None)
                size = variant_sizes.get(str(v.id)) or ((plan.size_value, plan.size_unit) if plan and plan.size_value else None)
                v.flavour_id = uuid.UUID(str(fid)) if fid else None
                if size and size[0]:
                    v.weight_value, v.weight_unit = float(size[0]), size[1]
                if product.id != target.id:
                    v.product_id = target.id
                    v.is_default = False
                v.save()
            if product.id == target.id:
                continue
            # photos follow their variant: a one-variant product's own photos become that variant's photos
            only = single[0] if len(single) == 1 else None
            for m in orm.ProductMedia.objects.filter(product=product):
                if m.variant_id is None and only is not None:
                    m.variant_id = only.id
                m.product_id = target.id
                if m.variant_id is None and m.media_role == "primary":
                    m.media_role = "gallery"
                m.save()
            _move_links(product, target)
            product.merged_into = target
            product.merged_variant_ids = [str(v.id) for v in single]
            product.status = "archived"
            product.is_deleted, product.deleted_at = True, timezone.now()
            product.save()
            moved_products += 1
        # one default variant: the in-stock... simply the first by size, then flavour
        variants = list(orm.ProductVariant.objects.filter(product=target).order_by("weight_value", "created_at"))
        if variants and not any(v.is_default for v in variants):
            orm.ProductVariant.objects.filter(id=variants[0].id).update(is_default=True)
        elif sum(v.is_default for v in variants) > 1:
            keep = next(v for v in variants if v.is_default)
            orm.ProductVariant.objects.filter(product=target, is_default=True).exclude(id=keep.id).update(is_default=False)
        # the family name in every language
        for t in orm.ProductTranslation.objects.filter(product=target):
            new = (names or {}).get(t.locale_code) or preview.names.get(t.locale_code)
            if new and new != t.name:
                t.name = new.strip()
                t.slug = _unique_slug(t.locale_code, t.name, target.id)
                t.save()
        sync_product_flavours(target)
    return {"target_id": str(target.id), "merged": moved_products, "variants": len(plans)}


def _move_links(source, target) -> None:
    from apps.reviews.infrastructure.models import ReviewModel

    ReviewModel.all_objects.filter(product_id=source.id).update(product_id=target.id)
    wished = set(orm.WishlistItem.objects.filter(product=target).values_list("customer_id", flat=True))
    orm.WishlistItem.objects.filter(product=source, customer_id__in=wished).delete()
    orm.WishlistItem.objects.filter(product=source).update(product=target)
    have_tags = set(orm.ProductTag.objects.filter(product=target).values_list("tag_id", flat=True))
    for link in orm.ProductTag.objects.filter(product=source).exclude(tag_id__in=have_tags):
        orm.ProductTag.objects.create(product=target, tag_id=link.tag_id)
    # curated "goes well with" links: never self-links, never duplicates
    recs = orm.ProductRecommendation.all_objects if hasattr(orm.ProductRecommendation, "all_objects") else orm.ProductRecommendation.objects
    recs.filter(product=source).delete()
    recs.filter(product=target, related_product=source).delete()
    already = set(recs.filter(related_product=target).values_list("product_id", flat=True))
    recs.filter(related_product=source, product_id__in=already).delete()
    recs.filter(related_product=source).update(related_product=target)
    try:
        from apps.pos.infrastructure.models import SaleLineItemModel

        SaleLineItemModel.objects.filter(product_id=source.id).update(product_id=target.id)  # sales reports by product
    except Exception:  # noqa: BLE001 -- reporting history is a bonus, never a reason to fail grouping
        pass


def moved_variant_of(old_product_id, target_id) -> str | None:
    old = orm.Product.all_objects.filter(id=old_product_id).values_list("merged_variant_ids", flat=True).first() or []
    alive = set(map(str, orm.ProductVariant.objects.filter(product_id=target_id, id__in=old).values_list("id", flat=True)))
    return next((v for v in old if v in alive), None)
