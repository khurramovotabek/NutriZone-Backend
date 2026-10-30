"""
Products read-model selectors -- optimized, read-only Postgres queries
backing `application/selectors.py::ProductSelector` and the query
Application Services (queries.py). No business logic: a selector never
decides whether something is *allowed*, only what data matches a given
filter/sort/search request (Django Implementation Blueprint §3).

`DjangoProductSearchBackend` implements `application/selectors.py::
ProductSearchBackend` (the Protocol that class depends on) using real,
indexed Postgres full-text search: a GIN-indexed, trigger-maintained
`ProductTranslation.search_vector` column for ranked/stemmed matching,
combined with a trigram GIN index on `name` for typo-tolerant fallback
(migration 0024). Per Domain Architecture Specification §2.16, this is
still the launch-stage engine choice -- the seam to a dedicated search
engine (Elasticsearch/OpenSearch/etc.) at much larger catalog scale is
`application/ports.py::SearchGateway`, not this class, which stays
Postgres-specific by design.
"""
from __future__ import annotations

import uuid

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum

from apps.products.domain.enums import ProductStatus
from apps.products.infrastructure import models as orm
from apps.products.infrastructure.variant_labels import variant_label
from apps.products.infrastructure.repositories import _DEFAULT_LOCALE, DjangoProductRepository


class ProductDetailSelector:
    """Backs `GetProduct` -- a single, fully-hydrated PUBLISHED product by slug. `get_by_id` added for the search-module barcode/SKU exact-match cascade (mirrors `get_by_slug`'s exact shape/filtering)."""

    def get_default_variant_id(self, product_id) -> uuid.UUID | None:
        """
        Real, closed gap: POS's own text-search results (via
        SearchProducts -> ProductSelector) are product-level cards
        with no variant_id at all, but every downstream POS call
        (price lookup, add_line_item) is variant-scoped. Resolves the
        same "is_default, else first" variant a real cashier's click
        would need -- never fabricates a variant that doesn't exist.
        """
        variant = orm.ProductVariant.objects.filter(product_id=product_id).order_by("-is_default", "created_at").first()
        return variant.id if variant else None

    def get_pos_display_info(self, product_ids: list) -> dict:
        """
        Real, closed gap: the POS terminal's premium redesign needs a
        brand name, a real variant weight ("size"), and a real
        available stock count on each product card -- none of which
        _product_card() exposes. Every value here is genuinely
        computed from already-existing, already-tested data
        (Brand/BrandTranslation, ProductVariant.weight_value/weight_unit,
        and the WMS stock's real available units, see
        apps/stores/infrastructure/availability.py) -- never a fabricated badge or count.
        Batched by product_ids to avoid one query per search result.
        """
        from apps.stores.infrastructure.availability import sellable

        products = orm.Product.objects.filter(id__in=product_ids).select_related("brand").prefetch_related("brand__translations", "variants")
        result: dict = {}
        for p in products:
            brand_name = None
            if p.brand_id:
                translation = next((t for t in p.brand.translations.all() if t.locale_code == _DEFAULT_LOCALE), None)
                brand_name = translation.name if translation else None

            variants = list(p.variants.all())
            default_variant = next((v for v in variants if v.is_default), None) or (variants[0] if variants else None)
            weight_value = default_variant.weight_value if default_variant else None
            weight_unit = default_variant.weight_unit if default_variant else None

            available_quantity = sellable([default_variant.id]).get(default_variant.id) if default_variant else None

            result[str(p.id)] = {"brand_name": brand_name, "weight_value": weight_value, "weight_unit": weight_unit, "available_quantity": available_quantity}
        return result

    def get_by_slug(self, slug: str, locale: str | None = None) -> dict | None:
        row = orm.Product.objects.filter(
            translations__slug=slug, status=ProductStatus.PUBLISHED.value
        ).prefetch_related(
            "translations", "variants", "media",
            # Real, closed gap: the flavour switcher below needs this
            # product's own tagged Flavours (name, color, photo) --
            # prefetched here so include_details=True still costs zero
            # *additional* queries beyond this one lookup, matching this
            # method's existing "zero new queries" property (see
            # _product_card's own docstring).
            "flavour_links__flavour__translations",
            "variants__media", "variants__package__translations", "variants__flavour__translations",
        ).first()
        if row is None:
            return None
        price_info = _bulk_default_variant_prices([row]).get(row.id)
        rating_info = _bulk_rating_summary([row.id]).get(str(row.id))
        default_variant_id = _bulk_default_variant_ids([row]).get(row.id)
        return _product_card(
            row, locale=locale, include_variants=True, include_details=True,
            price_info=price_info, rating_info=rating_info, default_variant_id=default_variant_id,
        )

    def get_by_id(self, product_id: uuid.UUID, locale: str | None = None) -> dict | None:
        """
        Real, closed gap: this previously never passed `include_variants`/
        `include_details` (unlike `get_by_slug` just above, which always
        has), so every caller of `get_by_id` -- confirmed directly: only
        `apps.telegram_bot.application.services.shopping.
        TelegramCatalogService.get_product`, used by the bot's own
        product-detail view -- silently got a variant-less, description-
        less card. The bot's "Batafsil" screen read `product["variants"]`
        expecting the same shape `get_by_slug` already gives the website,
        got `None` every time, and always rendered as if the product had
        no purchasable variant. Brought to parity with `get_by_slug`
        exactly (same prefetch depth, same flags) -- no new field, no new
        query pattern, the identical existing capability the website
        already relies on, just reachable by id as well as by slug.
        """
        row = orm.Product.objects.filter(
            id=product_id, status=ProductStatus.PUBLISHED.value
        ).prefetch_related(
            "translations", "variants", "media",
            "flavour_links__flavour__translations",
            "variants__media", "variants__package__translations", "variants__flavour__translations",
        ).first()
        if row is None:
            return None
        price_info = _bulk_default_variant_prices([row]).get(row.id)
        rating_info = _bulk_rating_summary([row.id]).get(str(row.id))
        default_variant_id = _bulk_default_variant_ids([row]).get(row.id)
        return _product_card(
            row, locale=locale, include_variants=True, include_details=True,
            price_info=price_info, rating_info=rating_info, default_variant_id=default_variant_id,
        )


class CatalogSelector:
    """Backs `ListProducts` -- public, PUBLISHED-only catalog browsing."""

    def list(self, category_id=None, brand_id=None, page: int = 1, page_size: int = 20, locale: str | None = None, order_by_newest: bool = False) -> tuple[list[dict], int]:
        """`locale` and `order_by_newest` are both optional and default to this method's exact prior behavior (no locale passthrough, no explicit ordering) -- added only for `apps.telegram_bot`'s own "🆕 Yangi mahsulotlar" listing, which needs both a locale-correct name and a real newest-first order with zero change to any existing caller (the REST `ProductListView` passes neither)."""
        qs = orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value)
        if category_id:
            from apps.products.infrastructure.catalog_browse import category_scope

            qs = qs.filter(category_id__in=category_scope(category_id))  # a section lists its product types' products too
        if brand_id:
            qs = qs.filter(brand_id=brand_id)
        if order_by_newest:
            qs = qs.order_by("-created_at")
        total = qs.count()
        start = (page - 1) * page_size
        rows = list(qs.prefetch_related("translations", "media", "variants")[start : start + page_size])
        price_by_product_id = _bulk_default_variant_prices(rows)
        rating_by_product_id = _bulk_rating_summary([r.id for r in rows])
        variant_by_product_id = _bulk_default_variant_ids(rows)
        return _with_stock([
            _product_card(
                r, locale=locale, price_info=price_by_product_id.get(r.id), rating_info=rating_by_product_id.get(str(r.id)),
                default_variant_id=variant_by_product_id.get(r.id),
            )
            for r in rows
        ]), total

    def list_best_sellers(self, limit: int = 8, locale: str | None = None) -> list[dict]:
        """
        Real, closed gap: no is_best_seller flag or sales-ranking
        mechanism previously existed anywhere in the project. Derives
        ranking from real, confirmed-order data (apps.ordering) rather
        than fabricating a ranking or a badge -- a genuine sales-count
        aggregation, not a marketing label. Only orders past
        DRAFT/PENDING_PAYMENT and not CANCELLED/RETURNED/FAILED count
        as a real sale (matches OrderStatus's own documented lifecycle).
        Returns an empty list (never fabricated products) once there
        simply are no qualifying sales yet.
        """
        from django.db.models import Sum

        from apps.ordering.infrastructure.models import OrderLineItemModel

        real_sale_statuses = ["confirmed", "processing", "shipped", "delivered", "completed"]
        variant_sales = (
            OrderLineItemModel.objects.filter(order__status__in=real_sale_statuses)
            .values("product_variant_id")
            .annotate(total_sold=Sum("quantity"))
        )
        variant_id_to_sold = {row["product_variant_id"]: row["total_sold"] for row in variant_sales}
        if not variant_id_to_sold:
            return []

        product_id_to_sold: dict = {}
        for variant in orm.ProductVariant.objects.filter(id__in=variant_id_to_sold.keys()).values("id", "product_id"):
            sold = variant_id_to_sold[variant["id"]]
            product_id_to_sold[variant["product_id"]] = product_id_to_sold.get(variant["product_id"], 0) + sold

        top_product_ids = sorted(product_id_to_sold, key=lambda pid: product_id_to_sold[pid], reverse=True)[:limit]
        rows = list(
            orm.Product.objects.filter(id__in=top_product_ids, status=ProductStatus.PUBLISHED.value)
            .prefetch_related("translations", "media", "variants")
        )
        rows_by_id = {r.id: r for r in rows}
        ordered_rows = [rows_by_id[pid] for pid in top_product_ids if pid in rows_by_id]

        price_by_product_id = _bulk_default_variant_prices(ordered_rows)
        rating_by_product_id = _bulk_rating_summary([r.id for r in ordered_rows])
        variant_by_product_id = _bulk_default_variant_ids(ordered_rows)
        return _with_stock([
            {
                **_product_card(r, locale=locale, price_info=price_by_product_id.get(r.id), rating_info=rating_by_product_id.get(str(r.id)), default_variant_id=variant_by_product_id.get(r.id)),
                "units_sold": product_id_to_sold[r.id],
            }
            for r in ordered_rows
        ])


def _admin_product_card(row: orm.Product) -> dict:
    """
    Real, closed bug: this function was called (AdminCatalogSelector.
    list(), below) but never defined anywhere in this module -- any
    real call to `GET /admin/products` (AdminProductListCreateView)
    crashed with `NameError: name '_admin_product_card' is not
    defined`. Matches `AdminProductListItemSerializer`'s exact declared
    shape: every status is shown (never PUBLISHED-only, unlike the
    public `_product_card`), and `variant_count`/`media_count` are
    read from this selector's own `.annotate()` above -- never a
    second, N+1 count.
    """
    all_translations = list(row.translations.all())
    translation = next((t for t in all_translations if t.locale_code == _DEFAULT_LOCALE), None) or (all_translations[0] if all_translations else None)
    return {
        "id": str(row.id),
        "slug": translation.slug if translation else str(row.id),
        "name": translation.name if translation else "",
        "status": row.status,
        "brand_id": str(row.brand_id) if row.brand_id else None,
        "category_id": str(row.category_id) if row.category_id else None,
        "variant_count": row.variant_count,
        "media_count": row.media_count,
        "created_at": row.created_at.isoformat(),
    }


class AdminCatalogSelector:
    """Backs `AdminListProducts` -- every status, staff-only."""

    def list(self, status=None, brand_id=None, category_id=None, query=None, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        qs = orm.Product.objects.all()
        if status:
            qs = qs.filter(status=status)
        if brand_id:
            qs = qs.filter(brand_id=brand_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if query:
            qs = qs.filter(translations__name__icontains=query).distinct()
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.prefetch_related("translations").annotate(variant_count=Count("variants", distinct=True), media_count=Count("media", distinct=True))[start : start + page_size]
        return [_admin_product_card(r) for r in rows], total


def valid_gtin(code: str | None) -> str | None:
    """The barcode when it is a real GTIN-8/12/13/14 (digits, correct check digit) -- for search engines'
    product matching; an internal or mistyped code is never published as a GTIN."""
    code = (code or "").strip()
    if len(code) not in (8, 12, 13, 14) or not code.isdigit():
        return None
    body, check = code[:-1], int(code[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return code if (10 - total % 10) % 10 == check else None


def _url_slugs(row, locale: str | None) -> tuple[str, dict[str, str]]:
    """(slug in `locale` -- else uz, else any, else the id; slug per language) from prefetched translations, for readable URLs."""
    slugs = {t.locale_code: t.slug for t in row.translations.all() if t.slug}
    return slugs.get(locale or _DEFAULT_LOCALE) or slugs.get("uz") or next(iter(slugs.values()), str(row.id)), slugs


class CategoryTreeSelector:
    def tree(self, locale: str | None = None) -> list[dict]:
        """`locale`: names in that language (falling back like `_translated_name`); omitted -- the default locale, as before."""
        from django.conf import settings

        rows = orm.Category.objects.filter(is_active=True).prefetch_related("translations").order_by("sort_order")
        result = []
        for r in rows:
            image_url = None
            if r.image_storage_path:
                path = r.image_thumbnail_paths.get("medium") or r.image_storage_path
                base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
                image_url = path if path.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{path}"
            result.append({
                "id": str(r.id), "parent_id": str(r.parent_id) if r.parent_id else None,
                "name": _translated_name(r, locale), "sort_order": r.sort_order, "image_url": image_url,
                **dict(zip(("slug", "slugs"), _url_slugs(r, locale))),
            })
        return result

    def description(self, category_id, locale: str | None = None) -> dict | None:
        """One active category's long description in `locale` (falling back to uz, then any filled one); None if unknown."""
        try:
            row = orm.Category.objects.filter(pk=category_id, is_active=True).prefetch_related("translations").first()
        except (ValueError, ValidationError):
            return None
        if row is None:
            return None
        texts = {t.locale_code: (t.description or "").strip() for t in row.translations.all()}
        text = texts.get(locale or "") or texts.get("uz") or next((v for v in texts.values() if v), "")
        return {"id": str(row.id), "name": _translated_name(row, locale), "description": text}


class BrandSelector:
    def list_active(self, locale: str | None = None, description_locale: str | None = None) -> list[dict]:
        """`locale` optional, defaults to this method's exact prior behavior (`_DEFAULT_LOCALE`) -- added only for `apps.telegram_bot`'s own locale-aware brand listing; the public `GET /brands` REST view still calls this with no locale, unaffected."""
        from django.conf import settings

        rows = orm.Brand.objects.filter(is_active=True, is_manufacturer=False).select_related("country").prefetch_related("translations", "country__translations").annotate(
            published_count=Count("products", filter=Q(products__status=ProductStatus.PUBLISHED.value, products__deleted_at__isnull=True), distinct=True)
        )
        result = []
        for r in rows:
            logo_url = None
            if r.logo_storage_path:
                path = r.logo_thumbnail_paths.get("medium") or r.logo_storage_path
                base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
                logo_url = path if path.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{path}"
            result.append({
                "id": str(r.id), "name": _translated_name(r, locale=locale), "logo_url": logo_url,
                **dict(zip(("slug", "slugs"), _url_slugs(r, locale or description_locale))),
                "description": _translated_description(r, description_locale or locale),
                "product_count": r.published_count, "country": _brand_country(r.country, description_locale or locale),
            })
        return result


def _brand_country(country, locale: str | None) -> dict | None:
    if country is None:
        return None
    names = {t.locale_code: t.name for t in country.translations.all()}
    return {"code": country.code, "flag": country.icon or "", "name": names.get(locale or _DEFAULT_LOCALE) or names.get("uz") or country.code}


class FlavourSelector:
    def list_active(self, locale: str | None = None) -> list[dict]:
        rows = orm.Flavour.objects.filter(is_active=True).prefetch_related("translations").order_by("sort_order")
        return [_flavour_summary(r, locale or _DEFAULT_LOCALE) for r in rows]


class PackageSelector:
    def list_active(self, locale: str | None = None) -> list[dict]:
        rows = orm.Package.objects.filter(is_active=True).prefetch_related("translations").order_by("sort_order")
        return [_package_summary(r, locale or _DEFAULT_LOCALE) for r in rows]


def _normalize_filters(filters: dict) -> dict:
    """Maps the API's filter dict onto catalog_browse's keys, accepting the older single-value keys too."""
    out = dict(filters)
    if "brand_ids" not in out and out.get("brand_id"):
        out["brand_ids"] = [out["brand_id"]]
    if "flavour_ids" not in out and out.get("flavor_id"):
        out["flavour_ids"] = [out["flavor_id"]]
    if out.get("availability") == "in_stock":
        out["in_stock"] = True
    return out


class FilterSelector:
    """Backs the faceted-search metadata endpoint (mission's 'Filter Options' cache group) -- brand/category/flavour/availability/nutrition-category/status facets."""

    def facets(self, category_id=None) -> dict:
        product_qs = orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value)
        if category_id:
            from apps.products.infrastructure.catalog_browse import category_scope

            product_qs = product_qs.filter(category_id__in=category_scope(category_id))

        brand_ids = product_qs.exclude(brand_id=None).values_list("brand_id", flat=True).distinct()
        brands = orm.Brand.objects.filter(id__in=brand_ids).prefetch_related("translations")

        flavour_ids = orm.ProductFlavour.objects.filter(product__in=product_qs).values_list("flavour_id", flat=True).distinct()
        flavours = orm.Flavour.objects.filter(id__in=flavour_ids, is_active=True).prefetch_related("translations").order_by("sort_order")

        return {
            "brand": [{"id": str(b.id), "name": _translated_name(b)} for b in brands],
            "flavour": [_flavour_summary(f, _DEFAULT_LOCALE) for f in flavours],
            "status": [s.value for s in ProductStatus],
        }


class StatisticsSelector:
    """Backs future Admin CRM catalog-health widgets -- e.g. product counts by status, average media per product (mission's `average_media_per_product` metric's data source)."""

    def counts_by_status(self) -> dict[str, int]:
        return dict(orm.Product.objects.values_list("status").annotate(count=Count("id")).order_by())

    def products_by_category(self, limit: int = 10) -> list[dict]:
        """
        Phase E2: real category distribution -- published products
        grouped by their real Category FK, with the real translated
        category name resolved in one bulk query (small category
        count, never per-row). PUBLISHED products only, matching
        top_products()'s own established scoping convention.
        """
        rows = list(
            orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value, category__isnull=False)
            .values("category_id")
            .annotate(count=Count("id"))
            .order_by("-count")[:limit]
        )
        category_ids = [r["category_id"] for r in rows]
        names = {t.category_id: t.name for t in orm.CategoryTranslation.objects.filter(category_id__in=category_ids, locale_code=_DEFAULT_LOCALE)}
        return [{"category_id": str(r["category_id"]), "name": names.get(r["category_id"], str(r["category_id"])[:8]), "count": r["count"]} for r in rows]

    def average_media_per_product(self) -> float:
        total_products = orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value).count()
        if total_products == 0:
            return 0.0
        total_media = orm.ProductMedia.objects.filter(product__status=ProductStatus.PUBLISHED.value).count()
        return round(total_media / total_products, 2)

    def top_products(self, limit: int = 10) -> list[dict]:
        """
        Dashboard "Top Products" -- reuses the exact same cross-module
        aggregation pattern already proven in
        `RecommendationSelector.for_customer()`'s own popularity tier
        (`OrderLineItemModel -> ProductVariant -> Product`), rather
        than a second, duplicate popularity concept. Completed orders
        only, ACTIVE line items only, PUBLISHED products only. Two
        bounded, DB-aggregated queries total -- never one query per
        product or per order line.
        """
        from apps.ordering.domain.enums import OrderLineItemStatus, OrderStatus
        from apps.ordering.infrastructure import models as ordering_orm

        limit = max(1, min(limit, 50))

        variant_sales = (
            ordering_orm.OrderLineItemModel.objects.filter(order__status=OrderStatus.COMPLETED.value, status=OrderLineItemStatus.ACTIVE.value)
            .values("product_variant_id").annotate(quantity_sold=Sum("quantity")).order_by("-quantity_sold")
        )
        variant_quantities: dict = {}
        for row in variant_sales:
            variant_quantities[row["product_variant_id"]] = row["quantity_sold"]
        if not variant_quantities:
            return []

        variants = (
            orm.ProductVariant.objects.filter(id__in=list(variant_quantities.keys()), product__status=ProductStatus.PUBLISHED.value)
            .select_related("product").prefetch_related("product__translations")
        )
        product_totals: dict = {}
        for variant in variants:
            qty = variant_quantities.get(variant.id, 0)
            product_totals[variant.product_id] = product_totals.get(variant.product_id, 0) + qty

        ranked = sorted(product_totals.items(), key=lambda item: (-item[1], str(item[0])))[:limit]  # quantity desc, id as deterministic tiebreak
        product_ids = [pid for pid, _ in ranked]
        products_by_id = {p.id: p for p in orm.Product.objects.filter(id__in=product_ids).prefetch_related("translations")}

        results = []
        for product_id, quantity_sold in ranked:
            product = products_by_id.get(product_id)
            if product is None:
                continue
            card = _product_card(product)
            card["quantity_sold"] = quantity_sold
            results.append(card)
        return results


_FTS_CONFIG_BY_LOCALE = {"en": "english", "ru": "russian"}


def _fts_config_for_locale(locale_code: str) -> str:
    """Uzbek has no Postgres text-search dictionary, so it falls back to `simple` (token matching, no stemming) -- must match the trigger in migration 0024 that populates `search_vector`, or query tokens won't line up with indexed ones."""
    return _FTS_CONFIG_BY_LOCALE.get(locale_code, "simple")


class DjangoProductSearchBackend:
    """Implements `application/selectors.py::ProductSearchBackend`."""

    def search(self, query: str, filters: dict, page: int, page_size: int, sort: str, locale: str | None = None) -> dict:
        """
        Catalog browse with or without a query -- smart search ranking,
        every filter, facets with counts, and sorting live in
        catalog_browse.py; this only renders the requested page's cards.
        `locale` falls back to the platform default when the caller
        didn't resolve one.
        """
        from apps.products.infrastructure import catalog_browse

        effective_locale = locale or _DEFAULT_LOCALE
        outcome = catalog_browse.browse(query=query, filters=_normalize_filters(filters), sort=sort, page=page, page_size=page_size, locale=effective_locale)
        page_ids = outcome["ordered_ids"]
        rows_by_id = {r.id: r for r in orm.Product.objects.filter(id__in=page_ids).prefetch_related("translations", "media", "variants")}
        rows = [rows_by_id[pid] for pid in page_ids if pid in rows_by_id]

        variant_by_product_id = _bulk_default_variant_ids(rows)
        price_by_product_id = _bulk_default_variant_prices(rows)
        rating_by_product_id = _bulk_rating_summary([r.id for r in rows])
        return {
            "results": _with_stock([
                _product_card(
                    r, locale=effective_locale, price_info=price_by_product_id.get(r.id), rating_info=rating_by_product_id.get(str(r.id)),
                    default_variant_id=variant_by_product_id.get(r.id),
                )
                for r in rows
            ]),
            "total_count": outcome["total_count"],
            "facets": outcome["facets"],
            "suggestion": outcome["suggestion"],
        }

    def autocomplete(self, partial: str, limit: int) -> list[str]:
        names = (
            orm.ProductTranslation.objects.filter(locale_code=_DEFAULT_LOCALE, name__istartswith=partial, product__status=ProductStatus.PUBLISHED.value)
            .values_list("name", flat=True)
            .distinct()[:limit]
        )
        return list(names)

    def list_facets(self, category_id=None) -> dict:
        return FilterSelector().facets(category_id=category_id)


# --- shared read-model shaping helpers -------------------------------


def _translated_description(row, locale: str | None = None) -> str:
    """Brand description in `locale`, else Uzbek, else any non-empty translation (descriptions are often written in one language only)."""
    translations = list(row.translations.all())
    for candidate in (locale, "uz"):
        t = next((tr for tr in translations if tr.locale_code == candidate and tr.description), None)
        if t:
            return t.description
    return next((tr.description for tr in translations if tr.description), "")


def _translated_name(row, locale: str | None = None) -> str:
    """
    No `locale` (every pre-existing caller): unchanged prior behavior
    exactly -- a single `_DEFAULT_LOCALE` lookup, `""` if that specific
    translation is missing.

    An explicit `locale` (added only for `apps.telegram_bot`'s locale-
    aware brand listing): falls back to `_DEFAULT_LOCALE`, then to
    whatever translation exists at all, mirroring `_product_card`'s own
    established fallback chain -- never silently rendering a real,
    named row as blank just because the caller's requested locale
    happens to be the one translation it's missing.
    """
    if locale is None:
        t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
        return t.name if t else ""
    translations = list(row.translations.all())
    match = (
        next((tr for tr in translations if tr.locale_code == locale), None)
        or next((tr for tr in translations if tr.locale_code == _DEFAULT_LOCALE), None)
        or (translations[0] if translations else None)
    )
    return match.name if match else ""




def _bulk_rating_summary(product_ids: list) -> dict:
    """Shared by CatalogSelector.list() and ProductDetailSelector -- resolves {product_id_str: {"average": ..., "count": ...}} via the real, existing Reviews module (cross-app read, matching this build's own established convention for Category.image/ProductVariantInline pricing). A single query regardless of product count."""
    from apps.reviews.infrastructure.selectors import ReviewStatisticsSelector

    return ReviewStatisticsSelector().bulk_rating_summary(product_ids)


def _bulk_default_variant_prices(products: list) -> dict:
    """Shared by CatalogSelector.list() and ProductDetailSelector -- resolves {product_id: {"amount": ..., "currency": ...}} for each product's is_default variant (or first variant, if none is marked default), matching ProductAdmin.price_display's own established convention exactly. A fixed, small number of queries regardless of product count -- never per-row."""
    from apps.pricing.infrastructure.models import PriceListEntryModel

    representative_variant_by_product = {}
    variant_ids = []
    for product in products:
        variants = list(product.variants.all())
        if not variants:
            continue
        representative = next((v for v in variants if v.is_default), variants[0])
        representative_variant_by_product[product.id] = representative.id
        variant_ids.append(representative.id)

    prices_by_variant = {}
    for entry in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).select_related("price_list").order_by("product_variant_id"):
        prices_by_variant.setdefault(entry.product_variant_id, entry)

    result = {}
    for product_id, variant_id in representative_variant_by_product.items():
        entry = prices_by_variant.get(variant_id)
        if entry is not None:
            result[product_id] = _price_payload(entry)
    return result


def _price_payload(entry) -> dict:
    """
    What the shopper pays and what it's marked down from, for one PriceListEntry.

    `amount` follows checkout's own rule (`CalculatePrice`: sale price when set,
    else base) so the catalog never shows a price the cart then contradicts.
    `compare_at_amount` is the crossed-out "old price": the editor's Old Price
    (compare_at) when it's above `amount`, else the base price when a sale price
    undercuts it, else None. Cart-level campaigns/coupons are not reflected here.
    """
    effective = entry.sale_price_amount if entry.sale_price_amount is not None else entry.base_price_amount
    compare_at = entry.compare_at_price_amount
    if compare_at is None or compare_at <= effective:
        compare_at = entry.base_price_amount if entry.base_price_amount > effective else None
    return {"amount": str(effective), "currency": entry.price_list.currency, "compare_at_amount": str(compare_at) if compare_at is not None else None}


def _discount_fields(price_info: dict | None) -> dict:
    """`compare_at_price` + whole-number `discount_percent` (rounded down, so the badge never overstates the saving)."""
    compare_at = price_info.get("compare_at_amount") if price_info else None
    if not compare_at:
        return {"compare_at_price": None, "discount_percent": None}
    from decimal import Decimal

    amount, old = Decimal(price_info["amount"]), Decimal(compare_at)
    percent = int((old - amount) * 100 / old) if old > 0 else 0
    return {"compare_at_price": compare_at, "discount_percent": percent if percent > 0 else None}


def _bulk_default_variant_ids(products: list) -> dict:
    """
    Real, product-required capability: the "Add to cart" button on the
    Product List/Catalog page needs a product_variant_id to call
    Cart's own AddItem operation -- but the list response never
    exposed one at all (only the detail response's own
    include_variants=True did). Returns {product_id: variant_id} for
    every product's is_default variant (or first variant, if none is
    marked default) -- identical selection rule to
    _bulk_default_variant_prices(), but never skips a product just
    because it has no price entry yet (a variant can exist and be
    addable to cart before pricing is configured).
    """
    result = {}
    for product in products:
        variants = list(product.variants.all())
        if not variants:
            continue
        representative = next((v for v in variants if v.is_default), variants[0])
        result[product.id] = representative.id
    return result


def _resolve_media_url(storage_path: str | None) -> str | None:
    """
    Real, closed gap: storage_path is a bare relative path (e.g.
    "image/72/63/....jpg"), never a full URL. Returning it as-is left
    the frontend's <img src={...}> resolved against its own origin
    (the Next.js host), not the Django backend that actually serves
    /media/ -- so every product image request went to the wrong
    server and 404'd there, regardless of whether the backend itself
    correctly served the file. PUBLIC_BASE_URL is the same setting
    already established for Telegram's own real, absolute callback
    URLs -- reused here rather than inventing a second config key.
    """
    if not storage_path:
        return None
    from django.conf import settings

    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return f"{base}{settings.MEDIA_URL}{storage_path}"


def _resolve_flavour_image(flavour: orm.Flavour) -> str | None:
    """Same convention as CategorySelector/BrandSelector: prefer the "medium" thumbnail (a chip-sized swatch, not the full upload) over the original, and pass an already-absolute URL through unchanged (a future object-storage/CDN backend)."""
    if not flavour.image_storage_path:
        return None
    from django.conf import settings

    path = flavour.image_thumbnail_paths.get("medium") or flavour.image_storage_path
    if path.startswith(("http://", "https://")):
        return path
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return f"{base}{settings.MEDIA_URL}{path}"


def _flavour_summary(flavour: orm.Flavour, locale: str) -> dict:
    """Mirrors _product_card's own translation-fallback order (requested locale -> uz -> whatever exists) rather than a single-locale lookup, since `flavour.translations` is prefetched by every real caller and a `.filter()` call would silently re-query instead of using that prefetch cache."""
    translations = list(flavour.translations.all())
    t = next((tr for tr in translations if tr.locale_code == locale), None)
    if t is None:
        t = next((tr for tr in translations if tr.locale_code == "uz"), None) or (translations[0] if translations else None)
    return {
        "id": str(flavour.id),
        "name": t.name if t else str(flavour.id),
        "color_hex": flavour.color_hex,
        "image_url": _resolve_flavour_image(flavour),
    }


def _package_summary(package: orm.Package | None, locale: str) -> dict | None:
    """Mirrors _flavour_summary's own translation-fallback order -- `None` when a variant genuinely has no package type set yet, never a fabricated placeholder."""
    if package is None:
        return None
    translations = list(package.translations.all())
    t = next((tr for tr in translations if tr.locale_code == locale), None)
    if t is None:
        t = next((tr for tr in translations if tr.locale_code == "uz"), None) or (translations[0] if translations else None)
    return {"id": str(package.id), "name": t.name if t else str(package.id)}


_LOW_STOCK_THRESHOLD = 10


def bulk_variant_prices(variant_ids: list) -> dict:
    """Same source/precedent as _bulk_default_variant_prices (PriceListEntryModel, "first entry found per variant" convention), just resolved for every given variant instead of only each product's default one -- both are equally public, already-displayed data (a product's price is already shown on every catalog card); this only extends that same exposure to a product's own sibling variants, never to another product's pricing.

    Deliberately public (no leading underscore): the Inventory admin dashboard's own product/stock table (apps/platform/infrastructure/inventory_view.py) reuses this exact bulk resolution for its own "selling price" column, rather than a second, parallel price query."""
    if not variant_ids:
        return {}
    from apps.pricing.infrastructure.models import PriceListEntryModel

    result: dict = {}
    for entry in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).select_related("price_list").order_by("product_variant_id"):
        result.setdefault(entry.product_variant_id, _price_payload(entry))
    return result


def _bulk_variant_stock_status(variant_ids: list) -> dict:
    """
    Real, closed gap: the storefront had no honest way to show "Only 3
    left"/"Out of stock" per flavor. Reads the WMS stock (on hand minus
    reserved at active locations, see apps/stores/infrastructure/availability.py),
    the same numbers the warehouse and the POS work with.
    Deliberately exposes a *status*, not the raw count, except when
    genuinely low (a common, real e-commerce urgency signal) -- unlike
    POS (a staff tool), there's no reason a public product page should
    reveal exactly how many units of a healthy-stock item sit in a
    warehouse.
    """
    if not variant_ids:
        return {}
    from apps.stores.infrastructure.availability import sellable

    totals = sellable(variant_ids)
    result: dict = {}
    for variant_id in variant_ids:
        quantity = totals.get(variant_id, 0)
        # Product decision: the storefront shows the real count for every
        # status (not only low stock), matching the list cards' own
        # `stock_quantity` -- see `_with_stock`.
        if quantity <= 0:
            result[variant_id] = {"status": "out_of_stock", "quantity": 0}
        elif quantity <= _LOW_STOCK_THRESHOLD:
            result[variant_id] = {"status": "low_stock", "quantity": quantity}
        else:
            result[variant_id] = {"status": "in_stock", "quantity": quantity}
    return result


def _bulk_variant_store_stock(variant_ids: list) -> dict:
    """
    {variant_id: [store availability, ...]} -- which active branches hold
    each variant and how many units are still sellable there (on hand
    minus reserved), straight from the WMS stock (see
    apps/stores/infrastructure/availability.py). Warehouses and closed
    branches are never listed. Stores with stock come first (most units
    first), then branches that carry the variant but ran out.
    """
    from apps.stores.infrastructure.availability import branches

    return branches(variant_ids)


def _with_family(cards: list[dict], rows: list) -> None:
    """
    Product-family facts for list cards: how many sizes and flavours the family sells, and `price_from` -- the
    lowest active variant price when the family's prices differ ("from 190 000 so'm"), else None.
    """
    by_product: dict = {}
    for vid, pid, status, weight, unit, flavour in rows:
        if status != "active":
            continue
        fam = by_product.setdefault(str(pid), {"sizes": set(), "flavours": set(), "variants": []})
        if weight:
            fam["sizes"].add((weight, unit))
        if flavour:
            fam["flavours"].add(flavour)
        fam["variants"].append(vid)
    multi = [vid for fam in by_product.values() if len(fam["variants"]) > 1 for vid in fam["variants"]]
    prices = bulk_variant_prices(multi) if multi else {}
    for card in cards:
        fam = by_product.get(str(card["id"]))
        card["size_count"] = len(fam["sizes"]) if fam else 0
        card["flavour_count"] = len(fam["flavours"]) if fam else 0
        amounts = sorted({float(prices[v]["amount"]) for v in (fam["variants"] if fam else []) if v in prices})
        card["price_from"] = f"{amounts[0]:.2f}" if len(amounts) > 1 else None


def _with_stock(cards: list[dict]) -> list[dict]:
    """
    Adds the product's total available stock to list-level cards --
    `stock_quantity` (units across all variants and warehouses) and
    `stock_status` (in_stock/low_stock/out_of_stock). Product decision:
    the storefront's product lists show "N left" for every product, not
    only for low stock (the per-variant detail payload keeps its own
    status-only rule). Products with no inventory record at all get
    `None` for both -- "not tracked", never a fabricated count.
    Three queries for the whole page, never one per card.
    """
    if not cards:
        return cards
    from apps.stores.infrastructure.availability import sellable

    rows = list(orm.ProductVariant.objects.filter(product_id__in=[c["id"] for c in cards]).values_list("id", "product_id", "status", "weight_value", "weight_unit", "flavour_id"))
    product_by_variant = {vid: pid for vid, pid, *_rest in rows}
    _with_family(cards, rows)
    totals: dict = {}
    tracked: set = set()
    for variant_id, units in sellable(list(product_by_variant)).items():
        product_id = str(product_by_variant[variant_id])
        tracked.add(product_id)
        totals[product_id] = totals.get(product_id, 0) + units

    for card in cards:
        product_id = str(card["id"])
        if product_id not in tracked:
            card["stock_quantity"], card["stock_status"] = None, None
            continue
        quantity = totals.get(product_id, 0)
        card["stock_quantity"] = quantity
        card["stock_status"] = "out_of_stock" if quantity <= 0 else "low_stock" if quantity <= _LOW_STOCK_THRESHOLD else "in_stock"
    return cards


def _variant_summary(variant: orm.ProductVariant, locale: str, price_by_variant: dict, stock_by_variant: dict, stores_by_variant: dict | None = None) -> dict:
    """Real, closed gap: the public variant payload carried no way to tell what a variant actually weighs, what it costs, whether it's in stock, or what it looks like -- a storefront could offer `product_variant_id` to Cart's AddItem but never render a real "2.27 kg, 620,000 UZS, in stock"-style selector. `media` is the real per-variant subset of `catalog.product_media` (its `variant` FK, previously write-only -- see UploadImage's new `variant_id` param). All prefetched/bulk-resolved by the caller so this adds no new queries per variant. `flavour` is the variant's own flavour (size x flavour families); `_resolve_flavour_switcher` covers legacy one-flavour-per-product data."""
    own_media = sorted(
        (m for m in variant.media.all() if m.media_role in ("primary", "gallery")),
        key=lambda m: (0 if m.media_role == "primary" else 1, m.sort_order),
    )
    # Empty when nobody has tagged a photo to this specific variant yet
    # -- the caller (storefront) falls back to the shared/family
    # gallery in that case, never a broken/empty viewer.
    gallery = [url for m in own_media if (url := _resolve_media_url(m.storage_path))]
    video = next((m for m in variant.media.all() if m.media_role == "video"), None)

    price_info = price_by_variant.get(variant.id)
    stock_info = stock_by_variant.get(variant.id, {"status": "out_of_stock", "quantity": 0})

    return {
        "id": str(variant.id),
        "sku": variant.sku,
        "gtin": valid_gtin(variant.barcode),
        "is_default": variant.is_default,
        "status": variant.status,
        "weight_value": variant.weight_value,
        "weight_unit": variant.weight_unit,
        "package": _package_summary(variant.package, locale),
        # each variant of a family is one size x one flavour (ProductVariant.flavour); null for legacy single-flavour rows
        "flavour": _flavour_summary(variant.flavour, locale) if variant.flavour_id else None,
        "gallery": gallery,
        "video_url": _resolve_media_url(video.storage_path) if video else None,
        "price": price_info["amount"] if price_info else None,
        "currency": price_info["currency"] if price_info else None,
        **_discount_fields(price_info),
        "stock_status": stock_info["status"],
        "stock_quantity": stock_info["quantity"],
        "store_availability": (stores_by_variant or {}).get(variant.id, []),
    }


def _resolve_flavour_switcher(row: orm.Product, own_slug: str, locale: str, default_variant: orm.ProductVariant | None) -> list[dict]:
    """
    PDP flavour switcher (real, product-required capability): selecting
    a flavour swatch on a product detail page navigates to the sibling
    Product that carries that Flavour at the SAME weight. This catalog
    models one flavour+weight combination as one independent Product
    row, not one Product with many variants (confirmed directly via DB
    inspection: e.g. "Gold Standard Whey" exists as 3 separate Product
    rows) -- so the grouping happens here, at read time, by
    (brand_id, category_id, weight_value, weight_unit), rather than via
    any parent/family FK the schema doesn't have. Scoped to same brand
    AND category (both required) specifically to avoid false-positive
    grouping across unrelated products that happen to share a weight.
    """
    # A product family whose variants carry their own flavour: every flavour is chosen on this page, no sibling hops.
    variant_flavours = {}
    for v in row.variants.all():
        if v.flavour_id and v.status == "active" and not getattr(v, "is_deleted", False) and v.flavour_id not in variant_flavours:
            variant_flavours[v.flavour_id] = v.flavour
    if variant_flavours:
        current = default_variant.flavour_id if default_variant is not None else None
        options = [
            {**_flavour_summary(f, locale), "product_id": str(row.id), "product_slug": own_slug, "is_current": fid == current}
            for fid, f in variant_flavours.items()
        ]
        return sorted(options, key=lambda o: o["name"].lower())

    own_options = [
        {**_flavour_summary(link.flavour, locale), "product_id": str(row.id), "product_slug": own_slug, "is_current": True}
        for link in row.flavour_links.all()
    ]
    if default_variant is None or default_variant.weight_value is None or row.brand_id is None or row.category_id is None:
        return own_options

    sibling_rows = (
        orm.Product.objects.filter(
            status=ProductStatus.PUBLISHED.value, brand_id=row.brand_id, category_id=row.category_id,
            variants__weight_value=default_variant.weight_value, variants__weight_unit=default_variant.weight_unit,
        )
        .exclude(id=row.id)
        .distinct()
        .prefetch_related("translations", "flavour_links__flavour__translations")
    )

    options = list(own_options)
    for sibling in sibling_rows:
        sibling_translations = list(sibling.translations.all())
        t = (
            next((tr for tr in sibling_translations if tr.locale_code == locale), None)
            or next((tr for tr in sibling_translations if tr.locale_code == "uz"), None)
            or (sibling_translations[0] if sibling_translations else None)
        )
        sibling_slug = t.slug if t else str(sibling.id)
        for link in sibling.flavour_links.all():
            options.append({**_flavour_summary(link.flavour, locale), "product_id": str(sibling.id), "product_slug": sibling_slug, "is_current": False})

    seen: set[str] = set()
    deduped = []
    for option in options:
        if option["id"] in seen:  # a data-quality edge (the same Flavour double-tagged across siblings) -- keep the first occurrence, self wins
            continue
        seen.add(option["id"])
        deduped.append(option)
    return sorted(deduped, key=lambda o: (0 if o["is_current"] else 1, o["name"]))


def _product_card(row: orm.Product, locale: str | None = None, include_variants: bool = False, include_details: bool = False, price_info: dict | None = None, rating_info: dict | None = None, default_variant_id=None) -> dict:
    """`locale` added as a real defect fix, alongside `search()`'s own -- without this, a locale-aware search filter would still render every result card in the platform default language regardless of what was actually searched/matched. Defaults to `_DEFAULT_LOCALE` so the 3 other existing call sites (product detail, product list, admin list) are entirely unaffected.

    `include_variants` (Phase 09.3): closes a confirmed gap -- the
    public product detail response exposed no purchasable variant
    identifiers at all, making it impossible for a storefront to know
    what `product_variant_id` to send to Cart's own AddItem operation.
    Defaults to False so the list/admin call sites are unaffected;
    only `ProductDetailSelector.get_by_slug()` passes True, and only
    because it already prefetches `variants` (confirmed directly) --
    this adds zero new queries, not a new N+1. Only customer-safe
    fields are exposed (id, sku, is_default, status) -- no cost
    price, supplier data, or other internal fields, matching the
    exact safe field set already used by the admin-only variant
    payload elsewhere in this file.

    `price_info` (real, closed gap): the public product list/detail
    response never exposed a price at all -- confirmed directly from
    this function's own prior field set and from api.ts's own
    storefront-side docstring disclosing this exact omission. The
    caller resolves this in bulk (matching ProductAdmin.price_display's
    own is-default-variant convention) and passes it in here, keeping
    this function itself free of any cross-app query -- it only ever
    shapes a dict.
    """
    effective_locale = locale or _DEFAULT_LOCALE
    all_translations = list(row.translations.all())
    translation = next((t for t in all_translations if t.locale_code == effective_locale), None)
    if translation is None:
        # Real, closed gap: most call sites of _product_card() never
        # pass a locale at all, so effective_locale defaults to "en" --
        # for this Uzbekistan-targeted project, a product with only a
        # "uz" translation (the ordinary case) rendered a blank name on
        # every product card. Falls back to "uz", then whatever
        # translation actually exists, before finally accepting a
        # blank name only if the product truly has none at all.
        translation = next((t for t in all_translations if t.locale_code == "uz"), None) or (all_translations[0] if all_translations else None)
    # Family-level (shared) media only -- a variant-tagged photo belongs
    # to that variant's own gallery (_variant_summary), not the shared
    # fallback every variant would otherwise incorrectly inherit.
    primary_media = next((m for m in row.media.all() if m.media_role == "primary" and m.variant_id is None), None)
    if primary_media is None and default_variant_id is not None:
        # Real, closed gap: a product whose photos were only ever
        # tagged to its own default variant (never a separate,
        # family-level "primary" photo) previously showed the generic
        # fallback icon on every list/search/recommendation card --
        # confirmed directly against a real product (every photo
        # uploaded against the variant, `Product.media` empty at the
        # family level) -- even though its own Product Detail page
        # already correctly shows a real photo, via this exact same
        # "fall back to the selected variant's own gallery" rule
        # (see ProductPurchaseExperience.tsx's own `familyGallery`).
        # List/search cards carry no per-variant gallery at all, so
        # this resolves the same real fallback server-side instead.
        variant_media = [m for m in row.media.all() if m.variant_id == default_variant_id]
        primary_media = next((m for m in variant_media if m.media_role == "primary"), None) or (
            sorted(variant_media, key=lambda m: m.sort_order)[0] if variant_media else None
        )
    card = {
        "id": str(row.id),
        "slug": translation.slug if translation else str(row.id),
        # the URL slug in every language this product is translated into -- the storefront's hreflang
        # alternates and sitemap need /ru/products/<ru slug>, not the current language's slug under /ru
        "slugs": {t.locale_code: t.slug for t in all_translations if t.slug},
        "name": translation.name if translation else "",
        "status": row.status,
        "brand_id": str(row.brand_id) if row.brand_id else None,
        "category_id": str(row.category_id) if row.category_id else None,
        "primary_image_path": _resolve_media_url(primary_media.storage_path) if primary_media else None,
        "created_at": row.created_at.isoformat(),
        "price": price_info["amount"] if price_info else None,
        "currency": price_info["currency"] if price_info else None,
        **_discount_fields(price_info),
        "rating_average": rating_info["average"] if rating_info else None,
        "rating_count": rating_info["count"] if rating_info else 0,
        "default_variant_id": str(default_variant_id) if default_variant_id else None,
    }
    if include_variants:
        active_variants = [v for v in row.variants.all() if v.status == "active"]
        variant_ids = [v.id for v in active_variants]
        price_by_variant = bulk_variant_prices(variant_ids)
        stock_by_variant = _bulk_variant_stock_status(variant_ids)
        stores_by_variant = _bulk_variant_store_stock(variant_ids)
        card["variants"] = [_variant_summary(v, effective_locale, price_by_variant, stock_by_variant, stores_by_variant) for v in active_variants]
    if include_details:
        # Real, closed gap: the public detail response exposed no
        # description, gallery, or specifications at all -- confirmed
        # directly (ProductTranslation.description, ProductMedia, and
        # Product.specifications all already existed, fully modeled,
        # with zero public read endpoint ever surfacing them). Gated
        # behind `include_details` (mirrors `include_variants`'s own
        # precedent) so the list/search/recommendation card shape is
        # entirely unaffected -- only ProductDetailSelector.get_by_slug
        # passes this, and it already prefetches "translations"/"media".
        card["description"] = (translation.description if translation else "") or ""
        gallery_media = sorted(
            (m for m in row.media.all() if m.media_role in ("primary", "gallery") and m.variant_id is None),
            key=lambda m: (0 if m.media_role == "primary" else 1, m.sort_order),
        )
        card["gallery"] = [url for m in gallery_media if (url := _resolve_media_url(m.storage_path))]
        raw_specs = [s for s in (row.specifications or []) if isinstance(s, dict) and s.get("key") and s.get("value")]
        card["specifications"] = [
            {"key": spec["key"], "value": spec["value"]}
            for spec in sorted(raw_specs, key=lambda s: s.get("sort_order", 0))
        ]
        # Real, closed gap: supplement_facts_text_{uz,ru,en}/
        # warnings_text_{uz,ru,en}/directions_text_{uz,ru,en} already
        # existed on Product (confirmed: ProductAdmin's own fieldsets
        # already edit all 9), but no public read endpoint ever
        # surfaced them -- a customer could never see what's actually
        # in the product they're buying. Resolved per the same
        # locale-fallback chain the translation lookup above already
        # uses (never all 3 languages at once, and never blank when a
        # real value exists in a different locale).
        card["supplement_facts"] = _localized_text_field(row, "supplement_facts_text", effective_locale)
        card["warnings"] = _localized_text_field(row, "warnings_text", effective_locale)
        card["directions"] = _localized_text_field(row, "directions_text", effective_locale)
        default_variant = next((v for v in row.variants.all() if v.id == default_variant_id), None) or next((v for v in row.variants.all() if v.is_default), None)
        card["flavours"] = _resolve_flavour_switcher(row, card["slug"], effective_locale, default_variant)
        # serving facts (price per serving on the compare page, replenishment forecasts) and the training goals
        card["nutrition"] = {"serving_size_grams": row.nutrition_serving_size_grams, "servings_per_container": row.nutrition_servings_per_container, "calories": row.nutrition_calories}
        card["goals"] = list(row.goals or [])
    return card


def _localized_text_field(row, field_prefix: str, effective_locale: str) -> str | None:
    for loc in (effective_locale, "uz", "ru", "en"):
        value = getattr(row, f"{field_prefix}_{loc}", None)
        if value:
            return value
    return None


def _cards_with_price_and_rating(rows: list, locale: str | None = None) -> list[dict]:
    """
    Real, closed gap: `RecommendationSelector.for_product()`/
    `for_customer()` built every card via a bare `_product_card(p)` --
    with no `price_info`/`rating_info` ever resolved -- so the
    "related products" carousel showed `price: null, currency: null,
    rating_average: null, rating_count: 0` for every item regardless of
    that product's real price/rating. Reuses the exact same bulk
    resolution `CatalogSelector.list()` already relies on -- never a
    second, duplicate price/rating concept, and never a per-row query.
    """
    price_by_product_id = _bulk_default_variant_prices(rows)
    rating_by_product_id = _bulk_rating_summary([r.id for r in rows])
    default_variant_by_product_id = _bulk_default_variant_ids(rows)
    return _with_stock([
        _product_card(
            r, locale=locale, price_info=price_by_product_id.get(r.id), rating_info=rating_by_product_id.get(str(r.id)),
            default_variant_id=default_variant_by_product_id.get(r.id),
        )
        for r in rows
    ])


class RecommendationSelector:
    """
    Phase 02J: closes a confirmed gap. `ProductRecommendation`
    (`catalog_product_recommendations`), `RelatedProduct`, and
    `RelationType` (`MANUAL_CURATED`, `SIMILAR_CATEGORY`) already
    existed in the domain/infrastructure layers with zero Application
    Service, repository method, or view ever using them -- confirmed
    by repository-wide search before writing this class.

    Strategy, using only data and relations that already exist:
    1. `MANUAL_CURATED` rows for this product, ordered by `sort_order`
       -- staff-curated, highest precedence, reusing the existing
       table exactly as its own `relation_type` enum already implies.
    2. If none exist, a deterministic `SIMILAR_CATEGORY` fallback:
       other PUBLISHED products sharing the same `category_id`,
       excluding the product itself, ordered by `id` for a stable,
       reproducible tiebreak (Step 24) -- computed on the fly, not
       pre-populated, since materializing every product pair would be
       a far larger undertaking than this phase's own evidence
       justifies.

    Read-only throughout; no write, no event, no mutation of Product.
    Inventory-level (stock > 0) filtering is deliberately NOT applied
    -- no existing precedent for Products querying Inventory directly
    was found, and this phase's own scope is bounded to what the
    existing schema/relations already support (see the final report's
    own "Known Remaining Issues" for this disclosed limitation).
    """

    DEFAULT_LIMIT = 8

    def for_product(self, product_id: uuid.UUID, limit: int = DEFAULT_LIMIT, locale: str | None = None) -> list[dict]:
        limit = max(1, min(limit, 50))  # bounded, per Step 23 -- never unbounded

        curated = list(
            orm.ProductRecommendation.objects.filter(product_id=product_id, relation_type="manual_curated")
            .select_related("related_product")
            .prefetch_related("related_product__translations", "related_product__media", "related_product__variants")
            .order_by("sort_order", "related_product_id")[:limit]
        )
        if curated:
            rows = [c.related_product for c in curated if c.related_product.status == ProductStatus.PUBLISHED.value]
            return _cards_with_price_and_rating(rows, locale)

        # No staff pick: what customers actually buy together with it (co_purchase.py), then the same category's
        # best sellers that are in stock -- never an arbitrary (id-ordered) slice of the category.
        from apps.products.infrastructure import co_purchase
        from apps.products.infrastructure.smart_search import _in_stock_products, _units_sold_by_product

        together = co_purchase.related(product_id, limit)
        rows_by_id = {p.id: p for p in orm.Product.objects.filter(id__in=together, status=ProductStatus.PUBLISHED.value).prefetch_related("translations", "media", "variants")}
        picked = [rows_by_id[pid] for pid in together if pid in rows_by_id]

        product = orm.Product.objects.filter(id=product_id).only("id", "category_id").first()
        if product is not None and product.category_id is not None and len(picked) < limit:
            siblings = list(
                orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value, category_id=product.category_id)
                .exclude(id__in=[product_id, *[p.id for p in picked]])
                .prefetch_related("translations", "media", "variants")
            )
            sold = _units_sold_by_product()
            stocked = _in_stock_products([p.id for p in siblings])
            siblings.sort(key=lambda p: (str(p.id) not in stocked, -sold.get(str(p.id), 0), str(p.id)))
            picked += siblings[: limit - len(picked)]
        return _cards_with_price_and_rating(picked, locale)

    def for_customer(self, customer_id: uuid.UUID, limit: int = DEFAULT_LIMIT) -> list[dict]:
        """
        Phase 03B: closes the gap Phase 02J's own report explicitly
        disclosed as never implemented -- "no customer-specific signal
        was used at all", since no sufficiently-authoritative source
        was confirmed at the time. `OrderLineItemModel` (Ordering) and
        `ProductVariant`/`Product` (Products) are both fully built and
        tested; the cross-module join between them was simply never
        written for this purpose.

        Priority, matching this phase's own specified hierarchy:
        1. Category affinity: the customer's own most-purchased
           category, derived from COMPLETED orders' line items,
           resolved via `product_variant_id -> ProductVariant.product
           -> Product.category_id` -- two bounded, DB-aggregated
           queries (find the affinity category, then the products in
           it), never one query per line item.
        2. Fallback (no purchase history, or no category signal):
           popular PUBLISHED products, ranked by completed-order line
           count -- reusing the same cross-module join, not a second,
           duplicate popularity concept.
        3. Fallback (no order data exists at all): general active
           products, deterministic `id` ordering, matching
           `for_product()`'s own established tiebreak convention.

        Read-only; never trusts a client-supplied customer_id (callers
        must resolve this from the authenticated identity themselves,
        matching this phase's own explicit security rule).
        """
        from apps.ordering.domain.enums import OrderLineItemStatus, OrderStatus
        from apps.ordering.infrastructure import models as ordering_orm

        limit = max(1, min(limit, 50))

        purchased_variant_ids = list(
            ordering_orm.OrderLineItemModel.objects.filter(
                order__customer_id=customer_id, order__status=OrderStatus.COMPLETED.value, status=OrderLineItemStatus.ACTIVE.value,
            ).values_list("product_variant_id", flat=True).distinct()
        )

        if purchased_variant_ids:
            affinity_category = (
                orm.ProductVariant.objects.filter(id__in=purchased_variant_ids, product__status=ProductStatus.PUBLISHED.value)
                .values("product__category_id").annotate(purchase_count=Count("id")).order_by("-purchase_count").first()
            )
            if affinity_category and affinity_category["product__category_id"] is not None:
                candidates = list(
                    orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value, category_id=affinity_category["product__category_id"])
                    .prefetch_related("translations", "media", "variants")
                    .order_by("id")[:limit]
                )
                if candidates:
                    return _cards_with_price_and_rating(candidates)

        popular_product_ids = (
            ordering_orm.OrderLineItemModel.objects.filter(order__status=OrderStatus.COMPLETED.value, status=OrderLineItemStatus.ACTIVE.value)
            .values("product_variant_id").annotate(sold_count=Count("id")).order_by("-sold_count")
            .values_list("product_variant_id", flat=True)[: limit * 3]  # over-fetch variants since several may share one product, or be unpublished
        )
        if popular_product_ids:
            popular = list(
                orm.Product.objects.filter(variants__id__in=list(popular_product_ids), status=ProductStatus.PUBLISHED.value)
                .distinct().prefetch_related("translations", "media", "variants").order_by("id")[:limit]
            )
            if popular:
                return _cards_with_price_and_rating(popular)

        fallback = list(orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value).prefetch_related("translations", "media", "variants").order_by("id")[:limit])
        return _cards_with_price_and_rating(fallback)


_VARIANT_DISPLAY_LIMIT = 100


class VariantDisplaySelector:
    """
    Name/photo/size for a set of variant ids -- what an order or cart line needs
    to show a real product instead of a bare id (Order/Cart lines carry only
    `product_variant_id`). Not limited to PUBLISHED products: a customer's past
    order must still show what they bought after the product is hidden or
    archived; `is_published` tells the client whether linking to it makes sense.
    Only already-public catalog fields are exposed.
    """

    def resolve(self, variant_ids: list, locale: str | None = None) -> list[dict]:
        ids = []
        for raw in variant_ids[:_VARIANT_DISPLAY_LIMIT]:
            try:
                ids.append(uuid.UUID(str(raw)))
            except ValueError:
                continue
        if not ids:
            return []
        effective_locale = locale or _DEFAULT_LOCALE
        variants = (
            orm.ProductVariant.objects.filter(id__in=ids)
            .select_related("product", "product__brand", "package", "flavour")
            .prefetch_related("product__translations", "product__brand__translations", "package__translations", "flavour__translations", "media", "product__media")
        )
        return [self._display(v, effective_locale) for v in variants]

    @staticmethod
    def _display(variant: orm.ProductVariant, locale: str) -> dict:
        product = variant.product
        translations = list(product.translations.all())
        translation = (
            next((t for t in translations if t.locale_code == locale), None)
            or next((t for t in translations if t.locale_code == "uz"), None)
            or (translations[0] if translations else None)
        )
        brand_name = None
        if product.brand is not None:
            brand_translations = list(product.brand.translations.all())
            bt = next((t for t in brand_translations if t.locale_code == locale), None) or (brand_translations[0] if brand_translations else None)
            brand_name = bt.name if bt else None
        # Variant's own photo first, then the family-level primary photo.
        variant_media = sorted((m for m in variant.media.all() if m.media_role == "primary"), key=lambda m: m.sort_order)
        family_media = sorted((m for m in product.media.all() if m.media_role == "primary" and m.variant_id is None), key=lambda m: m.sort_order)
        media = (variant_media or family_media or [None])[0]
        return {
            "variant_id": str(variant.id),
            "product_id": str(product.id),
            "product_slug": translation.slug if translation else None,
            "product_name": translation.name if translation else "",
            "brand_name": brand_name,
            "image_url": _resolve_media_url(media.storage_path) if media else None,
            "weight_value": variant.weight_value,
            "weight_unit": variant.weight_unit,
            "package": _package_summary(variant.package, locale),
            "flavour": _flavour_summary(variant.flavour, locale) if variant.flavour_id else None,
            "variant_label": variant_label(variant, locale, package=False),
            "is_published": product.status == ProductStatus.PUBLISHED.value,
        }


def merged_product_target(slug: str) -> dict | None:
    """
    {"slug": <family slug>, "variant_id": <one of the moved variants>} when `slug` belongs to a product that was grouped
    into another one (Product.merged_into) -- old links, bookmarks and search results then land on the right variant.
    """
    old = (
        orm.Product.all_objects.filter(translations__slug=slug, merged_into__isnull=False)
        .select_related("merged_into").prefetch_related("merged_into__translations").first()
    )
    if old is None:
        return None
    target, hops = old.merged_into, 0
    while target is not None and target.merged_into_id and hops < 5:  # grouped again later
        target, hops = target.merged_into, hops + 1
    if target is None or target.status != ProductStatus.PUBLISHED.value:
        return None
    translations = list(target.translations.all())
    t = next((x for x in translations if x.locale_code == "uz"), None) or (translations[0] if translations else None)
    if t is None:
        return None
    from apps.products.infrastructure.product_grouping import moved_variant_of

    return {"slug": t.slug, "variant_id": moved_variant_of(old.id, target.id)}
