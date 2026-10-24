"""Narxlarni qayta baholash on the dashboard: document list, the builder (add page) and the document page (change page)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import get_language

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.premium_admin import PremiumListMixin
from apps.pricing.infrastructure import repricing as rp
from apps.pricing.infrastructure.models import RepricingModel

TZ = ZoneInfo("Asia/Tashkent")
STATUS_STYLE = {"draft": ("#64748b", "fa-pen"), "scheduled": ("#7c3aed", "fa-clock"), "applied": ("#16a34a", "fa-circle-check"), "cancelled": ("#94a3b8", "fa-ban")}


def money(v) -> str:
    if v is None:
        return "—"
    return f"{Decimal(v):,.0f}".replace(",", " ")


def _dec(raw) -> Decimal | None:
    raw = (raw or "").replace(" ", "").replace(",", ".").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _locale() -> str:
    lang = (get_language() or "uz")[:2]
    return lang if lang in ("uz", "ru", "en") else "uz"


@admin.register(RepricingModel)
class RepricingAdmin(PremiumListMixin, admin.ModelAdmin):
    list_display = ("number", "title", "status", "created_at", "lines_count")
    search_fields = ("number", "title", "note")
    list_filter = ("status",)
    ordering = ("-created_at",)
    actions = None
    nz_icon, nz_tone, nz_title = "fa-tags", "#ea580c", "Narxlarni qayta baholash"
    nz_subtitle = "Ko'p mahsulot narxini bir martada o'zgartirish: brend, kategoriya yoki ro'yxat bo'yicha tanlang, qoidani bering, ko'rib chiqing va qo'llang — hozir yoki belgilangan vaqtda."
    nz_columns = (("Hujjat", ""), ("Holat", ""), ("Qoida", ""), ("Kim / qachon", ""), ("Mahsulotlar", "r"))
    nz_grid = "minmax(260px,2.2fr) 150px minmax(200px,1.6fr) minmax(170px,1.2fr) 110px"
    nz_search = "Raqam yoki nom…"
    nz_empty = ("Hali hujjat yo'q", "«Yangi qayta baholash» bilan birinchi ommaviy narx o'zgarishini yarating.")
    nz_css = ("admin/css/nutrizone-repricing.css",)

    def has_change_permission(self, request, obj=None):
        return False if obj is not None else super().has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("pricing.view_repricingmodel")

    def has_delete_permission(self, request, obj=None):
        return False

    def nz_tabs(self, request):
        counts = dict(RepricingModel.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values()))] + [(k, str(label), counts.get(k, 0)) for k, label in RepricingModel.STATUS_CHOICES],
                           {k: v[0] for k, v in STATUS_STYLE.items()})

    def nz_hero_actions(self, request):
        out = [{"label": "Narxlar ro'yxati", "url": reverse("admin:nz_price_list"), "icon": "fa-list"}]
        if self.has_add_permission(request):
            out.append({"label": "Yangi qayta baholash", "url": reverse("admin:pricing_repricingmodel_add"), "icon": "fa-plus", "primary": True})
        return out

    def nz_stats(self, request):
        month0 = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        agg = RepricingModel.objects.aggregate(month=Count("id", filter=Q(status="applied", applied_at__gte=month0)), sched=Count("id", filter=Q(status="scheduled")),
                                               draft=Count("id", filter=Q(status="draft")))
        return [ui.stat_card("Bu oy qo'llangan", agg["month"], "#16a34a", "fa-circle-check"), ui.stat_card("Rejalashtirilgan", agg["sched"], "#7c3aed", "fa-clock"),
                ui.stat_card("Qoralamalar", agg["draft"], "#64748b", "fa-pen")]

    def nz_href(self, obj):
        return reverse("admin:nz_repricing_doc", args=[obj.pk])

    def nz_row(self, d):
        color, icon = STATUS_STYLE.get(d.status, ("#64748b", "fa-circle"))
        title = format_html("<b>{}</b><br><small>{}</small>", d.title, d.number)
        state = ui.chip(d.get_status_display(), color, icon)
        if d.status == "scheduled" and d.scheduled_for:
            state = format_html("{}<br><small>{}</small>", state, timezone.localtime(d.scheduled_for, TZ).strftime("%d.%m.%Y %H:%M"))
        return [title, state, _rule_text(d.rule), format_html("{}<br><small>{}</small>", d.applied_by or d.created_by or "—", ui.local(d.applied_at or d.created_at)),
                format_html("<b>{}</b>", d.lines_count)]

    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("<uuid:pk>/doc/", v(self.doc_view), name="nz_repricing_doc"),
            path("<uuid:pk>/act/", v(self.act_view), name="nz_repricing_act"),
            path("<uuid:pk>/export.xlsx", v(self.export_view), name="nz_repricing_export"),
        ] + super().get_urls()

    # ------------------------------------------------------------ builder

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_add_permission(request):
            raise PermissionDenied
        g = request.POST if request.method == "POST" else request.GET
        f = rp.Filters.from_query(g)
        mode = g.get("mode") if g.get("mode") in rp.MODES else "percent"
        value = _dec(g.get("value"))
        rounding = g.get("rounding") if g.get("rounding") in rp.ROUNDINGS else "1000"
        compare = g.get("compare") if g.get("compare") in rp.COMPARE else "keep"
        rows = [] if f.empty else rp.compute(rp.candidates(f, _locale()), mode, value, rounding, compare)

        if request.method == "POST" and g.get("save"):
            lines = []
            for r in rows:
                vid = str(r["variant_id"])
                if not g.get(f"on_{vid}"):
                    continue
                new = _dec(g.get(f"new_{vid}")) if g.get(f"new_{vid}") not in (None, "") else r["new_price"]
                lines.append({"variant_id": r["variant_id"], "old_price": r["price"], "new_price": new, "old_compare": r["compare_at"],
                              "new_compare": r["new_compare"], "cost": r["cost"]})
            when = None
            if g.get("when") == "later":
                try:
                    when = datetime.fromisoformat(g.get("scheduled_for") or "").replace(tzinfo=TZ)
                except ValueError:
                    when = None
                if when is None or when <= timezone.now():
                    messages.error(request, "Kuchga kirish vaqti kelajakda bo'lishi kerak.")
                    return self._builder(request, f, mode, value, rounding, compare, rows)
            actor = request.user.get_full_name() or request.user.get_username()
            rule = {"mode": mode, "value": str(value) if value is not None else "", "rounding": rounding, "compare": compare, "filters": f.as_dict()}
            try:
                doc = rp.create(lines, g.get("title") or "", rule, actor, note=g.get("note") or "", scheduled_for=when)
                if g.get("when") == "now":
                    if not request.user.has_perm("pricing.apply_repricing"):
                        messages.warning(request, f"{doc.number} qoralama sifatida saqlandi — qo'llash uchun ruxsat kerak.")
                    else:
                        res = rp.apply(doc, actor)
                        messages.success(request, f"{doc.number}: {res['ok']} ta narx yangilandi." + (f" {res['failed']} ta xato." if res["failed"] else ""))
                elif when:
                    messages.success(request, f"{doc.number} {timezone.localtime(when, TZ):%d.%m.%Y %H:%M} da kuchga kiradi.")
                else:
                    messages.success(request, f"{doc.number} qoralama sifatida saqlandi.")
            except rp.RepricingError as exc:
                messages.error(request, str(exc))
                return self._builder(request, f, mode, value, rounding, compare, rows)
            return HttpResponseRedirect(reverse("admin:nz_repricing_doc", args=[doc.pk]))
        return self._builder(request, f, mode, value, rounding, compare, rows)

    def _builder(self, request, f, mode, value, rounding, compare, rows):
        from apps.products.infrastructure.models import Brand, Category

        brands = sorted(((str(b.pk), str(b)) for b in Brand.objects.filter(deleted_at__isnull=True).prefetch_related("translations")), key=lambda x: x[1].lower())
        cats = list(Category.objects.filter(deleted_at__isnull=True).prefetch_related("translations").order_by("sort_order"))
        by_parent: dict = {}
        for c in cats:
            by_parent.setdefault(c.parent_id, []).append(c)
        tree = []

        def walk(parent, depth):
            for c in by_parent.get(parent, []):
                tree.append((str(c.pk), "— " * depth + str(c)))
                walk(c.pk, depth + 1)

        walk(None, 0)
        changing = [r for r in rows if r["new_price"] is not None and not r["skip"] and r["new_price"] != r["price"]]
        for r in rows:
            r["price_fmt"], r["new_fmt"], r["cost_fmt"] = money(r["price"]), (money(r["new_price"]) if r["new_price"] is not None else ""), money(r["cost"])
            r["compare_fmt"], r["new_compare_fmt"] = money(r["compare_at"]), money(r["new_compare"])
        context = {
            **self.admin_site.each_context(request), "title": "Yangi qayta baholash", "opts": self.model._meta, "f": f, "mode": mode, "value": "" if value is None else f"{value.normalize():f}",
            "rounding": rounding, "compare": compare, "rows": rows, "modes": rp.MODES, "roundings": rp.ROUNDINGS, "compares": rp.COMPARE,
            "brands": brands, "cats": tree, "changing": len(changing), "below_cost": sum(1 for r in rows if "below_cost" in r["warn"]),
            "skipped": sum(1 for r in rows if r["skip"]), "limit_hit": len(rows) >= rp.MAX_LINES, "max_lines": rp.MAX_LINES,
            "can_apply": request.user.has_perm("pricing.apply_repricing"), "now_local": timezone.localtime(timezone.now(), TZ).strftime("%Y-%m-%dT%H:%M"),
            "title_default": (request.POST.get("title") if request.method == "POST" else "") or "",
        }
        return TemplateResponse(request, "admin/pricing/repricing_builder.html", context)

    # ------------------------------------------------------------ document

    def doc_view(self, request, pk):
        if not self.has_view_permission(request):
            raise PermissionDenied
        doc = get_object_or_404(RepricingModel, pk=pk)
        lines = rp.lines_view(doc, _locale())
        ups = [r for r in lines if r["delta"] is not None and r["delta"] > 0]
        downs = [r for r in lines if r["delta"] is not None and r["delta"] < 0]
        deltas = [r["delta"] for r in lines if r["delta"] is not None]
        context = {
            **self.admin_site.each_context(request), "title": f"{doc.number} · {doc.title}", "opts": self.model._meta, "doc": doc, "lines": lines,
            "rule_text": _rule_text(doc.rule), "style": STATUS_STYLE.get(doc.status), "ups": len(ups), "downs": len(downs),
            "avg": round(sum(deltas) / len(deltas), 1) if deltas else None, "below_cost": sum(1 for r in lines if r["below_cost"]),
            "errors": sum(1 for r in lines if r["l"].error), "can_apply": request.user.has_perm("pricing.apply_repricing"),
            "reverted": doc.reverted_by.filter(status="applied").first(), "money": money,
        }
        for r in lines:
            l = r["l"]
            r["old_fmt"], r["new_fmt"], r["cost_fmt"] = money(l.old_price), money(l.new_price), money(l.cost)
            r["oc_fmt"], r["nc_fmt"] = money(l.old_compare_at), money(l.new_compare_at)
        return TemplateResponse(request, "admin/pricing/repricing_doc.html", context)

    def act_view(self, request, pk):
        doc = get_object_or_404(RepricingModel, pk=pk)
        back = reverse("admin:nz_repricing_doc", args=[doc.pk])
        if request.method != "POST":
            return HttpResponseRedirect(back)
        if not request.user.has_perm("pricing.apply_repricing"):
            raise PermissionDenied
        actor = request.user.get_full_name() or request.user.get_username()
        action = request.POST.get("action")
        try:
            if action == "apply":
                res = rp.apply(doc, actor)
                messages.success(request, f"{res['ok']} ta narx yangilandi." + (f" {res['failed']} ta xato." if res["failed"] else ""))
            elif action == "cancel":
                rp.cancel(doc)
                messages.success(request, "Hujjat bekor qilindi.")
            elif action == "revert":
                back_doc = rp.revert(doc, actor)
                messages.success(request, f"Narxlar oldingi holatiga qaytarildi ({back_doc.number}).")
                return HttpResponseRedirect(reverse("admin:nz_repricing_doc", args=[back_doc.pk]))
        except rp.RepricingError as exc:
            messages.error(request, str(exc))
        return HttpResponseRedirect(back)

    def export_view(self, request, pk):
        from apps.platform.infrastructure.excel_export import Col, response, workbook

        if not self.has_view_permission(request):
            raise PermissionDenied
        doc = get_object_or_404(RepricingModel, pk=pk)
        rows = [type("R", (), {"name": r["name"], "size": r["size"], "sku": r["sku"], "old": r["l"].old_price, "new": r["l"].new_price, "delta": r["delta"],
                               "cost": r["l"].cost, "compare": r["l"].new_compare_at, "applied": "Ha" if r["l"].applied else ""}) for r in rp.lines_view(doc, _locale())]
        cols = [Col("Mahsulot", "name", 40), Col("Variant", "size", 22), Col("SKU", "sku", 16), Col("Eski narx", "old", 14, money=True), Col("Yangi narx", "new", 14, money=True),
                Col("O'zgarish, %", "delta", 12), Col("Tannarx", "cost", 14, money=True), Col("Eski narx (chizilgan)", "compare", 16, money=True), Col("Qo'llangan", "applied", 10)]
        return response(workbook(doc.number, cols, rows, doc.title), f"qayta-baholash-{doc.number}")


def _rule_text(rule: dict) -> str:
    mode, value = rule.get("mode"), rule.get("value") or ""
    if mode == "revert":
        return f"Qaytarish ({rule.get('of', '')})"
    try:
        v = Decimal(value) if value else None
    except InvalidOperation:
        v = None
    if mode == "percent" and v is not None:
        text = f"{'+' if v > 0 else ''}{v.normalize():f}%"
    elif mode == "amount" and v is not None:
        text = f"{'+' if v > 0 else '−' if v < 0 else ''}{money(abs(v))} so'm"
    elif mode == "markup" and v is not None:
        text = f"Tannarx + {v.normalize():f}%"
    elif mode == "fixed" and v is not None:
        text = f"= {money(v)} so'm"
    else:
        text = "Qo'lda"
    rnd = rule.get("rounding")
    if rnd and rnd != "none":
        text += f" · {rp.ROUNDINGS.get(rnd, '')}"
    return text
