"""
Inventory admin dashboard -- mirrors reports_view.py's/pos_view.py's
own established pattern: a real, staff-only view backed directly by
StockSelector (apps/inventory/infrastructure/selectors.py), which
already existed and is already exercised by reports.py's own
inventory_report().

Real product names/prices are resolved via a loose, cross-app UUID
lookup (product_variant_id -> ProductVariant -> Product -> translation
/ PriceListEntryModel), matching the same established pattern used for
User.avatar_preview/Category.image/ProductVariantInline's real
price-stock resolution, and pos_view.py's own identical resolution for
the POS Terminal's product cards.

No standalone Warehouse model exists in this codebase (Store/Branch
was removed as its own module) -- `WarehouseInventoryModel.warehouse_id`
is a bare, cross-app UUID reference, per this project's own convention.
As of the data migration `apps/inventory/infrastructure/migrations/
0003_link_warehouse_to_real_store.py`, every real warehouse id
genuinely IS a real `apps.stores.Store`'s own id -- "filial" (branch),
in the site owner's own words, means exactly that real Store. Labels
resolve the real Store name first; only a warehouse id with no
matching Store (which should not happen after that migration, but is
handled defensively rather than crashing) falls back to a generic,
sorted "Filial N" placeholder.
"""
from __future__ import annotations

import uuid

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST


def _actor_id(request) -> uuid.UUID:
    """Deterministic Django-admin-staff-user -> UUID mapping, matching pos_view.py's own identical `_actor_id` (Sale/WarehouseInventory both key their actor by a free UUID, never Django's own integer User pk)."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"nutrizone-admin-staff-{request.user.id}")


def _resolve_variant_product_names(inventory_ids_to_variant_ids: dict) -> dict:
    """Bulk-resolves {inventory_id: "Product Name (SKU)"} in a small, fixed number of queries -- never per-row."""
    from apps.products.infrastructure.models import ProductTranslation, ProductVariant

    variant_ids = list(inventory_ids_to_variant_ids.values())
    variants = {v.id: v for v in ProductVariant.objects.filter(id__in=variant_ids).select_related("product")}
    product_ids = [v.product_id for v in variants.values()]
    names = {t.product_id: t.name for t in ProductTranslation.objects.filter(product_id__in=product_ids, locale_code="en")}

    resolved = {}
    for inv_id, variant_id in inventory_ids_to_variant_ids.items():
        variant = variants.get(variant_id)
        if variant is None:
            resolved[inv_id] = str(variant_id)[:8]
            continue
        product_name = names.get(variant.product_id, str(variant.product_id)[:8])
        resolved[inv_id] = f"{product_name} ({variant.sku})"
    return resolved


def _warehouse_labels() -> dict:
    """Every real, distinct warehouse id that actually exists, labeled with its real Store name when the id matches one (the normal case after migration 0003) -- a stable, sorted "Filial N" placeholder only for the defensive fallback case."""
    from apps.inventory.infrastructure.models import WarehouseInventoryModel
    from apps.stores.infrastructure.models import Store

    distinct_ids = sorted(str(w) for w in WarehouseInventoryModel.objects.values_list("warehouse_id", flat=True).distinct())
    store_names = {str(s.id): s.name for s in Store.objects.filter(id__in=distinct_ids)}
    fallback_counter = 0
    labels = {}
    for wid in distinct_ids:
        if wid in store_names:
            labels[wid] = store_names[wid]
        else:
            fallback_counter += 1
            labels[wid] = f"Filial {fallback_counter}"
    return labels


def _resolve_stock_images(variants: dict) -> dict:
    """
    Real, closed gap: the stock table showed product name/SKU as plain
    text with no photo at all, unlike every other product list in this
    codebase (catalog, POS, search). Resolves each variant's own
    tagged primary photo first, falling back to the parent product's
    family-level primary photo -- the identical fallback chain
    `apps.products.infrastructure.selectors._product_card` already
    uses for the public storefront, just reapplied here since this
    admin view builds its own row shape rather than reusing that
    function directly. Batched by product_id (one query for the whole
    page), never per-row.
    """
    from apps.products.infrastructure.models import ProductMedia

    product_ids = [v.product_id for v in variants.values()]
    variant_ids = [v.id for v in variants.values()]
    media_qs = ProductMedia.objects.filter(product_id__in=product_ids, media_role__in=("primary", "gallery")).order_by("sort_order")

    by_variant: dict = {}
    by_product: dict = {}
    for m in media_qs:
        if m.variant_id and m.variant_id in variant_ids:
            by_variant.setdefault(m.variant_id, []).append(m)
        elif m.variant_id is None:
            by_product.setdefault(m.product_id, []).append(m)

    def _best(media_list: list) -> str | None:
        primary = next((m for m in media_list if m.media_role == "primary"), None)
        chosen = primary or (media_list[0] if media_list else None)
        if chosen is None:
            return None
        path = (chosen.thumbnail_paths or {}).get("small") or chosen.storage_path
        return f"/media/{path}"

    result = {}
    for variant_id_str, variant in variants.items():
        result[variant_id_str] = _best(by_variant.get(variant.id, [])) or _best(by_product.get(variant.product_id, []))
    return result


def _enrich_stock_rows(rows: list[dict]) -> list[dict]:
    """Attaches real product name/SKU/price/photo and human warehouse labels onto StockSelector.list_all()'s own inventory-native rows -- the one, shared enrichment step for both the initial page render and the AJAX search endpoint below."""
    from apps.products.infrastructure.models import ProductTranslation, ProductVariant
    from apps.products.infrastructure.selectors import bulk_variant_prices

    variant_ids = [row["product_variant_id"] for row in rows]
    variants = {str(v.id): v for v in ProductVariant.objects.filter(id__in=variant_ids).select_related("product")}
    product_ids = [v.product_id for v in variants.values()]
    names = {t.product_id: t.name for t in ProductTranslation.objects.filter(product_id__in=product_ids, locale_code="en")}
    # bulk_variant_prices() keys its result by real UUID objects (the ORM's own field type) -- every other lookup in this function is by string, so this is normalized right here rather than leaking the mismatch into the loop below.
    prices = {str(k): v for k, v in bulk_variant_prices(variant_ids).items()}
    labels = _warehouse_labels()
    images = _resolve_stock_images(variants)

    for row in rows:
        variant = variants.get(row["product_variant_id"])
        row["sku"] = variant.sku if variant else None
        row["product_name"] = names.get(variant.product_id, row["code"]) if variant else row["code"]
        row["image_url"] = images.get(row["product_variant_id"])
        price_info = prices.get(row["product_variant_id"])
        row["price"] = price_info["amount"] if price_info else None
        row["currency"] = price_info["currency"] if price_info else None
        for entry in row["by_warehouse"]:
            entry["label"] = labels.get(entry["warehouse_id"], entry["warehouse_id"][:8])
        row["by_warehouse"].sort(key=lambda e: e["label"])
    return rows


def _search_variant_ids(search: str) -> list:
    """Real product-name/SKU search -- Inventory has no name field of its own (see StockSelector.list_all()'s own docstring), so this resolves matching ProductVariant ids first, then the caller filters Inventory rows by them."""
    from django.db.models import Q

    from apps.products.infrastructure.models import ProductVariant

    return list(ProductVariant.objects.filter(Q(sku__icontains=search) | Q(product__translations__name__icontains=search)).values_list("id", flat=True).distinct())


@staff_member_required
def inventory_dashboard_view(request):
    from apps.inventory.infrastructure.models import InventoryModel
    from apps.inventory.infrastructure.selectors import StockSelector

    selector = StockSelector()
    low_stock_items, low_stock_total = selector.low_stock(page=1, page_size=50)
    expiring_batches = selector.expiring_batches(within_days=30)
    system_totals = selector.system_totals()

    # Resolve real product names for the low-stock table -- bulk, not per-row.
    inventory_ids = [item["inventory_id"] for item in low_stock_items]
    variant_ids_by_inventory = dict(InventoryModel.objects.filter(id__in=inventory_ids).values_list("id", "product_variant_id"))
    variant_ids_by_inventory = {str(k): v for k, v in variant_ids_by_inventory.items()}
    product_names = _resolve_variant_product_names(variant_ids_by_inventory)
    for item in low_stock_items:
        item["product_name"] = product_names.get(item["inventory_id"], item["code"])

    total_active = InventoryModel.objects.filter(status="active").count()
    out_of_stock_total = sum(1 for item in low_stock_items if item["available_quantity"] == 0)

    labels = _warehouse_labels()
    warehouse_summaries = [{"warehouse_id": wid, "label": labels[wid], "total_units": total} for wid, total in system_totals["by_warehouse"].items()]
    warehouse_summaries.sort(key=lambda w: w["label"])

    context = {
        **admin.site.each_context(request),
        "title": _("Inventory"),
        "total_active": total_active,
        "low_stock_total": low_stock_total,
        "out_of_stock_total": out_of_stock_total,
        "expiring_total": len(expiring_batches),
        "low_stock_items": low_stock_items,
        "expiring_batches": expiring_batches,
        "total_units_system_wide": system_totals["total_units"],
        "warehouse_count": len(warehouse_summaries),
        "warehouse_summaries": warehouse_summaries,
    }
    return render(request, "admin/inventory_dashboard.html", context)


def _scope_rows_to_warehouse(rows: list[dict], warehouse_id: str) -> None:
    """
    Real, product-required capability: the branch/store selector's
    whole point -- when the site owner picks one specific "filial"
    (real Store), each row's own number must become THAT store's
    stock, not the system-wide sum across every store. Mutates rows
    in place (the same shape `_enrich_stock_rows` already built),
    never hides a row just because it happens to be zero in this one
    store (the product still exists in the catalog; a genuinely
    unstocked-here row correctly shows 0, not disappears).
    """
    for row in rows:
        entry = next((e for e in row["by_warehouse"] if e["warehouse_id"] == warehouse_id), None)
        row["total_available"] = entry["available_quantity"] if entry else 0
        row["by_warehouse"] = [entry] if entry else []


@staff_member_required
@require_GET
def inventory_api_stock_list(request):
    """Searchable, paginated product/stock table -- backs the dashboard's own live search (mirrors the POS Terminal's identical `pos_api_search`/`pos_api_browse` pattern). `warehouse_id` (real Store id, or absent/"all" for the system-wide aggregate) scopes every row's shown quantity to that one branch."""
    from apps.inventory.infrastructure.selectors import StockSelector

    q = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))
    warehouse_id = request.GET.get("warehouse_id", "").strip()
    product_variant_ids = _search_variant_ids(q) if q else None
    if q and not product_variant_ids:
        return JsonResponse({"success": True, "data": {"results": [], "total_count": 0}})

    rows, total = StockSelector().list_all(page=page, page_size=24, product_variant_ids=product_variant_ids)
    rows = _enrich_stock_rows(rows)
    if warehouse_id and warehouse_id != "all":
        _scope_rows_to_warehouse(rows, warehouse_id)
    return JsonResponse({"success": True, "data": {"results": rows, "total_count": total}})


@staff_member_required
@require_POST
def inventory_api_adjust_stock(request):
    """
    `POST /django-admin/inventory/api/adjust-stock` -- the stock list's
    own inline "edit the number directly" capability. Takes the exact
    NEW quantity (what the input now shows), computes the real delta
    against the row's current `available_quantity`, and applies it
    through the certified `AdjustStock` service -- same ledger/negative-
    stock-guard path as POS/Ordering, never a raw field write.
    """
    import json

    from apps.inventory.infrastructure import composition as inventory_composition
    from apps.inventory.infrastructure.models import WarehouseInventoryModel
    from common.exceptions import DomainException

    try:
        body = json.loads(request.body)
        warehouse_inventory_id = uuid.UUID(str(body["warehouse_inventory_id"]))
        new_quantity = int(body["quantity"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "error": {"message": "Invalid request."}}, status=400)

    if new_quantity < 0:
        return JsonResponse({"success": False, "error": {"message": "Quantity cannot be negative."}}, status=422)

    row = WarehouseInventoryModel.objects.filter(id=warehouse_inventory_id).first()
    if row is None:
        return JsonResponse({"success": False, "error": {"message": "Not found."}}, status=404)

    delta = new_quantity - row.available_quantity
    if delta != 0:
        try:
            inventory_composition.build_adjust_stock(_actor_id(request)).execute(
                warehouse_inventory_id=row.id, stock_status="available", quantity_delta=delta,
                reason="admin_manual_adjustment", reference="inventory_dashboard",
            )
        except DomainException as exc:
            return JsonResponse({"success": False, "error": {"message": str(exc)}}, status=422)
        row.refresh_from_db(fields=["available_quantity"])

    return JsonResponse({"success": True, "data": {"quantity": row.available_quantity}})


_original_get_app_list = admin.site.get_app_list


def _get_app_list_with_inventory(request, app_label=None):
    """
    Gives Inventory its own top-level sidebar group. Jazzmin builds the
    sidebar from `available_apps` (i.e. this method), and Inventory has
    no registered ModelAdmin (see inventory/infrastructure/admin.py), so
    without this it never gets an entry of its own. The group carries no
    models -- its one link (the Stock Dashboard) comes from
    JAZZMIN_SETTINGS["custom_links"]["inventory"].
    """
    app_list = _original_get_app_list(request, app_label)
    if app_label is not None or not request.user.is_active or not request.user.is_staff:
        return app_list
    if any(app["app_label"] == "inventory" for app in app_list):
        return app_list
    from django.urls import reverse

    return app_list + [
        {
            "name": _("Inventory"),
            "app_label": "inventory",
            "app_url": reverse("admin:nz_inventory_dashboard"),
            "has_module_perms": True,
            "models": [],
        }
    ]


def install_sidebar_entry() -> None:
    """Called once from PlatformConfig.ready() -- idempotent (safe if ready() ever runs twice)."""
    admin.site.get_app_list = _get_app_list_with_inventory
