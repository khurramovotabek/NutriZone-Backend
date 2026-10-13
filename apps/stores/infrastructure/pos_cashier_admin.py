"""
Dashboard → POS → Kassalar va kassirlar: every kassa (each branch + the online kassa) on one page.

Per kassa: its PIN (set / change -- one shared PIN per kassa, see pos_cashiers.py), the shift that is open right now,
today's takings, and its cashiers -- customer accounts linked to the kassa, with their sales today / 30 days and last
activity. A superadmin adds a cashier by searching the customer base (name or phone) and removes one with a click.
The online kassa is run by Dashboard staff, so it only has a PIN.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _

from apps.stores.infrastructure import payroll, pos_cashiers
from apps.stores.infrastructure.models import CashierPayout, CashSession, Store, StoreCashier
from common.exceptions import DomainException


def _fmt(v) -> str:
    return f"{int(v or 0):,}".replace(",", " ")


TZ = ZoneInfo("Asia/Tashkent")  # kassas work on Tashkent wall-clock time (the server runs in UTC)


def _when(dt) -> str:
    return dt.astimezone(TZ).strftime("%d.%m.%Y %H:%M") if dt else ""


def _opened_by(ses) -> str:
    """Who opened the shift: stored name, else the "Dashboard: <staff>" note of older shifts, else the account."""
    if ses.opened_by_name:
        return ses.opened_by_name
    if ses.opening_note.startswith("Dashboard:"):
        return ses.opening_note.split(":", 1)[1].strip()
    return (ses.opened_by.full_name if ses.opened_by_id and ses.opened_by else "") or "—"


@admin.register(StoreCashier)
class StoreCashierAdmin(admin.ModelAdmin):
    change_list_template = "admin/pos/cashiers.html"
    list_display = ("user", "store", "is_active", "last_seen_at")

    def has_add_permission(self, request):
        return False  # cashiers are linked from the kassa cards (user search), never through a raw form

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or super().has_change_permission(request, obj)

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path("pin/<uuid:store_id>/", wrap(self.pin_view), name="stores_storecashier_pin"),
            path("link/", wrap(self.link_view), name="stores_storecashier_link"),
            path("unlink/<uuid:link_id>/", wrap(self.unlink_view), name="stores_storecashier_unlink"),
            path("users/", wrap(self.users_view), name="stores_storecashier_users"),
            path("payroll/", wrap(self.payroll_view), name="stores_storecashier_payroll"),
            path("payroll/excel/", wrap(self.payroll_excel), name="stores_storecashier_payroll_excel"),
            path("payroll/terms/<uuid:link_id>/", wrap(self.terms_view), name="stores_storecashier_terms"),
            path("payroll/pay/<uuid:link_id>/", wrap(self.pay_view), name="stores_storecashier_pay"),
            path("payroll/undo/<uuid:payout_id>/", wrap(self.undo_view), name="stores_storecashier_undo"),
        ] + super().get_urls()

    def _guard(self, request):
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied

    # ------------------------------------------------------------ actions

    def pin_view(self, request, store_id):
        self._guard(request)
        store = get_object_or_404(Store, id=store_id)
        pin, again = request.POST.get("pin", ""), request.POST.get("pin_again", "")
        base = reverse("admin:stores_storecashier_changelist")
        try:
            if pin != again:
                code = "PIN_MISMATCH"
            else:
                pos_cashiers.set_pin(store, pin)
                messages.success(request, f"{pos_cashiers.kassa_name(store)}: kassa PIN kodi o'rnatildi. Uni faqat shu kassa kassirlariga ayting.")
                return redirect(f"{base}?pin_ok={store.id}#k-{store.id}")
        except DomainException as exc:
            code = getattr(exc, "code", "") if getattr(exc, "code", "") in pos_cashiers.PIN_ERRORS else "PIN_FORMAT"
        # the error must be seen where the owner is looking: the dialog reopens on that kassa with the reason
        messages.error(request, f"{pos_cashiers.kassa_name(store)}: {pos_cashiers.PIN_ERRORS[code]}")
        return redirect(f"{base}?pin_error={code}&pin_kassa={store.id}#k-{store.id}")

    def link_view(self, request):
        self._guard(request)
        from apps.identity.infrastructure.models import User

        store = get_object_or_404(Store, id=request.POST.get("store"))
        user = get_object_or_404(User.objects.exclude(status="blocked"), id=request.POST.get("user"), is_deleted=False)
        try:
            moved_from = StoreCashier.objects.filter(user=user, is_active=True).exclude(store=store).select_related("store").first()
            pos_cashiers.link(store, user, added_by=request.user.get_full_name() or request.user.get_username())
            name = user.full_name or user.phone_number
            if moved_from:
                messages.success(request, _t("%(name)s moved from %(old)s to %(kassa)s.") % {"name": name, "old": moved_from.store.name, "kassa": store.name})
            else:
                messages.success(request, _t("%(name)s is now a cashier at %(kassa)s -- they were notified.") % {"name": name, "kassa": store.name})
        except DomainException as exc:
            messages.error(request, _t(str(exc)))
        return redirect(f"{reverse('admin:stores_storecashier_changelist')}#k-{store.id}")

    def unlink_view(self, request, link_id):
        self._guard(request)
        link = get_object_or_404(StoreCashier.objects.select_related("store", "user"), id=link_id)
        store_id = link.store_id
        link.delete()
        messages.success(request, _t("%(name)s is no longer a cashier at %(kassa)s.") % {"name": link.user.full_name or link.user.phone_number, "kassa": link.store.name})
        return redirect(f"{reverse('admin:stores_storecashier_changelist')}#k-{store_id}")

    def users_view(self, request):
        """Customer search for the "add cashier" dialog: name or phone, with where the person already works."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        from apps.identity.infrastructure.models import User

        q = (request.GET.get("q") or "").strip()
        if len(q) < 2:
            return JsonResponse({"results": []})
        digits = "".join(ch for ch in q if ch.isdigit())
        cond = Q(full_name__icontains=q)
        if len(digits) >= 3:
            cond |= Q(phone_number__contains=digits)
        users = list(User.objects.filter(cond, is_deleted=False).exclude(status="blocked").order_by("full_name")[:12])
        links = {c.user_id: c.store.name for c in StoreCashier.objects.filter(user__in=users, is_active=True).select_related("store")}
        owners = {s.owner_id: s.name for s in Store.objects.filter(owner__in=users)}
        return JsonResponse({"results": [{
            "id": str(u.id), "name": u.full_name or "—", "phone": u.phone_number, "initials": pos_cashiers.initials(u.full_name or u.phone_number or ""),
            "color": pos_cashiers.color_for(u.id), "works_at": links.get(u.id), "owns": owners.get(u.id),
        } for u in users]})

    # ------------------------------------------------------------ payroll (oylik + KPI)

    def _back(self, request, month=None):
        m = month or request.POST.get("month") or request.GET.get("month") or ""
        return redirect(f"{reverse('admin:stores_storecashier_payroll')}?month={m}")

    def terms_view(self, request, link_id):
        self._guard(request)
        link = get_object_or_404(StoreCashier.objects.select_related("user"), id=link_id)
        try:
            payroll.set_terms(link, request.POST.get("base_salary", "0"), request.POST.get("kpi_percent", "0"))
            messages.success(request, _t("%(name)s: base %(base)s so'm + KPI %(pct)s%% of sales.") % {"name": link.user.full_name, "base": _fmt(link.base_salary), "pct": link.kpi_percent.normalize()})
        except DomainException as exc:
            messages.error(request, _t(str(exc)))
        return self._back(request)

    def pay_view(self, request, link_id):
        self._guard(request)
        link = get_object_or_404(StoreCashier.objects.select_related("user"), id=link_id)
        month = payroll.month_start(request.POST.get("month"))
        try:
            p = payroll.pay(link, month, request.POST.get("adjustment") or 0, request.POST.get("note", ""), paid_by=request.user.get_full_name() or request.user.get_username())
            messages.success(request, _t("%(name)s: %(total)s so'm paid for %(month)s -- they were notified.") % {"name": link.user.full_name, "total": _fmt(p.total), "month": f"{month:%m.%Y}"})
        except DomainException as exc:
            messages.error(request, _t(str(exc)))
        return self._back(request, f"{month:%Y-%m}")

    def undo_view(self, request, payout_id):
        self._guard(request)
        if not request.user.is_superuser:
            raise PermissionDenied
        p = get_object_or_404(CashierPayout.objects.select_related("user"), id=payout_id)
        month = p.month
        payroll.undo(p)
        messages.success(request, _t("The payment was cancelled -- the month is computed live again."))
        return self._back(request, f"{month:%Y-%m}")

    def payroll_excel(self, request):
        from django.http import HttpResponse

        if not self.has_view_permission(request):
            raise PermissionDenied
        report = payroll.month_report(payroll.month_start(request.GET.get("month")))
        resp = HttpResponse(payroll.excel(report), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="kassirlar-oyligi-{report["month"]:%Y-%m}.xlsx"'
        return resp

    def payroll_view(self, request):
        from django.template.response import TemplateResponse

        if not self.has_view_permission(request):
            raise PermissionDenied
        month = payroll.month_start(request.GET.get("month"))
        report = payroll.month_report(month)
        t = report["totals"]
        best = max(report["rows"], key=lambda r: r["revenue"], default=None)
        rows = [{
            "name": r["user"].full_name or r["user"].phone_number, "phone": r["user"].phone_number, "initials": pos_cashiers.initials(r["user"].full_name or ""),
            "color": pos_cashiers.color_for(r["user"].id), "store": r["store"].name, "store_color": r["store"].color or "#64748b",
            "sales": r["sales"], "revenue": _fmt(r["revenue"]), "percent": r["percent"].normalize(), "kpi": _fmt(r["kpi"]), "base": _fmt(r["base"]),
            "adjustment": r["adjustment"], "adjustment_s": _fmt(abs(r["adjustment"])), "note": r["note"], "total": _fmt(r["total"]),
            "share": int(r["revenue"] * 100 / (best["revenue"] or 1)) if best and best["revenue"] else 0,
            "link_id": str(r["link"].id) if r["link"] else None, "base_raw": int(r["link"].base_salary) if r["link"] else 0,
            "percent_raw": str(r["link"].kpi_percent.normalize()) if r["link"] else "0",
            "payout_id": str(r["payout"].id) if r["payout"] else None, "paid_at": _when(r["payout"].paid_at) if r["payout"] else "", "paid_by": r["payout"].paid_by if r["payout"] else "",
            "kpi_raw": int(r["kpi"]), "base_now": int(r["base"]),
        } for r in report["rows"]]
        months_uz = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]
        ctx = {
            **self.admin_site.each_context(request), "title": _t("Cashier payroll"), "opts": self.model._meta, "rows": rows,
            "month": month, "month_key": f"{month:%Y-%m}", "month_label": f"{months_uz[month.month]} {month.year}",
            "prev": f"{payroll.prev_month(month):%Y-%m}", "next": f"{payroll.next_month(month):%Y-%m}" if month < payroll.month_start() else None,
            "current": report["current"], "can_edit": self.has_change_permission(request), "is_super": request.user.is_superuser,
            "t": {"total": _fmt(t["total"]), "kpi": _fmt(t["kpi"]), "base": _fmt(t["base"]), "revenue": _fmt(t["revenue"]), "sales": t["sales"],
                  "paid": _fmt(t["paid"]), "unpaid": _fmt(t["unpaid"]), "paid_n": t["paid_n"], "n": len(rows),
                  "kpi_share": f"{int(t['kpi'] * 100 / t['total']) if t['total'] else 0}%", "fund_share": f"{round(t['total'] * 100 / t['revenue'], 1)}%" if t["revenue"] else ""},
        }
        return TemplateResponse(request, "admin/pos/payroll.html", ctx)

    # ------------------------------------------------------------ page

    def changelist_view(self, request, extra_context=None):
        from apps.pos.infrastructure import sales_reports as rep
        from apps.pos.infrastructure.models import SaleModel

        stores = list(Store.objects.filter(kind="store").exclude(status="inactive").select_related("owner").order_by("name"))
        online = pos_cashiers.online_kassa()
        kassas = stores + ([online] if online else [])
        links = list(StoreCashier.objects.filter(store__in=stores).select_related("user").order_by("user__full_name"))
        sessions = {s.store_id: s for s in CashSession.objects.filter(status="open", store__in=kassas).select_related("opened_by")}

        now = timezone.now()
        today = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = rep.rows(SaleModel.objects.filter(branch_id__in=[k.id for k in kassas], status__in=("completed", "refunded"), completed_at__gte=now - timedelta(days=30)))
        by_person: dict = {}
        by_kassa: dict = {}
        for r in rows:
            for key, bucket in ((r["cashier_id"], by_person), (r["branch_id"], by_kassa)):
                s = bucket.setdefault(key, {"today": 0, "today_rev": Decimal(0), "month": 0, "month_rev": Decimal(0)})
                s["month"] += r["status"] == "completed"
                s["month_rev"] += r["revenue"]
                if r["completed_at"] and r["completed_at"] >= today:
                    s["today"] += r["status"] == "completed"
                    s["today_rev"] += r["revenue"]

        def person(user, role, link=None):
            st = by_person.get(user.id, {})
            name = user.full_name or user.phone_number or "—"
            return {"id": str(user.id), "name": name, "phone": user.phone_number, "role": role, "initials": pos_cashiers.initials(name), "color": pos_cashiers.color_for(user.id),
                    "today": st.get("today", 0), "today_rev": _fmt(st.get("today_rev")), "month": st.get("month", 0), "month_rev": _fmt(st.get("month_rev")),
                    "last": _when(link.last_seen_at) if link else "", "since": _when(link.created_at)[:10] if link else "", "added_by": link.added_by if link else "",
                    "link_id": str(link.id) if link else None, "active": link.is_active if link else True,
                    "pay": f"{_fmt(link.base_salary)} + {link.kpi_percent.normalize()}%" if link else ""}

        cards = []
        for k in kassas:
            ses = sessions.get(k.id)
            st = by_kassa.get(k.id, {})
            people = []
            if k.kind != "warehouse":
                if k.owner_id and k.owner:
                    people.append(person(k.owner, "owner"))
                people += [person(lnk.user, "cashier", lnk) for lnk in links if lnk.store_id == k.id]
            cards.append({
                "id": str(k.id), "name": pos_cashiers.kassa_name(k), "location": k.name if k.kind == "warehouse" else ", ".join(x for x in (k.address, k.city) if x),
                "color": "#6366f1" if k.kind == "warehouse" else (k.color or "#64748b"), "online": k.kind == "warehouse",
                "has_pin": bool(k.pos_pin_hash), "pin_changed": _when(k.pos_pin_changed_at), "locked": pos_cashiers.locked_seconds(k) // 60 + 1 if pos_cashiers.locked_seconds(k) else 0,
                "open": bool(ses), "open_since": _when(ses.opened_at)[-5:] if ses else "", "open_by": _opened_by(ses) if ses else "",
                "shift_url": reverse("admin:stores_cashsession_change", args=[ses.id]) if ses else None,
                "today": st.get("today", 0), "today_rev": _fmt(st.get("today_rev")), "month_rev": _fmt(st.get("month_rev")),
                "people": people, "cashier_n": sum(p["role"] == "cashier" for p in people),
            })
        kpis = {
            "kassas": len(cards), "pins": sum(c["has_pin"] for c in cards), "cashiers": len(links), "open": sum(c["open"] for c in cards),
            "today_rev": _fmt(sum((by_kassa.get(k.id, {}).get("today_rev", 0) for k in kassas), Decimal(0))),
            "today": sum(by_kassa.get(k.id, {}).get("today", 0) for k in kassas),
        }
        ctx = {
            **self.admin_site.each_context(request), "title": _t("Kassalar va kassirlar"), "opts": self.model._meta, "cards": cards, "kpis": kpis,
            "can_edit": self.has_change_permission(request),
            "nz_cfg": {"users": reverse("admin:stores_storecashier_users"), "pin_errors": pos_cashiers.PIN_ERRORS,
                       "pin_error": request.GET.get("pin_error") if request.GET.get("pin_error") in pos_cashiers.PIN_ERRORS else "",
                       "pin_kassa": request.GET.get("pin_kassa", ""), "pin_ok": request.GET.get("pin_ok", "")},
            **(extra_context or {}),
        }
        from django.template.response import TemplateResponse

        return TemplateResponse(request, self.change_list_template, ctx)
