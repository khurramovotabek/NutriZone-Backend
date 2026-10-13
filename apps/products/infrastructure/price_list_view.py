"""
Price List dashboard -- a dedicated, fast operational page for editing
existing Product pricing directly, without opening each Product's own
change form one at a time. Mirrors
`apps.platform.infrastructure.pos_view`/`inventory_view`'s own
established "custom admin view + JSON API, installed via
admin.site.get_urls()" pattern -- never a second admin framework.

Reuses the exact same `PriceListEntryModel` + `SetPrice` Application
Service (via `apps.products.infrastructure.admin`'s own
`_get_or_create_default_price_list`/pricing helpers, the same ones
`ProductVariantAdminForm` uses) -- never a second, divergent price
write path. Base Price = `cost_price_amount` (internal), Old Price =
`compare_at_price_amount` (marketing strike-through), Price =
`base_price_amount` (real selling price) -- the exact same mapping
Product Edit's own Pricing fields already use.

Real, product-required simplification: each row is a real, distinct
Product (never a fabricated grouping across separate Product records --
that stays explicitly banned, per this page's own prior "no family
grouping" decision). `PriceListEntryModel` itself is still keyed by
product_variant_id, not product_id, so a row's editable price is its
Product's own real *default* variant (`is_default=True`, else the
earliest-created one -- the identical, already-established convention
`ProductAdmin.price_display`/`selectors.py::_bulk_default_variant_ids`
already use). A Product with more than one variant shows a real "×N"
count next to its SKU so an editor knows other variants exist and may
need their own pricing from the Product's own change form -- never
hidden, never silently only-the-default.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.products.infrastructure import models as orm

_PAGE_SIZE = 20
_SORTABLE = {
    "name",
    "-name",
    "base_price",
    "-base_price",
    "old_price",
    "-old_price",
    "price",
    "-price",
    "recent",
    "-recent",
}
_DEFAULT_SORT = "-recent"  # newest-added product first -- Product.created_at is a real, existing field, not a fabricated one


def _bulk_default_variants(product_ids: list) -> dict:
    """
    Same is_default-else-earliest convention as `ProductAdmin.
    get_queryset()`/`selectors.py::_bulk_default_variant_ids` -- one
    bulk query, never per-row. Returns {product_id: ProductVariant}
    for products that have at least one real variant; a product with
    none is simply absent from the result (never a fabricated
    placeholder row -- see `_build_rows`, which skips it).
    """
    if not product_ids:
        return {}
    rows = orm.ProductVariant.objects.filter(product_id__in=product_ids).order_by(
        "product_id", "-is_default", "created_at"
    )
    result: dict = {}
    for v in rows:
        result.setdefault(v.product_id, v)
    return result


def _bulk_stock_by_variant(variant_ids: list) -> dict:
    """
    Sellable stock per variant from the WMS (on hand − reserved at active locations, see
    apps/stores/infrastructure/availability.py) -- the same numbers the warehouse, the POS and the storefront use.
    A variant with no stock row anywhere is genuinely not stock-tracked (absent → "Not tracked", never a fabricated 0).
    The "Low stock" state uses the WMS low-stock line (LOW_STOCK units).
    """
    from apps.stores.infrastructure.availability import sellable
    from apps.stores.infrastructure.warehouse_admin import LOW_STOCK

    return {vid: {"quantity": units, "low_stock_at": LOW_STOCK} for vid, units in sellable(variant_ids).items()}


def _stock_state(stock: int | None, low_stock_at: int | None) -> str:
    if stock is None:
        return "not_tracked"
    if stock == 0:
        return "out"
    if low_stock_at is not None and stock <= low_stock_at:
        return "low"
    return "in"


_STOCK_FILTERS = {"in", "low", "out", "not_tracked"}
_DISCOUNT_FILTERS = {"discounted", "none"}


def _parse_decimal_or_none(raw) -> Decimal | None:
    if not raw:
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _apply_advanced_filters(
    qs,
    *,
    stock_status: str | None,
    discount_filter: str | None,
    price_min: Decimal | None,
    price_max: Decimal | None,
):
    """
    Stock/discount/price-range filtering the existing GET-param query
    string mechanism (brand/category) didn't cover -- resolved the same
    way `_rows_sorted_by_price` already resolves price across the
    pricing bounded context (no real cross-schema FK to filter on in
    SQL), never a new backend endpoint, never a fabricated filter.
    Every check is against each Product's own real *default* variant
    (see `_bulk_default_variants`), matching every other resolution on
    this page.
    """
    if not (stock_status or discount_filter or price_min is not None or price_max is not None):
        return qs

    from apps.pricing.infrastructure.models import PriceListEntryModel

    all_product_ids = list(qs.values_list("id", flat=True))
    default_variant_by_product = _bulk_default_variants(all_product_ids)
    variant_ids = [v.id for v in default_variant_by_product.values()]
    entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids)}
    stock_by_variant = _bulk_stock_by_variant(variant_ids) if stock_status else {}

    keep_ids = []
    for product_id, variant in default_variant_by_product.items():
        entry = entries.get(variant.id)
        price = entry.base_price_amount if entry else None
        old_price = entry.compare_at_price_amount if entry else None

        if price_min is not None and (price is None or price < price_min):
            continue
        if price_max is not None and (price is None or price > price_max):
            continue

        if discount_filter:
            has_discount = old_price is not None and price is not None and old_price > price
            if discount_filter == "discounted" and not has_discount:
                continue
            if discount_filter == "none" and has_discount:
                continue

        if stock_status:
            info = stock_by_variant.get(variant.id)
            stock = info["quantity"] if info else None
            state = _stock_state(stock, info["low_stock_at"] if info else None)
            if stock_status != state:
                continue

        keep_ids.append(product_id)

    return qs.filter(id__in=keep_ids)


def _bulk_row_images(variants: list) -> dict:
    """
    Real, existing media pipeline (`ProductMedia`, the same table
    `ProductAdmin.thumbnail_display`/`_direct_thumbnail_html` already
    render) -- one bulk query for the whole page, never one per row.
    Each row's image is resolved from its Product's own default
    variant: a variant-level primary photo (`ProductMedia.variant_id`
    set) if that specific variant has one, otherwise the product-level
    primary photo (`variant_id IS NULL`) shared by the whole Product. A
    record with neither renders `_direct_thumbnail_html`'s own real
    empty-state icon, never a fabricated placeholder image.
    """
    from django.db.models import Q

    variant_ids = {v.id for v in variants}
    product_ids = {v.product_id for v in variants}
    rows = orm.ProductMedia.objects.filter(
        Q(variant_id__in=variant_ids) | Q(product_id__in=product_ids, variant__isnull=True),
        media_role="primary",
    ).order_by("sort_order")

    by_variant: dict = {}
    by_product: dict = {}
    for row in rows:
        if row.variant_id is not None:
            by_variant.setdefault(row.variant_id, (row.storage_path, row.thumbnail_paths))
        else:
            by_product.setdefault(row.product_id, (row.storage_path, row.thumbnail_paths))

    return {v.id: by_variant.get(v.id) or by_product.get(v.product_id, ("", {})) for v in variants}


def _bulk_flavor_names(variants: list) -> dict:
    """Flavour is a Product-level tag (see domain/aggregates.py::Flavour's docstring), not a per-variant attribute -- resolved via each variant's own product_id, then joined (", ") when a product carries more than one flavour tag, matching this file's own established descriptor convention."""
    from apps.products.infrastructure.admin import _display_name as _dn

    product_ids = {v.product_id for v in variants}
    links = orm.ProductFlavour.objects.filter(product_id__in=product_ids).select_related("flavour").prefetch_related("flavour__translations")

    names_by_product: dict = {}
    for link in links:
        names_by_product.setdefault(link.product_id, []).append(_dn(link.flavour.translations.all(), link.flavour_id))

    return {v.id: ", ".join(names_by_product[v.product_id]) for v in variants if v.product_id in names_by_product}


def _bulk_variant_counts(product_ids: list) -> dict:
    """How many real, sellable ProductVariant rows each Product actually has -- rendered as a real "×N" note next to a row's SKU when > 1, never hidden. A Product with exactly one variant (the ordinary case in this catalog) shows no note at all."""
    if not product_ids:
        return {}
    rows = orm.Product.objects.filter(id__in=product_ids).annotate(_vc=Count("variants", distinct=True)).values("id", "_vc")
    return {row["id"]: row["_vc"] for row in rows}


def _rows_sorted_by_name(qs, sort: str, page: int):
    """
    Real, closed gap (found live, verified by hand): the previous
    `order_by("translations__name")` was a plain SQL JOIN against
    `translations` (one product has up to 3 rows there -- uz/ru/en),
    never de-duplicated -- every product silently rendered once per
    translation row (a product with all 3 locales showed up 3 times).
    A `Subquery`/`Coalesce` annotation resolves to exactly one name per
    product (no join multiplication), matching `_display_name`'s own
    "uz" -> "en" -> whatever exists locale fallback order, never a
    second, divergent name-resolution rule.
    """
    from apps.pricing.infrastructure.models import PriceListEntryModel

    def _translation_name(locale: str | None):
        translations = orm.ProductTranslation.objects.filter(product_id=OuterRef("id"))
        if locale is not None:
            translations = translations.filter(locale_code=locale)
        return Subquery(translations.order_by("locale_code").values("name")[:1])

    qs = qs.annotate(
        _sort_name=Coalesce(_translation_name("uz"), _translation_name("en"), _translation_name(None))
    )
    qs = qs.order_by("-_sort_name" if sort.startswith("-") else "_sort_name")
    total = qs.count()
    start = (page - 1) * _PAGE_SIZE
    page_products = list(qs[start : start + _PAGE_SIZE].prefetch_related("translations"))
    default_variant_by_product = _bulk_default_variants([p.id for p in page_products])
    variant_ids = [v.id for v in default_variant_by_product.values()]
    prices_by_variant = {
        e.product_variant_id: e
        for e in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).select_related("price_list")
    }
    return page_products, default_variant_by_product, prices_by_variant, total


def _rows_sorted_by_recent(qs, sort: str, page: int):
    """
    Default view order: newest-added product first. `created_at` lives
    directly on `Product`, so this is a plain, real field order --
    never a fabricated "recently added" signal.
    """
    from apps.pricing.infrastructure.models import PriceListEntryModel

    qs = qs.order_by("created_at" if sort == "recent" else "-created_at")
    total = qs.count()
    start = (page - 1) * _PAGE_SIZE
    page_products = list(qs[start : start + _PAGE_SIZE].prefetch_related("translations"))
    default_variant_by_product = _bulk_default_variants([p.id for p in page_products])
    variant_ids = [v.id for v in default_variant_by_product.values()]
    prices_by_variant = {
        e.product_variant_id: e
        for e in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).select_related("price_list")
    }
    return page_products, default_variant_by_product, prices_by_variant, total


def _rows_sorted_by_price(qs, sort: str, page: int):
    """
    No cross-schema ORDER BY is possible, so this resolves every
    matching Product's own default variant + that variant's real price
    once (a single, bounded bulk query -- never per-row), sorts that
    small id list in Python, then only fetches full Product/translation
    data for the one page actually being displayed. Reasonable at this
    admin tool's real scale (a boutique catalog, not a marketplace); it
    does not load full product rows for the whole catalog.
    """
    from apps.pricing.infrastructure.models import PriceListEntryModel

    all_product_ids = list(qs.values_list("id", flat=True))
    default_variant_by_product = _bulk_default_variants(all_product_ids)
    # NOTE: UI "Price" reads the same base_price_amount column UI "Base
    # Price (cost)" writes to a *different* column (cost_price_amount).
    ui_field_to_column = {
        "base_price": "cost_price_amount",
        "old_price": "compare_at_price_amount",
        "price": "base_price_amount",
    }
    column = ui_field_to_column[sort.lstrip("-")]
    reverse = sort.startswith("-")

    variant_ids = [v.id for v in default_variant_by_product.values()]
    entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids)}

    def _sort_key(product_id):
        variant = default_variant_by_product.get(product_id)
        entry = entries.get(variant.id) if variant else None
        value = getattr(entry, column, None) if entry else None
        return (value is None, value if value is not None else Decimal(0))

    all_product_ids.sort(key=_sort_key, reverse=reverse)
    total = len(all_product_ids)
    start = (page - 1) * _PAGE_SIZE
    page_ids = all_product_ids[start : start + _PAGE_SIZE]
    rows_by_id = {p.id: p for p in qs.filter(id__in=page_ids).prefetch_related("translations")}
    page_products = [rows_by_id[pid] for pid in page_ids if pid in rows_by_id]
    return page_products, default_variant_by_product, entries, total


_SORT_HANDLERS = {"name": _rows_sorted_by_name, "recent": _rows_sorted_by_recent}


def _build_rows(page_products, default_variant_by_product, prices_by_variant, variant_count_by_product) -> list:
    """
    Real, product-required simplification: this page's own unit is now
    a Product, not a ProductVariant -- a Product with several variants
    (different Weight/Package) is edited here via its own real default
    variant's price, with a real "×N" note (see `_bulk_variant_counts`)
    disclosing that other variants exist rather than silently only
    showing/editing one of several. This draws no distinction between
    two separately-created Product rows that happen to share a name
    (e.g. two genuinely independent "Gold Standard Whey" records) --
    each still renders as its own, fully independent row, exactly as
    this page's own prior explicit "no family grouping" decision
    requires; only the variant-vs-product row *granularity* changed.
    """
    from apps.products.infrastructure.admin import _direct_thumbnail_html, _display_name

    default_variants = [default_variant_by_product[p.id] for p in page_products if p.id in default_variant_by_product]
    stock_by_variant = _bulk_stock_by_variant([v.id for v in default_variants])
    image_by_variant = _bulk_row_images(default_variants)
    flavor_by_variant = _bulk_flavor_names(default_variants)

    rows = []
    for p in page_products:
        variant = default_variant_by_product.get(p.id)
        if variant is None:
            # A Product with genuinely zero variants can't be priced --
            # never fabricate a row with nothing real to edit or save.
            continue
        entry = prices_by_variant.get(variant.id)
        stock_info = stock_by_variant.get(variant.id)
        stock = stock_info["quantity"] if stock_info else None
        stock_state = _stock_state(stock, stock_info["low_stock_at"] if stock_info else None)
        storage_path, thumbnail_paths = image_by_variant.get(variant.id, ("", {}))
        flavour_name = flavor_by_variant.get(variant.id)
        product_name = _display_name(p.translations.all(), p.id)
        price = entry.base_price_amount if entry else None
        cost = entry.cost_price_amount if entry else None
        rows.append(
            {
                "id": str(variant.id),
                "id_short": str(p.id)[:8],
                "sku": variant.sku,
                "name": f"{product_name}\n{flavour_name}" if flavour_name else product_name,
                "variant_count": variant_count_by_product.get(p.id, 1),
                "image_html": _direct_thumbnail_html(storage_path, thumbnail_paths),
                "product_id": str(p.id),
                "base_price": entry.cost_price_amount if entry else None,
                "old_price": entry.compare_at_price_amount if entry else None,
                "price": entry.base_price_amount if entry else None,
                "currency": entry.price_list.currency if entry else "UZS",
                "stock": stock,
                "stock_state": stock_state,
                "margin": round((price - cost) * 100 / price) if price and cost is not None else None,
                "discount": round((1 - price / entry.compare_at_price_amount) * 100) if entry and price and entry.compare_at_price_amount and entry.compare_at_price_amount > price else None,
                "size": _variant_size(variant),
            }
        )
    _attach_other_variants(rows, page_products, default_variant_by_product)
    return rows


def _variant_size(v) -> str:
    if not getattr(v, "weight_value", None):
        return ""
    value = int(v.weight_value) if float(v.weight_value).is_integer() else v.weight_value
    return f"{value} {v.weight_unit or ''}".strip()


def _attach_other_variants(rows: list, page_products, default_variant_by_product) -> None:
    """Each row also carries the product's other variants with their own prices (priced in the expandable panel)."""
    from apps.pricing.infrastructure.models import PriceListEntryModel
    from apps.stores.infrastructure.warehouse_admin import _last_costs

    by_product = {r["product_id"]: r for r in rows}
    others = list(orm.ProductVariant.objects.filter(product_id__in=[p.id for p in page_products]).order_by("product_id", "created_at"))
    defaults = {v.id for v in default_variant_by_product.values()}
    entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(product_variant_id__in=[v.id for v in others])}
    last = _last_costs([v.id for v in others])
    for r in rows:
        r["variants"], r["last_cost"], r["unpriced_variants"] = [], last.get(_uuid(r["id"])), 0
    for v in others:
        row = by_product.get(str(v.product_id))
        if row is None:
            continue
        e = entries.get(v.id)
        if e is None:
            row["unpriced_variants"] += 1
        if v.id in defaults:
            continue
        row["variants"].append({"id": str(v.id), "sku": v.sku, "size": _variant_size(v), "status": v.status, "price": e.base_price_amount if e else None,
                                "base_price": e.cost_price_amount if e else None, "old_price": e.compare_at_price_amount if e else None, "last_cost": last.get(v.id)})


def _uuid(v):
    import uuid

    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError):
        return None


def price_list_kpis() -> dict:
    """Whole-catalogue pricing health: products, variants without a price, discounted, average margin."""
    from apps.pricing.infrastructure.models import PriceListEntryModel

    variants = list(orm.ProductVariant.objects.filter(product__in=orm.Product.objects.all()).values_list("id", "product_id"))
    entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(product_variant_id__in=[v for v, _p in variants])}
    unpriced = [v for v, _p in variants if v not in entries]
    margins = [float((e.base_price_amount - e.cost_price_amount) * 100 / e.base_price_amount) for e in entries.values() if e.base_price_amount and e.cost_price_amount is not None]
    return {
        "products": len({p for _v, p in variants}), "variants": len(variants), "unpriced": len(unpriced), "unpriced_products": len({p for v, p in variants if v in set(unpriced)}),
        "discounted": sum(1 for e in entries.values() if e.compare_at_price_amount and e.compare_at_price_amount > e.base_price_amount),
        "margin": round(sum(margins) / len(margins)) if margins else None, "no_cost": sum(1 for e in entries.values() if e.cost_price_amount is None),
    }


def missing_price_product_ids() -> set:
    from apps.pricing.infrastructure.models import PriceListEntryModel

    priced = set(PriceListEntryModel.objects.values_list("product_variant_id", flat=True))
    return {p for v, p in orm.ProductVariant.objects.values_list("id", "product_id") if v not in priced}


_STOCK_LABELS = {
    "in": _("In stock"),
    "low": _("Low stock"),
    "out": _("Out of stock"),
    "not_tracked": _("Not tracked"),
}
_DISCOUNT_LABELS = {"discounted": _("Discounted"), "none": _("No discount")}


def _build_active_filter_chips(
    *,
    query,
    sort,
    brand_id,
    category_id,
    stock_status,
    discount_filter,
    price_min,
    price_max,
    brands,
    categories,
) -> list:
    """Each chip's remove_url is the full querystring with only that one filter dropped, computed server-side (not a template tag) so it works identically regardless of Django version."""
    from urllib.parse import urlencode

    base_params = {
        "q": query,
        "sort": sort if sort != _DEFAULT_SORT else "",
        "brand": brand_id or "",
        "category": category_id or "",
        "stock": stock_status or "",
        "discount": discount_filter or "",
        "price_min": price_min,
        "price_max": price_max,
    }

    def _remove(*drop_keys):
        params = {k: v for k, v in base_params.items() if v and k not in drop_keys}
        return "?" + urlencode(params)

    chips = []
    if brand_id:
        name = next((b["name"] for b in brands if b["id"] == brand_id), brand_id)
        chips.append({"label": f"{_('Brand')}: {name}", "remove_url": _remove("brand")})
    if category_id:
        name = next((c["name"] for c in categories if c["id"] == category_id), category_id)
        chips.append({"label": f"{_('Category')}: {name}", "remove_url": _remove("category")})
    if stock_status:
        chips.append(
            {"label": f"{_('Stock')}: {_STOCK_LABELS[stock_status]}", "remove_url": _remove("stock")}
        )
    if discount_filter:
        chips.append(
            {
                "label": f"{_('Discount')}: {_DISCOUNT_LABELS[discount_filter]}",
                "remove_url": _remove("discount"),
            }
        )
    if price_min or price_max:
        chips.append(
            {
                "label": f"{_('Price')}: {price_min or '0'}–{price_max or '∞'}",
                "remove_url": _remove("price_min", "price_max"),
            }
        )
    return chips


@staff_member_required
def price_list_view(request):
    query = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort") or _DEFAULT_SORT
    if sort not in _SORTABLE:
        sort = _DEFAULT_SORT
    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        page = 1
    brand_id = request.GET.get("brand") or None
    category_id = request.GET.get("category") or None
    stock_status = request.GET.get("stock") or None
    if stock_status not in _STOCK_FILTERS:
        stock_status = None
    discount_filter = request.GET.get("discount") or None
    if discount_filter not in _DISCOUNT_FILTERS:
        discount_filter = None
    price_min = _parse_decimal_or_none(request.GET.get("price_min"))
    price_max = _parse_decimal_or_none(request.GET.get("price_max"))

    qs = orm.Product.objects.annotate(_variant_count=Count("variants", distinct=True)).filter(_variant_count__gt=0)
    if brand_id:
        qs = qs.filter(brand_id=brand_id)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if query:
        from django.db.models import Q

        qs = qs.filter(
            Q(variants__sku__icontains=query) | Q(id__icontains=query) | Q(translations__name__icontains=query)
        ).distinct()
    if request.GET.get("missing") == "1":
        qs = qs.filter(id__in=missing_price_product_ids())
    qs = _apply_advanced_filters(
        qs,
        stock_status=stock_status,
        discount_filter=discount_filter,
        price_min=price_min,
        price_max=price_max,
    )

    sort_fn = _SORT_HANDLERS.get(sort.lstrip("-"), _rows_sorted_by_price)
    page_products, default_variant_by_product, prices_by_variant, total = sort_fn(qs, sort, page)

    variant_count_by_product = _bulk_variant_counts([p.id for p in page_products])
    rows = _build_rows(page_products, default_variant_by_product, prices_by_variant, variant_count_by_product)

    total_pages = max(math.ceil(total / _PAGE_SIZE), 1)
    page = min(page, total_pages)

    from apps.products.infrastructure import models as products_orm
    from apps.products.infrastructure.admin import _display_name

    brands = [
        {"id": str(b.id), "name": _display_name(b.translations.all(), b.id)}
        for b in products_orm.Brand.objects.filter(is_active=True).prefetch_related("translations")
    ]
    categories = [
        {"id": str(c.id), "name": _display_name(c.translations.all(), c.id)}
        for c in products_orm.Category.objects.filter(is_active=True).prefetch_related("translations")
    ]

    sort_columns = {}
    for base_field in ("name", "base_price", "old_price", "price"):
        active = sort.lstrip("-") == base_field
        current_desc = sort == f"-{base_field}"
        sort_columns[base_field] = {
            "active": active,
            "arrow": ("▲" if not current_desc else "▼") if active else "",
            "next_sort": f"-{base_field}" if (active and not current_desc) else base_field,
        }

    active_filter_count = sum(
        [
            bool(brand_id),
            bool(category_id),
            bool(stock_status),
            bool(discount_filter),
            price_min is not None,
            price_max is not None,
        ]
    )
    active_filters = _build_active_filter_chips(
        query=query,
        sort=sort,
        brand_id=brand_id,
        category_id=category_id,
        stock_status=stock_status,
        discount_filter=discount_filter,
        price_min=request.GET.get("price_min") or "",
        price_max=request.GET.get("price_max") or "",
        brands=brands,
        categories=categories,
    )

    context = {
        **admin.site.each_context(request),
        "title": _("Pricing List"),
        "rows": rows,
        "query": query,
        "sort": sort,
        "sort_columns": sort_columns,
        "page": page,
        "total_pages": total_pages,
        "total_count": total,
        "page_start": 0 if total == 0 else (page - 1) * _PAGE_SIZE + 1,
        "page_end": min(page * _PAGE_SIZE, total),
        "brands": brands,
        "categories": categories,
        "selected_brand": brand_id or "",
        "selected_category": category_id or "",
        "selected_stock": stock_status or "",
        "selected_discount": discount_filter or "",
        "price_min": request.GET.get("price_min") or "",
        "price_max": request.GET.get("price_max") or "",
        "active_filter_count": active_filter_count,
        "active_filters": active_filters,
        "kpi": price_list_kpis(),
        "missing": request.GET.get("missing") == "1",
    }
    return render(request, "admin/price_list.html", context)


def _err(message: str, status: int = 422) -> JsonResponse:
    """Matches `apps.platform.infrastructure.pos_view._json_error`'s exact envelope shape -- `{"error": {"message": ...}}`, not a bare string -- so this page's own JS error handling (identical to pos_terminal.html's `apiPost`) works unchanged."""
    return JsonResponse({"success": False, "error": {"message": message}}, status=status)


def _parse_decimal(raw) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("Not a valid number.") from exc
    if value < 0:
        raise ValueError("Value cannot be negative.")
    return value


@staff_member_required
def price_list_api_history(request, variant_id: str):
    """The last price changes of one variant (PriceHistoryEntry, written by SetPrice)."""
    import uuid

    from django.utils import timezone

    from apps.pricing.infrastructure.models import PriceHistoryEntryModel

    try:
        vid = uuid.UUID(variant_id)
    except ValueError:
        return _err("Invalid variant id.", status=400)
    labels = {"base": str(_("Price")), "cost": str(_("Cost")), "compare_at": str(_("Old price")), "sale": str(_("Sale price"))}
    rows = [{"type": labels.get(h.price_type, h.price_type), "old": str(h.old_amount) if h.old_amount is not None else None, "new": str(h.new_amount),
             "when": timezone.localtime(h.changed_at).strftime("%d.%m.%Y %H:%M")} for h in PriceHistoryEntryModel.objects.filter(product_variant_id=vid).order_by("-changed_at")[:200] if h.old_amount != h.new_amount][:25]
    return JsonResponse({"success": True, "data": rows})


@staff_member_required
@require_POST
def price_list_api_save(request, variant_id: str):
    import json
    import uuid

    from apps.pricing.infrastructure.models import PriceListEntryModel
    from apps.products.infrastructure.admin import _get_or_create_default_price_list

    try:
        variant_uuid = uuid.UUID(variant_id)
    except ValueError:
        return _err("Invalid variant id.", status=400)

    if not orm.ProductVariant.objects.filter(id=variant_uuid).exists():
        return _err("Variant not found.", status=404)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _err("Malformed request body.", status=400)

    try:
        base_cost = _parse_decimal(body.get("base_price")) if "base_price" in body else "unset"
        price = _parse_decimal(body.get("price")) if "price" in body else "unset"
        old_price = _parse_decimal(body.get("old_price")) if "old_price" in body else "unset"
    except ValueError as exc:
        return _err(str(exc))

    from apps.pricing.infrastructure.models import PriceListModel

    existing_list = (
        PriceListModel.objects.filter(status="active", region__isnull=True).order_by("created_at").first()
    )
    existing_entry = None
    if existing_list is not None:
        existing_entry = PriceListEntryModel.objects.filter(
            price_list=existing_list, product_variant_id=variant_uuid
        ).first()

    effective_base_cost = existing_entry.cost_price_amount if base_cost == "unset" else base_cost
    effective_price = existing_entry.base_price_amount if price == "unset" else price
    effective_old_price = existing_entry.compare_at_price_amount if old_price == "unset" else old_price

    if effective_price is None:
        return _err("Price (selling price) is required.")
    if effective_old_price is not None and effective_old_price <= effective_price:
        return _err("Old price must be greater than Price.")

    from apps.pricing.domain.exceptions import PriceListArchived
    from apps.pricing.infrastructure import composition as pricing_composition
    from common.exceptions import ConflictError

    price_list = _get_or_create_default_price_list()
    try:
        pricing_composition.build_set_price().execute(
            price_list_id=price_list.id,
            product_variant_id=variant_uuid,
            base_amount=effective_price,
            currency=price_list.currency,
            cost_amount=effective_base_cost,
            sale_amount=existing_entry.sale_price_amount if existing_entry else None,
            compare_at_amount=effective_old_price,
        )
    except (PriceListArchived, ConflictError) as exc:
        return _err(str(exc), status=409)
    except Exception:  # noqa: BLE001
        return _err("Could not save this price. Please try again.", status=500)

    return JsonResponse(
        {
            "success": True,
            "data": {
                "base_price": str(effective_base_cost) if effective_base_cost is not None else None,
                "old_price": str(effective_old_price) if effective_old_price is not None else None,
                "price": str(effective_price),
                "currency": price_list.currency,
            },
        }
    )


@staff_member_required
def price_list_api_product(request, product_id: str):
    """Every variant of one product with its prices, last purchase cost and stock -- the product list's quick price editor."""
    from django.db.models import Sum

    from apps.pricing.infrastructure.models import PriceListEntryModel
    from apps.products.infrastructure.admin import _display_name
    from apps.stores.infrastructure.models import StoreProductStock
    from apps.stores.infrastructure.warehouse_admin import _last_costs

    pid = _uuid(product_id)
    product = orm.Product.objects.filter(id=pid).prefetch_related("translations").first() if pid else None
    if product is None:
        return _err("Product not found.", status=404)
    variants = list(orm.ProductVariant.objects.filter(product_id=pid).select_related("package").order_by("created_at"))
    ids = [v.id for v in variants]
    entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(product_variant_id__in=ids, price_list__status="active")}
    stock = dict(StoreProductStock.objects.filter(product_variant_id__in=ids).values("product_variant_id").annotate(n=Sum("quantity")).values_list("product_variant_id", "n"))
    last = _last_costs(ids)
    flavours = _bulk_flavor_names(variants)

    def s(x):
        return str(x) if x is not None else None

    return JsonResponse({"success": True, "data": {
        "id": str(product.id), "name": _display_name(product.translations.all(), product.id),
        "variants": [{
            "id": str(v.id), "sku": v.sku, "status": v.status, "barcode": getattr(v, "barcode", None),
            "label": " · ".join(x for x in (_variant_size(v), str(v.package) if v.package_id else "", flavours.get(v.id, "")) if x) or v.sku,
            "cost": s(entries[v.id].cost_price_amount) if v.id in entries else None,
            "price": s(entries[v.id].base_price_amount) if v.id in entries else None,
            "old_price": s(entries[v.id].compare_at_price_amount) if v.id in entries else None,
            "last_cost": s(last.get(v.id)), "stock": stock.get(v.id, 0),
        } for v in variants],
    }})
