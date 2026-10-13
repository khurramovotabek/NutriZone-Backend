"""
Dashboard → Narxlash → Kuponlar: discount codes with their rules, usage and results.

Pages (templates/admin/pricing/): the list (status tabs, KPIs, usage bars), the coupon card (rules, orders that
used it with revenue and discount given, customers, activate / pause / revoke) and a premium create / edit form
(code generator, live preview). Business rules: coupon_rules.py. Orders carry the coupon id (OrderModel.coupon_ids),
which is what the results count -- uses recorded before redemptions were tracked are included.
"""
from __future__ import annotations

import secrets
import string
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _

from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.pricing.infrastructure import coupon_rules
from apps.pricing.infrastructure import models as orm

STATUS_STYLE = {
    "draft": (_("Draft"), "#64748b", "fa-pen-ruler"), "active": (_("Active"), "#10b981", "fa-circle-check"),
    "exhausted": (_("Limit reached"), "#f59e0b", "fa-battery-empty"), "expired": (_("Expired"), "#e11d48", "fa-calendar-xmark"),
    "revoked": (_("Revoked"), "#94a3b8", "fa-ban"),
}
STACKING = (("exclusive", _("Can't be combined")), ("stackable", _("Adds up with other coupons")), ("best_of", _("Only the biggest discount applies")))
CODE_ALPHABET = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"


def _money(v) -> str:
    return f"{int(round(v or 0)):,}".replace(",", " ")


def generate_code(prefix: str = "NZ", length: int = 6) -> str:
    manager = getattr(orm.CouponModel, "all_objects", orm.CouponModel.objects)
    while True:
        code = f"{prefix}{''.join(secrets.choice(CODE_ALPHABET) for _ in range(length))}"
        if not manager.filter(code=code).exists():
            return code


def discount_label(c) -> str:
    if c.discount_value_type == "percentage" and c.discount_percentage is not None:
        return f"−{c.discount_percentage.normalize():f}%"
    if c.discount_fixed_amount is not None:
        return f"−{_money(c.discount_fixed_amount)} {_t("so'm")}"
    return "—"


def effective_status(c, now=None) -> str:
    """What the coupon really is right now (an active code past its end date is expired)."""
    now = now or timezone.now()
    if c.status == "active" and c.validity_ends_at and c.validity_ends_at < now:
        return "expired"
    if c.status == "active" and c.max_redemptions is not None and getattr(c, "_uses", 0) >= c.max_redemptions:
        return "exhausted"
    return c.status


def order_stats(coupons) -> dict:
    """coupon id -> {"orders", "customers", "revenue", "discount", "last"} from the orders that carried the coupon."""
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

    by_id = {str(c.id): c for c in coupons}
    if not by_id:
        return {}
    q = Q()
    for cid in by_id:
        q |= Q(coupon_ids__contains=[cid])
    orders = list(OrderModel.objects.filter(q).exclude(status__in=["cancelled", "draft"]).values("id", "order_number", "customer_id", "coupon_ids", "created_at", "status"))
    lines: dict = {}
    for ln in OrderLineItemModel.objects.filter(order_id__in=[o["id"] for o in orders]).exclude(status="cancelled").values("order_id", "unit_price_amount", "quantity", "discount_amount"):
        g = lines.setdefault(ln["order_id"], {"gross": Decimal(0), "discount": Decimal(0)})
        g["gross"] += ln["unit_price_amount"] * ln["quantity"]
        g["discount"] += ln["discount_amount"]
    out: dict = {}
    for o in orders:
        totals = lines.get(o["id"], {"gross": Decimal(0), "discount": Decimal(0)})
        for cid in o["coupon_ids"] or []:
            c = by_id.get(str(cid))
            if c is None:
                continue
            s = out.setdefault(c.id, {"orders": 0, "customers": set(), "revenue": Decimal(0), "discount": Decimal(0), "last": None, "list": []})
            s["orders"] += 1
            if o["customer_id"]:
                s["customers"].add(o["customer_id"])
            disc = min(coupon_rules.discount_amount(c, totals["gross"]), totals["discount"]) if totals["discount"] else Decimal(0)
            s["revenue"] += totals["gross"] - totals["discount"]
            s["discount"] += disc
            s["last"] = max(s["last"], o["created_at"]) if s["last"] else o["created_at"]
            s["list"].append({**o, "gross": totals["gross"], "paid": totals["gross"] - totals["discount"], "coupon_discount": disc})
    return out


class CouponForm(forms.ModelForm):
    """The premium coupon editor: one validated form for every rule."""

    KIND = (("percentage", _("Percent off")), ("fixed_amount", _("Amount off (so'm)")))
    discount_kind = forms.ChoiceField(choices=KIND, widget=forms.RadioSelect, initial="percentage")
    value = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2, label=_("Discount"))
    starts = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), label=_("Starts"))
    ends = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), label=_("Ends"))
    activate = forms.BooleanField(required=False, initial=True, label=_("Active right away"))

    class Meta:
        model = orm.CouponModel
        fields = ("code", "title", "min_order_amount", "max_redemptions", "max_per_customer", "stacking_mode")

    def __init__(self, *args, used: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.used = used
        c = self.instance
        if c is not None and not c._state.adding:  # a new CouponModel already has a UUID pk, so pk can't tell new from existing
            self.fields["discount_kind"].initial = c.discount_value_type
            self.fields["value"].initial = c.discount_percentage if c.discount_value_type == "percentage" else c.discount_fixed_amount
            self.fields["starts"].initial = timezone.localtime(c.validity_starts_at) if c.validity_starts_at else None
            self.fields["ends"].initial = timezone.localtime(c.validity_ends_at) if c.validity_ends_at else None
            self.fields["activate"].initial = c.status == "active"
            if used:
                self.fields["code"].disabled = True  # customers already typed it: renaming would break their links / posts
        else:
            self.fields["max_per_customer"].initial = 1
        self.fields["code"].help_text = _("Latin letters and digits, 3–24 characters. Customers type it at checkout.")
        self.fields["stacking_mode"].label = _("With other coupons")
        self.fields["stacking_mode"].choices = STACKING

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper().replace(" ", "")
        if not code or len(code) < 3 or len(code) > 24 or not code.isalnum() or not code.isascii():
            raise forms.ValidationError(_("Use 3–24 Latin letters and digits, without spaces."))
        clash = orm.CouponModel.objects.filter(code=code).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("This code is already taken."))
        return code

    def clean(self):
        d = super().clean()
        kind, value = d.get("discount_kind"), d.get("value")
        if kind == "percentage" and value is not None and value > 100:
            self.add_error("value", _("A percent can't be more than 100."))
        starts, ends = d.get("starts"), d.get("ends")
        if starts and ends and ends <= starts:
            self.add_error("ends", _("The end must be after the start."))
        if d.get("max_redemptions") is not None and d["max_redemptions"] < self.used:
            self.add_error("max_redemptions", _("It has already been used %s times.") % self.used)
        if d.get("min_order_amount") is not None and kind == "fixed_amount" and value and d["min_order_amount"] < value:
            self.add_error("min_order_amount", _("The minimum order should be at least the discount amount."))
        return d

    def save(self, commit=True):
        c = super().save(commit=False)
        d = self.cleaned_data
        c.coupon_type = c.coupon_type or "coupon"
        c.discount_value_type = d["discount_kind"]
        c.discount_percentage = d["value"] if d["discount_kind"] == "percentage" else None
        c.discount_fixed_amount = d["value"] if d["discount_kind"] == "fixed_amount" else None
        c.currency = "UZS"
        # the pricing engine reads an end date only together with a start date
        c.validity_starts_at = d.get("starts") or (timezone.now() if d.get("ends") else None)
        c.validity_ends_at = d.get("ends")
        if c.status in ("draft", "active", "", None) or not c.pk:
            c.status = "active" if d.get("activate") else "draft"
        if commit:
            c.save()
        return c


def state_q(state: str, now=None) -> Q:
    """The real state as a query (an "active" coupon past its end date is expired)."""
    now = now or timezone.now()
    past = Q(validity_ends_at__lt=now)
    return {
        "active": Q(status="active") & ~past, "expired": Q(status="expired") | (Q(status="active") & past),
        "exhausted": Q(status="exhausted"), "draft": Q(status="draft"), "revoked": Q(status="revoked"),
    }.get(state, Q())


class StateFilter(admin.SimpleListFilter):
    title = _("State")
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [(k, v[0]) for k, v in STATUS_STYLE.items()]

    def queryset(self, request, queryset):
        return queryset.filter(state_q(self.value())) if self.value() else queryset


@admin.register(orm.CouponModel)
class CouponAdmin(ExcelExportMixin, admin.ModelAdmin):
    excel_title = "Kuponlar"
    excel_columns = [
        Col("Kod", "code", 16), Col("Nomi", "title", 26), Col("Turi", "coupon_type", 12), Col("Holat", "status", 11),
        Col("Chegirma", lambda c: f"{c.discount_percentage.normalize():f}%" if c.discount_value_type == "percentage" and c.discount_percentage is not None
            else (c.discount_fixed_amount or ""), 13),
        Col("Min. buyurtma", "min_order_amount", 14, money=True), Col("Boshlanadi", "validity_starts_at", 17), Col("Tugaydi", "validity_ends_at", 17),
        Col("Limit", "max_redemptions", 9), Col("Ishlatilgan", lambda c: getattr(c, "_uses", 0), 11, number=True),
        Col("Buyurtmalar", lambda c: c.x.get("orders", 0), 11, number=True), Col("Mijozlar", lambda c: len(c.x.get("customers", ())), 10, number=True),
        Col("Tushum (so'm)", lambda c: c.x.get("revenue", 0), 15, money=True), Col("Berilgan chegirma", lambda c: c.x.get("discount", 0), 15, money=True),
    ]

    def excel_prepare(self, objs):
        stats = order_stats(objs)
        for c in objs:
            c.x = stats.get(c.id, {})

    list_display = ("code", "status")
    list_filter = (StateFilter, "status", "coupon_type")
    search_fields = ("code", "title")
    list_per_page = 25
    ordering = ("-created_at",)
    change_list_template = "admin/pricing/coupons.html"
    actions = ["revoke_selected"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_uses=Count("redemptions"))

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        rows = list(cl.result_list)
        stats = order_stats(rows)
        now = timezone.now()
        for c in rows:
            s = stats.get(c.id, {})
            uses = max(c._uses, s.get("orders", 0))
            status = effective_status(c, now)
            label, color, icon = STATUS_STYLE.get(status, (status, "#64748b", "fa-circle"))
            days_left = (c.validity_ends_at - now).days if c.validity_ends_at and c.validity_ends_at > now else None
            c.nz = {
                "discount": discount_label(c), "uses": uses, "limit": c.max_redemptions, "pct": min(100, round(uses * 100 / c.max_redemptions)) if c.max_redemptions else None,
                "label": label, "color": color, "icon": icon, "status": status, "revenue": _money(s.get("revenue")) if s.get("revenue") else "",
                "customers": len(s.get("customers", ())), "ends": timezone.localtime(c.validity_ends_at).strftime("%d.%m.%Y") if c.validity_ends_at else "",
                "days_left": days_left, "soon": days_left is not None and days_left <= 7,
            }
        return cl

    def changelist_view(self, request, extra_context=None):
        coupons = list(orm.CouponModel.objects.annotate(_uses=Count("redemptions")))
        stats = order_stats(coupons)
        now = timezone.now()
        month = now - timedelta(days=30)
        live = [c for c in coupons if effective_status(c, now) == "active"]
        month_orders = sum(1 for s in stats.values() for o in s["list"] if o["created_at"] >= month)
        current = request.GET.get("state", "")
        counts: dict = {}
        for c in coupons:
            st = effective_status(c, now)
            counts[st] = counts.get(st, 0) + 1
        tabs = [("", _t("All"), "#64748b", "fa-layer-group", len(coupons))] + [(k, str(v[0]), v[1], v[2], counts.get(k, 0)) for k, v in STATUS_STYLE.items()]
        extra = {
            "title": _t("Kuponlar"), "tabs": tabs, "current": current, "q": request.GET.get("q", ""),
            "kpi": {
                "active": len(live), "expiring": sum(1 for c in live if c.validity_ends_at and c.validity_ends_at < now + timedelta(days=7)),
                "orders": sum(s["orders"] for s in stats.values()), "month_orders": month_orders,
                "revenue": _money(sum((s["revenue"] for s in stats.values()), Decimal(0))), "discount": _money(sum((s["discount"] for s in stats.values()), Decimal(0))),
                "customers": len(set().union(*[s["customers"] for s in stats.values()])) if stats else 0,
            },
            "can_add": request.user.has_perm("pricing.add_couponmodel"),
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    # ------------------------------------------------------------------ card, form, lifecycle
    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("<uuid:pk>/edit/", v(self.edit_view), name="pricing_couponmodel_edit"),
            path("<uuid:pk>/status/", v(self.status_view), name="pricing_couponmodel_status"),
            path("generate-code/", v(self.code_view), name="pricing_couponmodel_code"),
            *super().get_urls(),
        ]

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_add_permission(request):
            raise PermissionDenied
        return self._form(request, None)

    def edit_view(self, request, pk):
        if not self.has_change_permission(request):
            raise PermissionDenied
        return self._form(request, get_object_or_404(orm.CouponModel, pk=pk))

    def _form(self, request, coupon):
        used = coupon.redemptions.count() + (order_stats([coupon]).get(coupon.id, {}).get("orders", 0) if coupon else 0) if coupon else 0
        initial = {} if coupon else {"code": generate_code()}
        form = CouponForm(request.POST or None, instance=coupon, initial=initial, used=used)
        if request.method == "POST" and form.is_valid():
            c = form.save()
            messages.success(request, _t("Coupon %s saved.") % c.code)
            return HttpResponseRedirect(reverse("admin:pricing_couponmodel_change", args=[c.pk]))
        return render(request, "admin/pricing/coupon_form.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": _t("Edit coupon") if coupon else _t("New coupon"),
            "form": form, "coupon": coupon, "used": used, "code_url": reverse("admin:pricing_couponmodel_code"),
        })

    def code_view(self, request):
        from django.http import JsonResponse

        prefix = "".join(ch for ch in (request.GET.get("prefix") or "NZ").upper() if ch.isalnum() and ch.isascii())[:10] or "NZ"
        return JsonResponse({"ok": True, "code": generate_code(prefix)})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        c = get_object_or_404(orm.CouponModel.objects.annotate(_uses=Count("redemptions")), pk=object_id)
        s = order_stats([c]).get(c.id, {"orders": 0, "customers": set(), "revenue": Decimal(0), "discount": Decimal(0), "list": [], "last": None})
        from apps.identity.infrastructure.models import User

        users = {u.id: u for u in User.objects.filter(id__in={o["customer_id"] for o in s["list"] if o["customer_id"]}).only("id", "full_name", "phone_number")}
        status = effective_status(c)
        label, color, icon = STATUS_STYLE.get(status, (status, "#64748b", "fa-circle"))
        uses = max(c._uses, s["orders"])
        rules = []
        if c.min_order_amount:
            rules.append((_t("Minimum order"), f"{_money(c.min_order_amount)} {_t("so'm")}"))
        rules.append((_t("Total uses"), f"{uses} / {c.max_redemptions}" if c.max_redemptions else f"{uses} / ∞"))
        rules.append((_t("Uses per customer"), str(c.max_per_customer) if c.max_per_customer else "∞"))
        rules.append((_t("Valid"), (timezone.localtime(c.validity_starts_at).strftime("%d.%m.%Y %H:%M") if c.validity_starts_at else _t("from now")) + " → " +
                      (timezone.localtime(c.validity_ends_at).strftime("%d.%m.%Y %H:%M") if c.validity_ends_at else _t("no end date"))))
        rules.append((_t("With other coupons"), str(dict(STACKING).get(c.stacking_mode, c.stacking_mode))))
        orders = [{**o, "user": users.get(o["customer_id"]), "paid": _money(o["paid"]), "disc": _money(o["coupon_discount"]),
                   "when": timezone.localtime(o["created_at"]).strftime("%d.%m.%Y %H:%M")} for o in sorted(s["list"], key=lambda o: o["created_at"], reverse=True)]
        problem = coupon_rules.problem(c)
        return render(request, "admin/pricing/coupon_detail.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": c.code, "c": c, "label": label, "color": color, "icon": icon,
            "discount": discount_label(c), "uses": uses, "pct": min(100, round(uses * 100 / c.max_redemptions)) if c.max_redemptions else None, "rules": rules,
            "orders": orders, "revenue": _money(s["revenue"]), "given": _money(s["discount"]), "customers": len(s["customers"]),
            "avg": _money(s["revenue"] / s["orders"]) if s["orders"] else "0", "problem": problem[1] if problem and c.status == "active" else "",
            "can_change": request.user.has_perm("pricing.change_couponmodel"), "status": c.status,
        })

    def status_view(self, request, pk):
        """activate / pause (back to draft) / revoke."""
        if request.method != "POST" or not request.user.has_perm("pricing.change_couponmodel"):
            raise PermissionDenied
        c = get_object_or_404(orm.CouponModel, pk=pk)
        to = request.POST.get("to")
        if to == "revoke":
            self.revoke_selected(request, orm.CouponModel.objects.filter(pk=c.pk))
            messages.success(request, _t("Coupon revoked -- customers can no longer use it."))
        elif to in ("active", "draft") and c.status in ("active", "draft", "exhausted", "expired"):
            if to == "active" and c.validity_ends_at and c.validity_ends_at < timezone.now():
                messages.error(request, _t("The end date has passed -- edit the dates first."))
            elif to == "active" and c.max_redemptions is not None and c.redemptions.count() >= c.max_redemptions:
                messages.error(request, _t("The use limit is reached -- raise the limit first."))
            else:
                orm.CouponModel.objects.filter(pk=c.pk).update(status=to, updated_at=timezone.now())
                messages.success(request, _t("Coupon activated.") if to == "active" else _t("Coupon paused."))
        return HttpResponseRedirect(reverse("admin:pricing_couponmodel_change", args=[c.pk]))

    @admin.action(description=_("Revoke selected coupons"))
    def revoke_selected(self, request, queryset):
        from apps.pricing.application.services.coupons_bundles_snapshots import RevokeCoupon
        from apps.pricing.infrastructure.admin import _admin_ctx
        from apps.pricing.infrastructure.repositories import DjangoCouponRepository

        service = RevokeCoupon(DjangoCouponRepository(), _admin_ctx(request))
        for item in queryset:
            try:
                service.execute(item.id)
            except Exception as exc:  # noqa: BLE001
                self.message_user(request, f"Could not revoke coupon '{item.code}': {exc}", level="error")
