"""
Dashboard → Ombor → Hisobdan chiqarish: write-offs of damaged / expired / defective / lost goods (see writeoff_service.py).

Pages: the list (tabs, month KPIs, value by reason), "new write-off" (scan or search the location's stock;
nutrizone-writeoff.js), and the write-off act (dalolatnoma) with approve / reject / cancel.
Permissions: WriteOff model permissions; `approve_writeoff` deducts stock (managers).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext as _t

from apps.stores.infrastructure import stock_service, transfer_service, writeoff_service
from apps.stores.infrastructure.models import StoreKind, StoreProductStock, WriteOff, WriteOffItem, WriteOffReason, WriteOffStatus
from apps.stores.infrastructure.warehouse_admin import _actor, _body, _error, _local, _location_payload, _som
from common.exceptions import DomainException

STATUS_STYLE = {
    "pending": ("#f59e0b", "fa-hourglass-half"), "approved": ("#10b981", "fa-circle-check"),
    "rejected": ("#ef4444", "fa-circle-xmark"), "cancelled": ("#94a3b8", "fa-ban"),
}
REASON_STYLE = {
    "damaged": ("#ef4444", "fa-box-open"), "expired": ("#b91c1c", "fa-calendar-xmark"), "defect": ("#f97316", "fa-triangle-exclamation"),
    "lost": ("#7c3aed", "fa-user-secret"), "tester": ("#0ea5e9", "fa-flask"), "internal": ("#14b8a6", "fa-building"), "other": ("#64748b", "fa-circle-question"),
}


def reasons_payload() -> list[dict]:
    return [{"key": k, "label": str(v), "color": REASON_STYLE[k][0], "icon": REASON_STYLE[k][1]} for k, v in WriteOffReason.choices]


@admin.register(WriteOff)
class WriteOffAdmin(admin.ModelAdmin):
    list_display = ("number", "store", "status", "created_at")
    list_filter = ("status", "store")
    search_fields = ("number", "note", "created_by", "items__name", "items__sku", "items__barcode")
    list_per_page = 30
    ordering = ("-created_at",)
    change_list_template = "admin/wms/writeoff_list.html"

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("store").annotate(_lines=Count("items"))

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        reasons: dict = {}
        for wid, reason in WriteOffItem.objects.filter(write_off__in=[w.pk for w in cl.result_list]).values_list("write_off_id", "reason").distinct():
            reasons.setdefault(wid, []).append({"label": WriteOffReason(reason).label, "color": REASON_STYLE[reason][0]})
        for w in cl.result_list:
            color, icon = STATUS_STYLE.get(w.status, ("#64748b", "fa-circle"))
            w.nz = {"color": color, "icon": icon, "lines": w._lines, "created": _local(w.created_at), "decided": _local(w.decided_at),
                    "value": _som(w.total_value) if w.total_value else "", "reasons": reasons.get(w.pk, [])}
        return cl

    def changelist_view(self, request, extra_context=None):
        month = timezone.localtime(timezone.now()).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        approved = WriteOff.objects.filter(status=WriteOffStatus.APPROVED, decided_at__gte=month)
        agg = approved.aggregate(n=Count("id"), units=Sum("total_units"), value=Sum("total_value"))
        by_reason = []
        rows = WriteOffItem.objects.filter(write_off__in=approved).values("reason").annotate(units=Sum("quantity")).order_by("-units")
        values: dict = {}
        for i in WriteOffItem.objects.filter(write_off__in=approved).values("reason", "quantity", "unit_cost"):
            values[i["reason"]] = values.get(i["reason"], Decimal(0)) + i["quantity"] * i["unit_cost"]
        total_units = sum(r["units"] for r in rows) or 1
        for r in rows:
            color, icon = REASON_STYLE[r["reason"]]
            by_reason.append({"label": WriteOffReason(r["reason"]).label, "units": r["units"], "value": _som(values.get(r["reason"])), "color": color, "icon": icon,
                              "share": round(r["units"] * 100 / total_units)})
        current = request.GET.get("status__exact", "")
        counts = dict(WriteOff.objects.values_list("status").annotate(n=Count("id")))
        tabs = [{"key": "", "label": _t("All"), "n": sum(counts.values()), "color": "#64748b", "icon": "fa-layer-group", "on": not current}]
        for key, label in WriteOffStatus.choices:
            color, icon = STATUS_STYLE[key]
            tabs.append({"key": key, "label": label, "n": counts.get(key, 0), "color": color, "icon": icon, "on": current == key})
        extra = {
            "title": _t("Hisobdan chiqarish"), "nz_tabs": tabs, "nz_by_reason": by_reason,
            "nz_kpis": {"pending": counts.get(WriteOffStatus.PENDING, 0), "month": agg["n"] or 0, "units": agg["units"] or 0, "value": _som(agg["value"])},
            "can_create": request.user.has_perm("stores.add_writeoff"), "can_approve": request.user.has_perm("stores.approve_writeoff"),
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("new/", v(self.new_view), name="stores_writeoff_new"),
            path("new/post/", v(self.post_view), name="stores_writeoff_post"),
            path("<uuid:pk>/doc/", v(self.document_view), name="stores_writeoff_document"),
            path("<uuid:pk>/decide/", v(self.decide_view), name="stores_writeoff_decide"),
            *super().get_urls(),
        ]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("admin:stores_writeoff_document", args=[object_id]))

    def add_view(self, request, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("admin:stores_writeoff_new"))

    def _ctx(self, request, title):
        return {**self.admin_site.each_context(request), "opts": self.model._meta, "title": title}

    # ------------------------------------------------------------------ new
    def _prefill(self, request, store) -> list[dict]:
        """Lines handed over from another page (?variant=…&qty=…&reason=…&batch=…&expiry=…), e.g. the expiry panel."""
        ids = []
        for raw in request.GET.getlist("variant"):
            try:
                ids.append(uuid.UUID(raw))
            except ValueError:
                continue
        if not ids or store is None:
            return []
        from apps.stores.infrastructure.count_service import cost_map

        infos = stock_service.variant_infos(ids)
        avail = stock_service.available_map(store, ids)
        costs = cost_map(ids)
        reason = request.GET.get("reason") if request.GET.get("reason") in WriteOffReason.values else WriteOffReason.DAMAGED
        try:
            qty = max(1, int(request.GET.get("qty") or 1))
        except ValueError:
            qty = 1
        lines = []
        for vid in ids:
            info = infos.get(vid)
            if info is None:
                continue
            lines.append({"variant_id": str(vid), "name": info.name, "sku": info.sku, "barcode": info.barcode, "size": info.size, "image_url": info.image_url,
                          "available": avail.get(vid, 0), "cost": str(costs.get(vid) or 0), "quantity": min(qty, avail.get(vid, 0)) or 1, "reason": reason,
                          "batch": request.GET.get("batch", "")[:48] if len(ids) == 1 else "", "expiry": request.GET.get("expiry", "")[:10] if len(ids) == 1 else "", "note": ""})
        return lines

    def new_view(self, request):
        if not request.user.has_perm("stores.add_writeoff"):
            raise PermissionDenied
        locations = list(transfer_service.locations())
        store = next((s for s in locations if str(s.id) == request.GET.get("store")), None) or next((s for s in locations if s.kind == StoreKind.WAREHOUSE), None) or (locations[0] if locations else None)
        units = dict(StoreProductStock.objects.filter(quantity__gt=0).values_list("store").annotate(u=Sum("quantity")))
        return render(request, "admin/wms/writeoff_new.html", {
            **self._ctx(request, _t("New write-off")),
            "config": {
                "locations": [{**_location_payload(s), "units": units.get(s.id, 0)} for s in locations],
                "location": str(store.id) if store else None, "lines": self._prefill(request, store), "reasons": reasons_payload(),
                "can_approve": request.user.has_perm("stores.approve_writeoff"),
                "urls": {
                    "lookup": reverse("admin:stores_stocktransfer_lookup"), "search": reverse("admin:stores_stocktransfer_search"),
                    "post": reverse("admin:stores_writeoff_post"), "list": reverse("admin:stores_writeoff_changelist"),
                },
            },
            "i18n": {
                "scanPh": _t("Scan a barcode or type a product name…"), "scanHint": _t("1 scan = 1 unit"), "product": _t("Product"),
                "available": _t("Available"), "qty": _t("Quantity"), "reason": _t("Reason"), "batch": _t("Batch / expiry"), "note": _t("Comment"),
                "empty": _t("Scan the damaged or expired products, or find them by name. Only what the location has available can be written off."),
                "defaultReason": _t("Reason for scanned products"), "lines": _t("Products"), "units": _t("Units"), "value": _t("Value at cost"),
                "som": _t("so'm"), "submit": _t("Send for approval"), "approveNow": _t("Write off now"), "notePh": _t("Note for the act (optional)"),
                "notFound": _t("Bu shtrix-kod bo'yicha mahsulot topilmadi."), "noStock": _t("Not available at this location"), "error": _t("Could not save. Please try again."),
                "tooMany": _t("Only %s available"), "changeLoc": _t("Changing the location clears the list. Continue?"), "remove": _t("Remove"),
                "where": _t("Where are the goods?"), "cancel": _t("Cancel"), "pcs": _t("pcs"), "nothing": _t("Nothing found"), "noCost": _t("no cost"),
                "pendingNote": _t("The units are set aside at once (not sellable) and leave stock when a manager approves."),
            },
        })

    def post_view(self, request):
        if request.method != "POST" or not request.user.has_perm("stores.add_writeoff"):
            raise PermissionDenied
        b = _body(request)
        approve = bool(b.get("approve"))
        if approve and not request.user.has_perm("stores.approve_writeoff"):
            return JsonResponse({"ok": False, "error": {"code": "FORBIDDEN", "message": _t("Bu amal uchun sizda ruxsat yo'q.")}}, status=403)
        actor = _actor(request)
        try:
            w = writeoff_service.create(b.get("location"), actor, b.get("lines") or [], note=str(b.get("note") or ""))
            if approve:
                writeoff_service.approve(w.id, actor)
        except DomainException as exc:
            return _error(exc)
        return JsonResponse({"ok": True, "data": {"number": w.number, "url": reverse("admin:stores_writeoff_document", args=[w.pk])}})

    # ------------------------------------------------------------------ document + decision
    def document_view(self, request, pk):
        w = get_object_or_404(WriteOff.objects.select_related("store"), pk=pk)
        items = list(w.items.all())
        infos = stock_service.variant_infos([i.product_variant_id for i in items])
        rows = [{"n": n, "i": i, "info": infos.get(i.product_variant_id), "value": _som(i.unit_cost * i.quantity) if i.unit_cost else "",
                 "color": REASON_STYLE[i.reason][0]} for n, i in enumerate(items, 1)]
        color, icon = STATUS_STYLE.get(w.status, ("#64748b", "fa-circle"))
        user = request.user
        pending = w.status == WriteOffStatus.PENDING
        return render(request, "admin/wms/writeoff_document.html", {
            **self._ctx(request, w.number), "w": w, "rows": rows, "color": color, "icon": icon, "created": _local(w.created_at), "decided": _local(w.decided_at),
            "value": _som(w.total_value) if w.total_value else "",
            "can_approve": pending and user.has_perm("stores.approve_writeoff"),
            "can_cancel": pending and (user.has_perm("stores.approve_writeoff") or w.created_by == _actor(request)),
        })

    def decide_view(self, request, pk):
        if request.method != "POST":
            raise PermissionDenied
        w = get_object_or_404(WriteOff, pk=pk)
        action, note, actor, user = request.POST.get("action"), request.POST.get("note", ""), _actor(request), request.user
        allowed = {"approve": user.has_perm("stores.approve_writeoff"), "reject": user.has_perm("stores.approve_writeoff"),
                   "cancel": user.has_perm("stores.approve_writeoff") or (user.has_perm("stores.add_writeoff") and w.created_by == actor)}
        if not allowed.get(action):
            raise PermissionDenied
        try:
            getattr(writeoff_service, action)(w.id, actor, note)
        except DomainException as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, {"approve": _t("Write-off approved -- the units left stock."), "reject": _t("Write-off rejected -- the units are sellable again."),
                                       "cancel": _t("Write-off cancelled -- the units are sellable again.")}[action])
        return HttpResponseRedirect(reverse("admin:stores_writeoff_document", args=[w.pk]))

