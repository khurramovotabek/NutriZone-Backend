"""
Branch-to-branch stock transfers in the dashboard (Ombor -> Transferlar).

Staff pick a sending and a receiving branch (real Stores -- see
inventory_view.py's module docstring for why a warehouse id IS a Store
id), find products by name (the storefront's smart search: typos,
transliteration, three languages) or by barcode/SKU, enter quantities
and confirm. The move itself is TransferStockBetweenBranches
(apps/inventory/application/services/branch_transfers.py): one atomic,
all-or-nothing document that goes through the stock ledger.
"""
from __future__ import annotations

import json
import uuid

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.platform.infrastructure.inventory_view import _actor_id, _resolve_stock_images

SEARCH_LIMIT = 40
BROWSE_PAGE_SIZE = 24


# --------------------------------------------------------------------------
# Lookups (batched -- never one query per row)
# --------------------------------------------------------------------------


def _branches() -> list[dict]:
    """Every real branch with its current total AVAILABLE units, for the two selects."""
    from apps.inventory.infrastructure.models import WarehouseInventoryModel
    from apps.stores.infrastructure.models import Store

    totals = {
        str(row["warehouse_id"]): row["units"]
        for row in WarehouseInventoryModel.objects.values("warehouse_id").annotate(units=Sum("available_quantity"))
    }
    return [
        {"id": str(s.id), "name": s.name, "status": s.status, "units": totals.get(str(s.id), 0) or 0}
        for s in Store.objects.order_by("name")
    ]


def _branch_names() -> dict[str, str]:
    from apps.stores.infrastructure.models import Store

    return {str(s.id): s.name for s in Store.objects.only("id", "name")}


def _product_names(product_ids) -> dict:
    """Name in the dashboard's current language, falling back to English, then to any translation."""
    from apps.products.infrastructure.models import ProductTranslation

    lang = (get_language() or "en")[:2]
    ranked: dict = {}
    for t in ProductTranslation.objects.filter(product_id__in=set(product_ids)).only("product_id", "locale_code", "name"):
        if not t.name:
            continue
        rank = 0 if t.locale_code == lang else 1 if t.locale_code == "en" else 2
        if t.product_id not in ranked or rank < ranked[t.product_id][0]:
            ranked[t.product_id] = (rank, t.name)
    return {pid: name for pid, (_rank, name) in ranked.items()}


def _brand_names(products) -> dict:
    from apps.products.infrastructure.models import BrandTranslation

    brand_ids = {p.brand_id for p in products if p.brand_id}
    names: dict = {}
    for t in BrandTranslation.objects.filter(brand_id__in=brand_ids).only("brand_id", "locale_code", "name"):
        if t.name and (t.brand_id not in names or t.locale_code == "en"):
            names[t.brand_id] = t.name
    return {p.id: names.get(p.brand_id) for p in products}


def _weight_label(variant) -> str | None:
    if not variant.weight_value:
        return None
    value = variant.weight_value
    unit = variant.weight_unit or "g"
    if unit in ("g", "gram") and value >= 1000:
        return f"{value / 1000:g} kg"
    short = {"gram": "g", "kilogram": "kg", "pound": "lb", "ounce": "oz", "milliliter": "ml", "liter": "l"}.get(unit, unit)
    return f"{value:g} {short}"


def _variant_rows(variants: list, source_id: str | None, destination_id: str | None) -> list[dict]:
    """Card data for each variant: name, brand, size, photo, barcode/SKU and stock at both chosen branches."""
    from apps.inventory.infrastructure.models import InventoryModel, WarehouseInventoryModel

    if not variants:
        return []
    variant_ids = [v.id for v in variants]
    inventory_by_variant = dict(InventoryModel.objects.filter(product_variant_id__in=variant_ids).values_list("product_variant_id", "id"))
    stock: dict = {}
    branch_ids = [b for b in (source_id, destination_id) if b]
    if branch_ids and inventory_by_variant:
        for row in WarehouseInventoryModel.objects.filter(inventory_id__in=inventory_by_variant.values(), warehouse_id__in=branch_ids).values("inventory_id", "warehouse_id", "available_quantity"):
            stock[(row["inventory_id"], str(row["warehouse_id"]))] = row["available_quantity"]

    products = {v.product_id: v.product for v in variants}
    names = _product_names(products.keys())
    brands = _brand_names(products.values())
    images = _resolve_stock_images({str(v.id): v for v in variants})

    rows = []
    for v in variants:
        inv_id = inventory_by_variant.get(v.id)
        rows.append({
            "variant_id": str(v.id),
            "name": names.get(v.product_id) or v.sku,
            "brand": brands.get(v.product_id),
            "size": _weight_label(v),
            "sku": v.sku,
            "barcode": v.barcode,
            "image_url": images.get(str(v.id)),
            "source_available": stock.get((inv_id, source_id), 0) if inv_id and source_id else 0,
            "destination_available": stock.get((inv_id, destination_id), 0) if inv_id and destination_id else 0,
        })
    return rows


def _parse_branch(value) -> str | None:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


@staff_member_required
def stock_transfer_view(request):
    """The transfer workspace: new-transfer builder on top, transfer history underneath."""
    from apps.inventory.infrastructure.models import StockTransferModel

    branches = _branches()
    names = {b["id"]: b["name"] for b in branches}

    branch_filter = _parse_branch(request.GET.get("branch"))
    history = StockTransferModel.objects.annotate(line_count=Count("lines"))
    if branch_filter:
        history = history.filter(Q(source_warehouse_id=branch_filter) | Q(destination_warehouse_id=branch_filter))
    page = Paginator(history.order_by("-completed_at"), 15).get_page(request.GET.get("page"))
    for t in page.object_list:
        t.source_name = names.get(str(t.source_warehouse_id), _("Unknown branch"))
        t.destination_name = names.get(str(t.destination_warehouse_id), _("Unknown branch"))

    now = timezone.localtime()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = StockTransferModel.objects.filter(completed_at__gte=start_of_day.replace(day=1))
    context = {
        **admin.site.each_context(request),
        "title": _("Stock transfers"),
        "branches": branches,
        "history": page,
        "branch_filter": branch_filter or "",
        "stats": {
            "today": StockTransferModel.objects.filter(completed_at__gte=start_of_day).count(),
            "month": month.count(),
            "month_units": month.aggregate(u=Sum("total_units"))["u"] or 0,
            "all": StockTransferModel.objects.count(),
        },
        "i18n": {
            "chooseBranches": _("Choose the sending and receiving branch first."),
            "sameBranch": _("The sending and receiving branch must be different."),
            "inStock": _("in stock"),
            "atDestination": _("at receiver"),
            "outOfStock": _("Out of stock here"),
            "add": _("Add"),
            "added": _("Added"),
            "noResults": _("Nothing found. Try another name, a barcode or SKU."),
            "emptyBranch": _("This branch has no products in stock."),
            "searchFailed": _("Search failed. Please try again."),
            "maxReached": _("Only %(n)s available at the sending branch."),
            "units": _("pcs"),
            "products": _("products"),
            "confirmTitle": _("Confirm transfer"),
            "sending": _("Transferring..."),
            "done": _("Transfer completed"),
            "failed": _("The transfer could not be completed."),
            "shortage": _("Not enough stock at the sending branch:"),
            "requested": _("requested"),
            "available": _("available"),
            "prev": _("Previous"),
            "next": _("Next"),
            "page": _("Page"),
            "exactMatch": _("Barcode match"),
            "searchResults": _("Search results"),
            "atSource": _("Products at the sending branch"),
            "view": _("Open document"),
            "newTransfer": _("New transfer"),
        },
    }
    return render(request, "admin/stock_transfers.html", context)


@staff_member_required
def stock_transfer_detail_view(request, transfer_id):
    from apps.inventory.infrastructure.models import StockTransferModel
    from apps.products.infrastructure.models import ProductVariant

    transfer = StockTransferModel.objects.filter(id=transfer_id).prefetch_related("lines").first()
    if transfer is None:
        raise Http404(_("Transfer not found."))
    names = _branch_names()
    lines = list(transfer.lines.all())
    # all_objects: a document keeps showing a product even after it was later removed from the catalog
    variants = list(ProductVariant.all_objects.filter(id__in=[ln.product_variant_id for ln in lines]).select_related("product"))
    cards = {row["variant_id"]: row for row in _variant_rows(variants, None, None)}
    rows = []
    for ln in lines:
        card = cards.get(str(ln.product_variant_id), {})
        rows.append({**card, "quantity": ln.quantity, "source_after": ln.source_balance_after, "destination_after": ln.destination_balance_after, "source_before": ln.source_balance_after + ln.quantity, "destination_before": ln.destination_balance_after - ln.quantity})

    context = {
        **admin.site.each_context(request),
        "title": f"{_('Transfer')} {transfer.number}",
        "transfer": transfer,
        "source_name": names.get(str(transfer.source_warehouse_id), _("Unknown branch")),
        "destination_name": names.get(str(transfer.destination_warehouse_id), _("Unknown branch")),
        "rows": rows,
    }
    return render(request, "admin/stock_transfer_detail.html", context)


# --------------------------------------------------------------------------
# JSON API used by the page
# --------------------------------------------------------------------------


@staff_member_required
@require_GET
def transfer_api_products(request):
    """
    `?q=&source=&destination=&page=` -- a barcode/SKU typed or scanned
    exactly returns that one variant; any other text goes through the
    storefront's smart search (partial words, typos, uz/ru/en
    transliteration), best sellers first. An empty query lists what the
    sending branch actually has in stock, paginated.
    """
    from apps.inventory.infrastructure.models import WarehouseInventoryModel
    from apps.products.infrastructure import smart_search
    from apps.products.infrastructure.models import ProductVariant

    q = request.GET.get("q", "").strip()
    source_id = _parse_branch(request.GET.get("source"))
    destination_id = _parse_branch(request.GET.get("destination"))
    base = ProductVariant.objects.select_related("product")

    if q:
        from apps.products.infrastructure import barcodes

        match = barcodes.resolve(q)
        exact = list(base.filter(pk=match.variant.pk)[:1]) if match else []
        if exact:
            return JsonResponse({"success": True, "data": {"mode": "exact", "results": _variant_rows(exact, source_id, destination_id), "total_count": 1}})

        ranked_ids = smart_search.search(q).product_ids[:SEARCH_LIMIT]
        rank = {pid: i for i, pid in enumerate(ranked_ids)}
        variants = list(base.filter(Q(product_id__in=ranked_ids) | Q(sku__icontains=q) | Q(barcode__startswith=q))[: SEARCH_LIMIT * 2])
        variants.sort(key=lambda v: (rank.get(str(v.product_id), len(rank)), not v.is_default, v.sku))
        rows = _variant_rows(variants[:SEARCH_LIMIT], source_id, destination_id)
        # what can actually be sent comes first, keeping the relevance order inside each group
        rows.sort(key=lambda r: r["source_available"] <= 0)
        return JsonResponse({"success": True, "data": {"mode": "search", "results": rows, "total_count": len(rows)}})

    if not source_id:
        return JsonResponse({"success": True, "data": {"mode": "browse", "results": [], "total_count": 0}})

    in_stock = (
        WarehouseInventoryModel.objects.filter(warehouse_id=source_id, available_quantity__gt=0)
        .order_by("-available_quantity", "inventory__code")
        .values_list("inventory__product_variant_id", flat=True)
    )
    page = Paginator(in_stock, BROWSE_PAGE_SIZE).get_page(request.GET.get("page"))
    variant_ids = list(page.object_list)
    order = {vid: i for i, vid in enumerate(variant_ids)}
    variants = sorted(base.filter(id__in=variant_ids), key=lambda v: order.get(v.id, 0))
    return JsonResponse({"success": True, "data": {
        "mode": "browse", "results": _variant_rows(variants, source_id, destination_id),
        "total_count": page.paginator.count, "page": page.number, "num_pages": page.paginator.num_pages,
    }})


@staff_member_required
@require_POST
def transfer_api_create(request):
    """`{"source": uuid, "destination": uuid, "note": str, "lines": [{"variant_id": uuid, "quantity": int}]}` -> the completed transfer document."""
    from apps.inventory.domain.transfers import TransferLineRequest, TransferShortage
    from apps.inventory.infrastructure import composition as inventory_composition
    from apps.stores.infrastructure.models import Store
    from common.exceptions import DomainException

    try:
        body = json.loads(request.body)
        source_id = uuid.UUID(str(body["source"]))
        destination_id = uuid.UUID(str(body["destination"]))
        lines = [TransferLineRequest(product_variant_id=uuid.UUID(str(ln["variant_id"])), quantity=int(ln["quantity"])) for ln in body.get("lines") or []]
        note = str(body.get("note") or "")
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"success": False, "error": {"code": "INVALID_REQUEST", "message": _("Invalid request.")}}, status=400)

    if Store.objects.filter(id__in=[source_id, destination_id]).count() != len({source_id, destination_id}):
        return JsonResponse({"success": False, "error": {"code": "UNKNOWN_BRANCH", "message": _("Unknown branch.")}}, status=422)

    actor_name = request.user.get_full_name() or request.user.get_username()
    try:
        transfer = inventory_composition.build_transfer_between_branches(_actor_id(request)).execute(
            source_warehouse_id=source_id, destination_warehouse_id=destination_id, lines=lines, note=note, actor_name=actor_name,
        )
    except TransferShortage as exc:
        from apps.products.infrastructure.models import ProductVariant

        variants = {v.id: v for v in ProductVariant.objects.filter(id__in=[s.product_variant_id for s in exc.shortages]).select_related("product")}
        names = _product_names({v.product_id for v in variants.values()})
        shortages = [
            {"variant_id": str(s.product_variant_id), "name": names.get(variants[s.product_variant_id].product_id) if s.product_variant_id in variants else str(s.product_variant_id)[:8], "requested": s.requested, "available": s.available}
            for s in exc.shortages
        ]
        return JsonResponse({"success": False, "error": {"code": exc.code, "message": _("Not enough stock at the sending branch."), "shortages": shortages}}, status=422)
    except DomainException as exc:
        messages = {
            "SAME_BRANCH_TRANSFER": _("The sending and receiving branch must be different."),
            "EMPTY_TRANSFER": _("Add at least one product to the transfer."),
            "INVALID_TRANSFER_QUANTITY": _("Each quantity must be a whole number greater than zero."),
        }
        return JsonResponse({"success": False, "error": {"code": exc.code, "message": messages.get(exc.code, str(exc))}}, status=422)

    from django.urls import reverse

    return JsonResponse({"success": True, "data": {
        "id": str(transfer.id), "number": transfer.number, "total_units": transfer.total_units, "line_count": len(transfer.lines),
        "url": reverse("admin:nz_stock_transfer_detail", args=[transfer.id]),
    }}, status=201)
