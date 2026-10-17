"""
Dashboard → Mahsulotlar → Guruhlash: suggested product families (same brand, same name apart from size and flavour)
and the review screen that merges the chosen products into one family -- see product_grouping.py.
"""
from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.products.domain.enums import WeightUnit
from apps.products.infrastructure import models as orm
from apps.products.infrastructure.product_grouping import group_suggestions, merge_products, preview_group

UNITS = [(u.value, u.value) for u in WeightUnit]


def _flavour_choices() -> list[tuple[str, str]]:
    rows = orm.Flavour.objects.filter(is_active=True).prefetch_related("translations").order_by("sort_order")
    out = []
    for f in rows:
        names = {t.locale_code: t.name for t in f.translations.all()}
        out.append((str(f.id), names.get("uz") or names.get("en") or f.slug, f.color_hex))
    return sorted(out, key=lambda x: x[1].lower())


@staff_member_required
def grouping_view(request):
    if not request.user.has_perm("products.change_product"):
        raise PermissionDenied
    ids = [i for i in (request.POST.get("ids") or request.GET.get("ids") or "").split(",") if i.strip()]

    if request.method == "POST" and ids:
        target = request.POST.get("target")
        names = {loc: (request.POST.get(f"name_{loc}") or "").strip() for loc in ("uz", "ru", "en")}
        flavours, sizes = {}, {}
        for key, value in request.POST.items():
            if key.startswith("flavour_"):
                flavours[key[8:]] = value or None
            elif key.startswith("size_value_"):
                vid = key[11:]
                raw = (value or "").replace(",", ".").strip()
                try:
                    number = float(raw) if raw else None
                except ValueError:
                    number = None
                if number:
                    sizes[vid] = (number, request.POST.get(f"size_unit_{vid}") or "g")
        try:
            result = merge_products(target, ids, names={k: v for k, v in names.items() if v}, variant_flavours=flavours, variant_sizes=sizes)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('admin:nz_product_grouping')}?ids={','.join(ids)}")
        messages.success(request, f"Guruhlandi: {result['merged'] + 1} ta mahsulot → bitta mahsulot, {result['variants']} ta variant (o'lcham × ta'm).")
        return redirect("admin:products_product_change", result["target_id"])

    context = {**admin.site.each_context(request), "title": "Guruhlash", "units": UNITS}
    if ids:
        try:
            preview = preview_group(ids, request.GET.get("target"))
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("admin:nz_product_grouping")
        products = {}
        for v in preview.variants:
            products.setdefault(v.product_id, v.product_name)
        context.update({
            "preview": preview, "ids": ",".join(ids), "flavours": _flavour_choices(),
            "products": [{"id": pid, "name": name, "is_target": pid == preview.target_id} for pid, name in products.items()],
            "product_list_url": reverse("admin:products_product_changelist"),
        })
        return render(request, "admin/products/grouping_preview.html", context)

    groups = group_suggestions()
    for g in groups:
        g["url"] = f"{reverse('admin:nz_product_grouping')}?ids={','.join(g['product_ids'])}"
    context.update({
        "groups": groups,
        "stats": [
            {"label": "Tavsiya etilgan guruh", "value": len(groups), "icon": "fa-layer-group", "tone": "#4f46e5"},
            {"label": "Birlashadigan mahsulot", "value": sum(len(g["product_ids"]) for g in groups), "icon": "fa-boxes-stacked", "tone": "#0ea5e9"},
            {"label": "Variant (o'lcham × ta'm)", "value": sum(g["variant_count"] for g in groups), "icon": "fa-swatchbook", "tone": "#16a34a"},
        ],
        "product_list_url": reverse("admin:products_product_changelist"),
    })
    return render(request, "admin/products/grouping.html", context)
