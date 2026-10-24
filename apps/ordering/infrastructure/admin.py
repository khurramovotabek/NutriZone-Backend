"""
Django Admin registration -- engineering/ops debugging tool only, per
Django Implementation Blueprint §13 and MIC §9's Admin Contract. Bulk
actions call Application Services exclusively.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import admin
from django.db.models import OuterRef, Q, Subquery
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.application.services.lifecycle import ArchiveOrder, CancelOrder
from apps.ordering.application.services.returns import RefundReturn
from apps.ordering.infrastructure import models as orm
from apps.ordering.infrastructure.composition import build_order_return_repository
from apps.ordering.infrastructure.repositories import DjangoOrderRepository
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from core.outbox import stage_event
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin


def _stage_ordering_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.OrderingOutboxEvent, event_type, payload)


def _admin_ctx(request) -> OrderingServiceContext:
    """Production context for dashboard actions: outbox events, location stock and the staff member's name in the order history."""
    from apps.ordering.infrastructure import admin_desk

    return admin_desk.staff_ctx(request)


def _redirect_back(request, fallback: str):
    from django.http import HttpResponseRedirect
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return HttpResponseRedirect(nxt)
    return HttpResponseRedirect(fallback)


class OrderLineItemInline(admin.TabularInline):
    model = orm.OrderLineItemModel
    extra = 0
    fields = ("product_variant_id", "quantity", "unit_price_amount", "status")


class OrderStatusHistoryInline(admin.TabularInline):
    model = orm.OrderStatusHistoryEntryModel
    extra = 0
    can_delete = False
    fields = ("from_status_badge", "to_status_badge", "reason", "changed_at", "actor_id")
    readonly_fields = ("from_status_badge", "to_status_badge", "reason", "changed_at", "actor_id")

    _STATUS_TONES = {"draft": "neutral", "pending_payment": "warning", "confirmed": "info", "processing": "info", "shipped": "info", "delivered": "success", "completed": "success", "cancelled": "danger", "returned": "danger", "failed": "danger"}

    def from_status_badge(self, obj: orm.OrderStatusHistoryEntryModel) -> str:
        if not obj.from_status:
            return "—"
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', self._STATUS_TONES.get(obj.from_status, "neutral"), obj.from_status)

    from_status_badge.short_description = "From"

    def to_status_badge(self, obj: orm.OrderStatusHistoryEntryModel) -> str:
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', self._STATUS_TONES.get(obj.to_status, "neutral"), obj.to_status)

    to_status_badge.short_description = "To"


_ORDER_STATUS_LABELS = {
    "draft": _("Qoralama"),
    "pending_payment": _("To'lov kutilmoqda"),
    "confirmed": _("Tasdiqlangan"),
    "processing": _("Yig'ilmoqda"),
    "shipped": _("Yo'lda"),
    "delivered": _("Yetkazilgan"),
    "completed": _("Yakunlangan"),
    "cancelled": _("Bekor qilingan"),
    "returned": _("Qaytarilgan"),
    "failed": _("Muvaffaqiyatsiz"),
}
# (colour, icon) per status -- the list, the tabs and the donut all speak the same visual language
_STATUS_STYLE = {
    "draft": ("#64748b", "fa-file"), "pending_payment": ("#f59e0b", "fa-hourglass-half"), "confirmed": ("#6366f1", "fa-circle-check"),
    "processing": ("#8b5cf6", "fa-box-open"), "shipped": ("#0ea5e9", "fa-truck-fast"), "delivered": ("#10b981", "fa-house-circle-check"),
    "completed": ("#16a34a", "fa-flag-checkered"), "cancelled": ("#e11d48", "fa-circle-xmark"), "returned": ("#f97316", "fa-rotate-left"),
    "failed": ("#b91c1c", "fa-triangle-exclamation"),
}
_EARNED = ("delivered", "completed")
_ORDER_STATUS_TONES = {"draft": "neutral", "pending_payment": "warning", "confirmed": "info", "processing": "info", "shipped": "info", "delivered": "success", "completed": "success", "cancelled": "danger", "returned": "danger", "failed": "danger"}
_CHANNEL_LABELS = {"web": _("Sayt"), "mobile": _("Mobil ilova"), "pos": _("POS terminal"), "api": _("API"), "telegram": _("Telegram bot")}
_CHANNEL_ICONS = {"web": "fa-globe", "mobile": "fa-mobile-screen", "pos": "fa-cash-register", "api": "fa-plug", "telegram": "fab fa-telegram"}


def _money(amount) -> str:
    return f"{int(round(Decimal(amount or 0))):,}".replace(",", " ")


class OrderStatusFilter(admin.SimpleListFilter):
    title = _("Status")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return list(_ORDER_STATUS_LABELS.items())

    def queryset(self, request, queryset):
        return queryset.filter(status=self.value()) if self.value() else queryset


class OrderChannelFilter(admin.SimpleListFilter):
    title = _("Channel")
    parameter_name = "channel"

    def lookups(self, request, model_admin):
        return list(_CHANNEL_LABELS.items())

    def queryset(self, request, queryset):
        return queryset.filter(channel=self.value()) if self.value() else queryset


LATE_HOURS = 24  # a confirmed/packing order untouched this long is late for same/next-day delivery (dashboard "Bugungi vazifalar" too)


def late_orders(queryset):
    from datetime import timedelta

    from django.utils import timezone

    return queryset.filter(is_archived=False, status__in=("confirmed", "processing"), updated_at__lt=timezone.now() - timedelta(hours=LATE_HOURS))


class OrderLateFilter(admin.SimpleListFilter):
    title = _("Kechikish")
    parameter_name = "late"

    def lookups(self, request, model_admin):
        return [("1", _("Kechikayotgan (%(h)s soat+)") % {"h": LATE_HOURS})]

    def queryset(self, request, queryset):
        return late_orders(queryset) if self.value() == "1" else queryset


class OrderArchivedFilter(admin.SimpleListFilter):
    title = _("Archive")
    parameter_name = "archived"

    def lookups(self, request, model_admin):
        return [("0", _("Active orders")), ("1", _("Archived"))]

    def queryset(self, request, queryset):
        if self.value() in ("0", "1"):
            return queryset.filter(is_archived=self.value() == "1")
        return queryset


@admin.register(orm.OrderModel)
class OrderAdmin(ExcelExportMixin, admin.ModelAdmin):
    excel_title = "Buyurtmalar"
    excel_columns = [
        Col("Buyurtma", "order_number", 18), Col("Berilgan", lambda o: o.placed_at or o.created_at, 17),
        Col("Holat", lambda o: str(_ORDER_STATUS_LABELS.get(o.status, o.status)), 18), Col("Kanal", "channel", 10),
        Col("Usul", lambda o: "Olib ketish" if o.fulfilment_method == "pickup" else "Yetkazib berish", 15), Col("Filial", lambda o: o.x_store, 20),
        Col("Mijoz", lambda o: o.x_customer[0], 24), Col("Telefon", lambda o: o.x_customer[1] or o.shipping_phone, 16),
        Col("Qabul qiluvchi", "shipping_recipient_name", 22), Col("Shahar", "shipping_city", 14),
        Col("Manzil", lambda o: ", ".join(x for x in (o.shipping_line1, o.shipping_line2) if x), 34),
        Col("Mahsulotlar (dona)", lambda o: o.x_units, 11, number=True), Col("Chegirma", lambda o: o.x_discount, 13, money=True),
        Col("Jami (so'm)", lambda o: o.x_total, 15, money=True), Col("Arxivda", "is_archived", 9), Col("Izoh", "customer_comment", 30),
    ]

    def excel_prepare(self, objs):
        from django.db.models import DecimalField, ExpressionWrapper, F, Sum

        ids = [o.id for o in objs]
        line = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
        sums = {r["order_id"]: r for r in orm.OrderLineItemModel.objects.filter(order_id__in=ids, status="active").values("order_id")
                .annotate(total=Sum(line), units=Sum("quantity"), discount=Sum("discount_amount"))}
        who, where = xl.people(o.customer_id for o in objs), xl.stores(o.fulfilment_store_id for o in objs)
        for o in objs:
            r = sums.get(o.id, {})
            o.x_total, o.x_units, o.x_discount = r.get("total") or Decimal(0), r.get("units") or 0, r.get("discount") or Decimal(0)
            o.x_customer, o.x_store = who.get(o.customer_id, ("", "")), where.get(o.fulfilment_store_id, "")

    # The buyer is shown by name and phone (never the raw customer UUID); payment type is cash-only for now.
    list_display = ("order_col", "status_col", "customer_col", "delivery_col", "total_col", "payment_type", "placed_col")
    list_display_links = ("order_col",)
    change_list_template = "admin/ordering/ordermodel/change_list.html"
    list_filter = (OrderStatusFilter, OrderChannelFilter, OrderArchivedFilter, OrderLateFilter)
    search_fields = ("order_number",)
    list_per_page = 25  # Phase 08.4's own explicit default pagination requirement
    # OrderModel has no Meta.ordering (id is a random UUID, not
    # chronological), so without this the change list previously came
    # back in arbitrary DB order. -created_at as the tiebreak covers
    # the rare not-yet-placed draft order (placed_at is nullable).
    ordering = ("-placed_at", "-created_at")
    inlines = [OrderLineItemInline, OrderStatusHistoryInline]
    readonly_fields = ("id", "version", "created_at", "updated_at", "financial_summary", "delivery_location", "coupon_ids", "promotion_ids")
    actions = ["cancel_selected", "archive_selected"]
    change_form_template = "admin/ordering/ordermodel/change_form.html"

    def has_add_permission(self, request) -> bool:
        return False  # orders come from checkout, the Telegram bot and POS -- a hand-typed order would skip prices, coins and stock

    def get_urls(self):
        from django.urls import path

        return [
            path("board/", self.admin_site.admin_view(self.board_view), name="ordering_ordermodel_board"),
            path("board/data/", self.admin_site.admin_view(self.board_data_view), name="ordering_ordermodel_board_data"),
            path("board/<uuid:pk>/move/", self.admin_site.admin_view(self.board_move_view), name="ordering_ordermodel_board_move"),
            path("board/<uuid:pk>/ship-options/", self.admin_site.admin_view(self.board_ship_options_view), name="ordering_ordermodel_board_ship_options"),
            path("delivery/", self.admin_site.admin_view(self.delivery_view), name="ordering_ordermodel_delivery"),
            path("delivery/<uuid:pk>/assign/", self.admin_site.admin_view(self.delivery_assign_view), name="ordering_ordermodel_delivery_assign"),
            path("delivery/<uuid:pk>/waybill/", self.admin_site.admin_view(self.delivery_waybill_view), name="ordering_ordermodel_delivery_waybill"),
            path("<uuid:pk>/act/", self.admin_site.admin_view(self.act_view), name="ordering_ordermodel_act"),
            path("<uuid:pk>/note/", self.admin_site.admin_view(self.note_view), name="ordering_ordermodel_note"),
        ] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """The order workspace. Read-only page; every change goes through act_view / note_view (Application Services), never a raw form save."""
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseRedirect
        from django.shortcuts import get_object_or_404
        from django.template.response import TemplateResponse

        from apps.ordering.infrastructure import admin_desk

        order = get_object_or_404(orm.OrderModel, pk=object_id)
        if not self.has_view_or_change_permission(request, order):
            raise PermissionDenied
        if request.method != "GET":
            return HttpResponseRedirect(request.path)
        context = {
            **self.admin_site.each_context(request),
            "title": order.order_number, "opts": self.model._meta, "original": order, "desk": admin_desk.order_snapshot(order),
            "has_change_permission": self.has_change_permission(request, order), "preserved_filters": self.get_preserved_filters(request),
            "nz_order_flow": admin_desk.ORDER_FLOW,
            "nz_payments": _order_payments(order),
        }
        return TemplateResponse(request, self.change_form_template, context)

    ORDER_ACTION_DONE = {
        "confirm": _("Order confirmed."), "start_processing": _("Packing started."), "ship": _("Handed over to the courier."),
        "deliver": _("Marked as delivered."), "complete": _("Order completed."), "cancel": _("Order cancelled."),
        "archive": _("Order archived."), "restore": _("Order restored from the archive."),
    }

    def run_order_action(self, request, order, action: str, store_id=None, reason: str = "", note: str = "") -> str:
        """The one way the dashboard changes an order (workspace buttons and the board). Returns the success text; raises on rejection."""
        from apps.ordering.application.services import lifecycle as lc
        from apps.ordering.infrastructure import admin_desk

        services = {
            "confirm": lc.ConfirmOrder, "start_processing": lc.StartOrderProcessing, "ship": lc.ShipOrder, "deliver": lc.DeliverOrder,
            "complete": lc.CompleteOrder, "cancel": lc.CancelOrder, "archive": lc.ArchiveOrder, "restore": lc.RestoreOrder,
        }
        if action not in services:
            raise ValueError(_("Unknown action."))
        service = services[action](DjangoOrderRepository(), _admin_ctx(request))
        if action == "ship":
            service.execute(order.id, store_id=uuid_or_none(store_id))
        elif action == "cancel":
            code = reason if reason in admin_desk.CANCEL_REASON else "admin_action"
            service.execute(order.id, reason=f"cancellation:{code}")
            if note.strip():
                orm.OrderModel.objects.filter(pk=order.pk).update(note=_append_note(order.note, note.strip()))
        else:
            service.execute(order.id)
        return str(self.ORDER_ACTION_DONE[action])

    def act_view(self, request, pk):
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseNotAllowed
        from django.shortcuts import get_object_or_404
        from django.urls import reverse

        from apps.ordering.infrastructure import admin_desk

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        order = get_object_or_404(orm.OrderModel, pk=pk)
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        back = reverse("admin:ordering_ordermodel_change", args=[order.pk])
        if request.POST.get("action") == "assign_store":
            return self._assign_store(request, order, back)
        try:
            text = self.run_order_action(request, order, request.POST.get("action", ""), request.POST.get("store_id") or None,
                                         request.POST.get("reason") or "", request.POST.get("note") or "")
        except Exception as exc:  # noqa: BLE001 -- domain/application rejections become a readable message, never a 500
            messages.error(request, admin_desk.error_text(exc))
        else:
            messages.success(request, text)
        return _redirect_back(request, back)

    def _assign_store(self, request, order, back):
        """Hand a delivery to a branch (or back to the main warehouse); the branch owner is told and moves it from the storefront."""
        from django.contrib import messages

        from apps.stores.infrastructure import store_orders
        from apps.stores.infrastructure.models import Store

        sid = request.POST.get("assign_store_id") or ""
        store = Store.objects.filter(pk=uuid_or_none(sid)).first() if sid else None
        if sid and store is None:
            messages.error(request, _("Store not found."))
            return _redirect_back(request, back)
        label = request.user.get_full_name() or request.user.get_username()
        try:
            store_orders.assign(order, store, by=label)
        except store_orders.StoreOrderError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, (_("Assigned to %(store)s — the store owner was notified.") % {"store": store.name}) if store else _("Back with the main warehouse."))
        return _redirect_back(request, back)

    # ------------------------------------------------------------------ dispatcher board

    def board_view(self, request):
        from django.core.exceptions import PermissionDenied
        from django.template.response import TemplateResponse

        if not self.has_view_permission(request):
            raise PermissionDenied
        from django.utils.translation import gettext as t

        i18n = {
            "next": {"confirm": t("Confirm"), "start_processing": t("Start packing"), "ship": t("To courier"), "deliver": t("Delivered")},
            "empty": t("No orders here"), "emptyDelivered": t("Nothing delivered in the last 3 days"), "items": t("items"), "open": t("Open"),
            "comment": t("Customer left a comment"), "note": t("Has an internal note"), "short": t("Not enough stock at the main warehouse"),
            "requests": t("Open return / cancellation request"), "coins": t("Partly paid with coins"), "oneStep": t("An order only moves one step forward."),
            "error": t("Could not save. Please try again."), "min": t("min"), "h": t("h"), "d": t("d"), "drop": t("Drop here"),
            "noFilter": t("Nothing matches the filter"), "paused": t("paused"), "late": t("late"), "reserved": t("reserved here"),
            "allIn": t("Everything in stock"), "noLocations": t("No location to ship from."), "short_n": t("short"),
        }
        context = {**self.admin_site.each_context(request), "title": _("Order board"), "opts": self.model._meta,
                   "has_change_permission": self.has_change_permission(request), "nz_board_i18n": i18n}
        return TemplateResponse(request, "admin/ordering/ordermodel/board.html", context)

    def board_data_view(self, request):
        from django.core.exceptions import PermissionDenied
        from django.http import JsonResponse

        from apps.ordering.infrastructure import admin_board

        if not self.has_view_permission(request):
            raise PermissionDenied
        return JsonResponse(admin_board.board_payload())

    def board_move_view(self, request, pk):
        import json

        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        from apps.ordering.infrastructure import admin_board, admin_desk

        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "POST required"}, status=405)
        order = get_object_or_404(orm.OrderModel, pk=pk)
        if not self.has_change_permission(request, order):
            return JsonResponse({"ok": False, "error": str(_("You don't have permission to change orders."))}, status=403)
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid body"}, status=400)
        action = body.get("action", "")
        expected = admin_board.NEXT_ACTION.get(order.status)
        if action != expected and action != "cancel":
            return JsonResponse({"ok": False, "error": str(_("An order only moves one step forward. Refresh the board."))}, status=409)
        try:
            text = self.run_order_action(request, order, action, body.get("store_id"), body.get("reason") or "", body.get("note") or "")
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({"ok": False, "error": admin_desk.error_text(exc)}, status=422)
        order.refresh_from_db()
        return JsonResponse({"ok": True, "message": text, "status": order.status})

    def board_ship_options_view(self, request, pk):
        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        from apps.ordering.infrastructure import admin_board

        if not self.has_view_permission(request):
            return JsonResponse({"ok": False}, status=403)
        order = get_object_or_404(orm.OrderModel, pk=pk)
        return JsonResponse({"ok": True, "locations": admin_board.ship_options(order)})

    # ------------------------------------------------------------------ delivery desk

    def delivery_view(self, request):
        """Yetkazib berish markazi: delivery orders by stage with items, address, courier and the cash to collect."""
        from django.core.exceptions import PermissionDenied
        from django.template.response import TemplateResponse

        from apps.ordering.infrastructure import admin_delivery

        if not self.has_view_permission(request):
            raise PermissionDenied
        g = request.GET
        desk = admin_delivery.desk_payload(g.get("stage") or "prepare", (g.get("q") or "").strip()[:80], g.get("city") or "", g.get("courier") or "", g.get("day") or "")
        context = {**self.admin_site.each_context(request), "title": _("Delivery"), "opts": self.model._meta, "desk": desk,
                   "has_change_permission": self.has_change_permission(request)}
        return TemplateResponse(request, "admin/ordering/ordermodel/delivery.html", context)

    def delivery_assign_view(self, request, pk):
        import json

        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        from apps.ordering.infrastructure import admin_delivery

        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "POST required"}, status=405)
        order = get_object_or_404(orm.OrderModel, pk=pk)
        if not self.has_change_permission(request, order):
            return JsonResponse({"ok": False, "error": str(_("You don't have permission to change orders."))}, status=403)
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid body"}, status=400)
        try:
            row = admin_delivery.assign(order, body, request.user.get_full_name() or request.user.get_username())
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=422)
        return JsonResponse({"ok": True, "message": str(_("Saved.")), "courier": row.courier.name if row.courier else "", "courier_id": str(row.courier_id or "")})

    def delivery_waybill_view(self, request, pk):
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import get_object_or_404
        from django.template.response import TemplateResponse

        from apps.ordering.infrastructure import admin_delivery

        if not self.has_view_permission(request):
            raise PermissionDenied
        order = get_object_or_404(orm.OrderModel, pk=pk)
        return TemplateResponse(request, "admin/ordering/ordermodel/waybill.html", {"w": admin_delivery.waybill(order), "auto_print": request.GET.get("print") == "1"})

    def note_view(self, request, pk):
        """The internal (staff-only) note on the order."""
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseNotAllowed
        from django.shortcuts import get_object_or_404
        from django.urls import reverse

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        order = get_object_or_404(orm.OrderModel, pk=pk)
        if not self.has_change_permission(request, order):
            raise PermissionDenied
        orm.OrderModel.objects.filter(pk=order.pk).update(note=(request.POST.get("note") or "").strip()[:4000] or None)
        messages.success(request, _("Note saved."))
        return _redirect_back(request, reverse("admin:ordering_ordermodel_change", args=[order.pk]))

    def get_queryset(self, request):
        from apps.identity.infrastructure.models import User

        buyer = User.objects.filter(id=OuterRef("customer_id"))
        return (
            super().get_queryset(request)
            .annotate(buyer_full_name=Subquery(buyer.values("full_name")[:1]), buyer_phone=Subquery(buyer.values("phone_number")[:1]))
            .prefetch_related("lines")
        )

    def get_search_results(self, request, queryset, search_term):
        """Order number, buyer name or buyer phone (account or delivery contact) -- no UUIDs to type."""
        term = search_term.strip()
        if not term:
            return queryset, False
        match = Q(order_number__icontains=term) | Q(buyer_full_name__icontains=term) | Q(shipping_recipient_name__icontains=term)
        digits = "".join(ch for ch in term if ch.isdigit())
        if len(digits) >= 3:
            match |= Q(buyer_phone__icontains=digits) | Q(shipping_phone__icontains=digits)
        return queryset.filter(match), False

    # ------------------------------------------------------------------ premium list

    def changelist_view(self, request, extra_context=None):
        from datetime import timedelta

        from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
        from django.utils import timezone

        from apps.products.infrastructure import catalog_analytics as ca
        from apps.products.infrastructure.catalog_admin_ui import kpi

        now = timezone.now()
        start, prev_start = now - timedelta(days=30), now - timedelta(days=60)
        today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        real = orm.OrderModel.objects.exclude(status="draft")
        line_value = ExpressionWrapper(F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))

        def revenue(qs):
            return qs.filter(lines__status="active").aggregate(t=Sum(line_value))["t"] or Decimal(0)

        earned = real.filter(status__in=_EARNED, placed_at__gte=start)
        earned_prev = real.filter(status__in=_EARNED, placed_at__gte=prev_start, placed_at__lt=start)
        rev, rev_prev = revenue(earned), revenue(earned_prev)
        n_earned = earned.count()
        month = real.filter(placed_at__gte=start)
        lost = month.filter(status__in=("cancelled", "returned", "failed")).count()
        todays = real.filter(placed_at__gte=today)
        counts = dict(real.filter(is_archived=False).values_list("status").annotate(n=Count("id")))

        # best customers of the month by delivered spend
        from apps.identity.infrastructure.models import User

        spend = (earned.filter(customer_id__isnull=False, lines__status="active").values("customer_id").annotate(t=Sum(line_value), n=Count("id", distinct=True)).order_by("-t")[:5])
        names = {u.id: u.full_name or u.phone_number for u in User.objects.filter(id__in=[r["customer_id"] for r in spend])}
        lead = spend[0]["t"] if spend else 1
        ranking = [{"label": names.get(r["customer_id"], "Mijoz"), "revenue": ca.compact(r["t"]), "units": r["n"], "units_text": f"{r['n']} ta buyurtma", "pct": max(int(r["t"] * 100 / lead), 3), "color": ca.PALETTE[i], "change": None} for i, r in enumerate(spend)]

        donut = ca.donut([(str(_ORDER_STATUS_LABELS.get(k, k)), v) for k, v in month.values_list("status").annotate(n=Count("id"))], limit=8)
        colors = {str(_ORDER_STATUS_LABELS[k]): v[0] for k, v in _STATUS_STYLE.items()}
        acc, stops = 0.0, []
        for item in donut["legend"]:
            item["color"] = colors.get(item["label"], item["color"])
            a0, acc = acc, acc + item["value"] * 100 / (donut["total"] or 1)
            stops.append(f"{item['color']} {a0:.2f}% {acc:.2f}%")
        donut["gradient"] = f"conic-gradient({', '.join(stops)})" if stops else ""

        nzc = {
            "kpis": [
                kpi("Bugun", todays.count(), "fa-calendar-day", "#2563eb", f"{ca.compact(revenue(todays))} so'm"),
                kpi("Ishlov kutmoqda", counts.get("pending_payment", 0) + counts.get("confirmed", 0), "fa-inbox", "#f59e0b", f"{counts.get('pending_payment', 0)} tasi to'lov kutyapti"),
                kpi("Jarayonda", counts.get("processing", 0) + counts.get("shipped", 0), "fa-truck-fast", "#0ea5e9", f"{counts.get('shipped', 0)} tasi yo'lda"),
                kpi("30 kunlik tushum", ca.compact(rev), "fa-sack-dollar", "#10b981", f"{n_earned} ta yetkazilgan", round(float((rev - rev_prev) / rev_prev * 100)) if rev_prev else None),
                kpi("O'rtacha chek", ca.compact(rev / n_earned) if n_earned else "—", "fa-receipt", "#8b5cf6", "yetkazilgan buyurtmalar"),
                kpi("Yo'qotilgan", f"{round(lost * 100 / month.count()) if month.count() else 0}%", "fa-circle-xmark", "#e11d48", f"{lost} ta bekor / qaytarilgan"),
            ],
            "ranking_title": "Eng faol mijozlar", "ranking": {"rows": ranking},
            "donut_title": "Holatlar (30 kun)", "donut_unit": "buyurtma", "donut": donut,
        }
        current = request.GET.get("status", "")
        tabs = [{"key": "", "label": "Hammasi", "n": sum(counts.values()), "color": "#64748b", "icon": "fa-layer-group", "on": not current}]
        for key in ("pending_payment", "confirmed", "processing", "shipped", "delivered", "completed", "cancelled", "returned"):
            color, icon = _STATUS_STYLE[key]
            tabs.append({"key": key, "label": _ORDER_STATUS_LABELS[key], "n": counts.get(key, 0), "color": color, "icon": icon, "on": current == key})
        return super().changelist_view(request, {**(extra_context or {}), "nzc": nzc, "order_tabs": tabs, "title": _("Buyurtmalar")})

    def get_changelist_instance(self, request):
        """One bulk lookup per page: product thumbnails for every line shown (never a query per row)."""
        cl = super().get_changelist_instance(request)
        from apps.products.infrastructure.models import ProductMedia, ProductVariant

        vids = {line.product_variant_id for o in cl.result_list for line in o.lines.all()}
        product_of = dict(ProductVariant.all_objects.filter(id__in=vids).values_list("id", "product_id"))
        thumbs = {}
        for m in ProductMedia.objects.filter(product_id__in=set(product_of.values())).order_by("sort_order").values("product_id", "storage_path", "thumbnail_paths"):
            thumbs.setdefault(m["product_id"], (m["thumbnail_paths"] or {}).get("small") or m["storage_path"])
        self._thumbs = {vid: thumbs.get(pid) for vid, pid in product_of.items()}
        return cl

    @admin.display(description=_("Buyurtma"), ordering="order_number")
    def order_col(self, obj: orm.OrderModel) -> str:
        from django.utils.safestring import mark_safe

        active = [line for line in obj.lines.all() if line.status == "active"]
        icon = _CHANNEL_ICONS.get(obj.channel, "fa-globe")
        icon = icon if icon.startswith("fab") else f"fas {icon}"
        thumbs = getattr(self, "_thumbs", {})
        pics = "".join(
            format_html('<img src="/media/{}" alt="" loading="lazy">', thumbs[line.product_variant_id]) if thumbs.get(line.product_variant_id) else '<span class="ph"><i class="fas fa-box"></i></span>'
            for line in active[:3]
        )
        more = format_html('<span class="ph">+{}</span>', len(active) - 3) if len(active) > 3 else ""
        return format_html(
            '<div class="nzo-who"><span class="nzo-items">{}{}</span><span class="nzc-name"><b class="nz-num">{}</b><small><i class="{}"></i> {} · {} ta mahsulot</small></span></div>',
            mark_safe(pics), more, obj.order_number, icon, _CHANNEL_LABELS.get(obj.channel, obj.channel), sum(line.quantity for line in active),
        )

    @admin.display(description=_("Holat"), ordering="status")
    def status_col(self, obj: orm.OrderModel) -> str:
        color, icon = _STATUS_STYLE.get(obj.status, ("#64748b", "fa-circle"))
        archived = format_html(' <span class="nzc-pill" style="--t:#64748b">{}</span>', "Arxiv") if obj.is_archived else ""
        return format_html('<span class="nzc-pill" style="--t:{}"><i class="fas {}"></i> {}</span>{}', color, icon, _ORDER_STATUS_LABELS.get(obj.status, obj.status), archived)

    @admin.display(description=_("Mijoz"), ordering="buyer_full_name")
    def customer_col(self, obj: orm.OrderModel) -> str:
        name = getattr(obj, "buyer_full_name", None) or obj.shipping_recipient_name or "Mijoz"
        phone = getattr(obj, "buyer_phone", None) or obj.shipping_phone
        initials = "".join(p[0] for p in name.split()[:2]).upper() or "?"
        return format_html('<div class="nzo-who"><span class="nzo-av">{}</span><span class="nzc-name"><b>{}</b><small>{}</small></span></div>', initials, name, phone or "—")

    @admin.display(description=_("Yetkazish"))
    def delivery_col(self, obj: orm.OrderModel) -> str:
        place = ", ".join(p for p in (obj.shipping_city, obj.shipping_region) if p) or "—"
        pin = format_html(' <a href="https://maps.google.com/?q={},{}" target="_blank" rel="noopener" title="Xaritada" class="nzo-pin"><i class="fas fa-location-dot"></i></a>', obj.shipping_latitude, obj.shipping_longitude) if obj.shipping_latitude is not None else ""
        line = (obj.shipping_line1 or "")[:48]
        return format_html('<div class="nzc-name"><b>{}{}</b><small>{}</small></div>', place, pin, line)

    @admin.display(description=_("Summa"))
    def total_col(self, obj: orm.OrderModel) -> str:
        active = [line for line in obj.lines.all() if line.status == "active"]
        total = sum((line.unit_price_amount * line.quantity - line.discount_amount + line.tax_amount for line in active), Decimal("0"))
        return format_html('<b class="nz-num">{}</b> <span class="nz-text-muted">{}</span>', _money(total), _("so'm") if obj.currency == "UZS" else obj.currency)

    @admin.display(description=_("Sana"), ordering="placed_at")
    def placed_col(self, obj: orm.OrderModel) -> str:
        from django.utils import timezone

        when = obj.placed_at or obj.created_at
        if not when:
            return "—"
        secs = (timezone.now() - when).total_seconds()
        ago = "hozirgina" if secs < 60 else f"{int(secs // 60)} daq oldin" if secs < 3600 else f"{int(secs // 3600)} soat oldin" if secs < 86400 else f"{int(secs // 86400)} kun oldin"
        return format_html('<div class="nzc-name"><b>{}</b><small>{}</small></div>', ago, timezone.localtime(when).strftime("%d.%m.%Y %H:%M"))

    @admin.display(description=_("Order"), ordering="order_number")
    def order_number_display(self, obj: orm.OrderModel) -> str:
        return format_html('<strong class="nz-num">{}</strong>', obj.order_number)

    @admin.display(description=_("Customer"), ordering="buyer_full_name")
    def customer_name(self, obj: orm.OrderModel) -> str:
        name = getattr(obj, "buyer_full_name", None) or obj.shipping_recipient_name
        if not name:
            return format_html('<span class="nz-text-muted">{}</span>', _("Unknown"))
        return name

    @admin.display(description=_("Phone"))
    def customer_phone(self, obj: orm.OrderModel) -> str:
        phone = getattr(obj, "buyer_phone", None) or obj.shipping_phone
        return format_html('<a href="tel:{}" class="nz-num">{}</a>', phone, phone) if phone else "—"

    @admin.display(description=_("Total"))
    def order_total(self, obj: orm.OrderModel) -> str:
        """Same formula as financial_summary (subtotal - discount + tax over active lines), from the prefetched lines."""
        active = [line for line in obj.lines.all() if line.status == "active"]
        total = sum((line.unit_price_amount * line.quantity - line.discount_amount + line.tax_amount for line in active), Decimal("0"))
        return format_html('<strong class="nz-num">{}</strong> <span class="nz-text-muted">{}</span>', _money(total), _("so'm") if obj.currency == "UZS" else obj.currency)

    @admin.display(description=_("To'lov"))
    def payment_type(self, obj: orm.OrderModel) -> str:
        # Only cash is accepted today; card/online types will be listed here once they exist.
        return format_html('<span class="nzc-pill nz-badge-success" style="--t:#10b981"><i class="fas fa-money-bill-wave" aria-hidden="true"></i> {}</span>', _("Naqd"))

    @admin.display(description=_("Channel"), ordering="channel")
    def channel_display(self, obj: orm.OrderModel) -> str:
        return _CHANNEL_LABELS.get(obj.channel, obj.channel)

    @admin.display(description=_("Date"), ordering="placed_at")
    def placed_at_display(self, obj: orm.OrderModel) -> str:
        from django.utils import timezone

        when = obj.placed_at or obj.created_at
        return timezone.localtime(when).strftime("%d.%m.%Y %H:%M") if when else "—"

    def delivery_location(self, obj: orm.OrderModel) -> str:
        """Real, closed gap: shipping_latitude/longitude (added this phase) previously had no dedicated admin presentation -- shown here as a clickable Google Maps link, or an honest 'not provided' state, rather than a raw float pair a dispatcher would have to copy-paste manually."""
        if obj.shipping_latitude is None or obj.shipping_longitude is None:
            return mark_safe('<span class="nz-empty-state">No GPS location provided for this address.</span>')
        maps_url = f"https://maps.google.com/?q={obj.shipping_latitude},{obj.shipping_longitude}"
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">\U0001F4CD {}, {}</a>', maps_url, obj.shipping_latitude, obj.shipping_longitude)

    delivery_location.short_description = "Delivery Location"

    def financial_summary(self, obj: orm.OrderModel) -> str:
        """
        Phase 08.4: 'Financial Summary' section. Reuses the exact
        same formula already certified in OrderStatisticsSelector.
        total_revenue_by_status() -- subtotal - discount + tax over
        ACTIVE line items only -- rather than inventing a second,
        alternative monetary formula (this phase's own explicit
        requirement). Computed from the already-prefetched `lines`,
        never a per-row query.

        Phase C1: upgraded from a plain <br>-separated line to a
        premium, --nz-* token-based table -- same real formula,
        premium visual presentation.
        """
        active_lines = [line for line in obj.lines.all() if line.status == "active"]
        subtotal = sum((line.unit_price_amount * line.quantity for line in active_lines), Decimal("0"))
        discount = sum((line.discount_amount for line in active_lines), Decimal("0"))
        tax = sum((line.tax_amount for line in active_lines), Decimal("0"))
        total = subtotal - discount + tax
        return format_html(
            '<table class="nz-financial-summary">'
            '<tr><td>Subtotal</td><td>{} {}</td></tr>'
            '<tr><td>Discount</td><td>-{} {}</td></tr>'
            '<tr><td>Tax</td><td>+{} {}</td></tr>'
            '<tr class="nz-financial-total"><td>Total</td><td>{} {}</td></tr>'
            "</table>",
            subtotal, obj.currency, discount, obj.currency, tax, obj.currency, total, obj.currency,
        )

    financial_summary.short_description = "Financial Summary"

    fieldsets = (
        ("Order Information", {"fields": ("order_number", "customer_id", "cart_id", "currency", "order_type", "channel", "status", "lock_reason", "is_archived", "placed_at")}),
        ("Financial Summary", {"fields": ("financial_summary",)}),
        ("Notes", {"fields": ("note", "customer_comment"), "classes": ("collapse",)}),
        ("Coupons & Promotions", {"fields": ("coupon_ids", "promotion_ids"), "classes": ("collapse",)}),
        ("System", {"fields": ("id", "version", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: orm.OrderModel) -> str:
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', _ORDER_STATUS_TONES.get(obj.status, "neutral"), _ORDER_STATUS_LABELS.get(obj.status, obj.status))

    @admin.display(description=_("Items"))
    def line_count(self, obj: orm.OrderModel) -> int:
        """Fixed a genuine N+1: `.filter()` on a prefetch_related-cached manager bypasses the cache entirely and re-queries per row (the same bug class found and fixed in Phase 08.3's ProductAdmin). Counting the already-prefetched, already-in-memory list in Python instead."""
        return sum(1 for line in obj.lines.all() if line.status == "active")

    @admin.action(description=_("Cancel selected orders"))
    def cancel_selected(self, request, queryset):
        service = CancelOrder(DjangoOrderRepository(), _admin_ctx(request))
        for order in queryset:
            try:
                service.execute(order.id, reason="admin_bulk_cancel")
            except Exception:  # noqa: BLE001
                self.message_user(request, f"Could not cancel {order.order_number}.", level="error")

    @admin.action(description=_("Archive selected orders"))
    def archive_selected(self, request, queryset):
        service = ArchiveOrder(DjangoOrderRepository(), _admin_ctx(request))
        for order in queryset:
            try:
                service.execute(order.id)
            except Exception:  # noqa: BLE001
                pass


# Real, product-required simplification: removed from Dashboard -- already visible as an inline on the Order admin page itself -- a separate standalone page is redundant.
# @admin.register(orm.OrderLineItemModel)
class OrderLineItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_variant_id", "quantity", "status")
    list_filter = ("status",)
    list_per_page = 25


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal audit log an admin never creates or edits by hand.
# @admin.register(orm.OrderStatusHistoryEntryModel)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    """Read-only -- append-only, per MIC §9."""

    list_display = ("order", "from_status", "to_status", "changed_at")
    readonly_fields = [f.name for f in orm.OrderStatusHistoryEntryModel._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


# Real, product-required simplification: removed from Dashboard -- cross-app reference data, best viewed via the Order it belongs to, not as its own workspace.
# @admin.register(orm.OrderPaymentReferenceModel)
class OrderPaymentReferenceAdmin(admin.ModelAdmin):
    list_display = ("order", "payment_id", "amount", "currency", "status")
    list_filter = ("status",)
    search_fields = ("order__order_number", "payment_id")
    list_per_page = 25


# Real, product-required simplification: removed from Dashboard -- references the Fulfillment module, which was removed from this project entirely -- this page would only ever show empty/dead data now.
# @admin.register(orm.OrderFulfillmentReferenceModel)
class OrderFulfillmentReferenceAdmin(admin.ModelAdmin):
    list_display = ("order", "fulfillment_id", "status", "tracking_number")
    list_filter = ("status",)
    search_fields = ("order__order_number", "fulfillment_id", "tracking_number")
    list_per_page = 25


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal audit log an admin never creates or edits by hand.
# @admin.register(orm.OrderFailureModel)
class OrderFailureAdmin(admin.ModelAdmin):
    """Read-only -- append-only."""

    list_display = ("order", "reason", "occurred_at")
    readonly_fields = [f.name for f in orm.OrderFailureModel._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


def uuid_or_none(value):
    import uuid as _uuid

    try:
        return _uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _append_note(existing: str | None, addition: str) -> str:
    return f"{existing}\n{addition}" if existing else addition


class _WorkflowAdmin(admin.ModelAdmin):
    """Shared premium list / workspace / create page for OrderReturn and OrderCancellation."""

    kind = ""  # "return" | "cancel"
    list_per_page = 25
    list_filter = ("status", "reason")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")

    def has_change_permission(self, request, obj=None) -> bool:
        return super().has_change_permission(request, obj)

    def _desk(self):
        from apps.ordering.infrastructure import admin_desk

        return admin_desk

    def _table(self):
        d = self._desk()
        return (d.RETURN_STATUS, d.RETURN_REASON) if self.kind == "return" else (d.CANCEL_STATUS, d.CANCEL_REASON)

    def get_search_results(self, request, queryset, search_term):
        from apps.identity.infrastructure.models import User

        term = (search_term or "").strip()
        if not term:
            return queryset, False
        orders = orm.OrderModel.objects.filter(Q(order_number__icontains=term) | Q(shipping_recipient_name__icontains=term))
        digits = "".join(ch for ch in term if ch.isdigit())
        users = User.objects.filter(Q(full_name__icontains=term) | (Q(phone_number__icontains=digits) if len(digits) >= 3 else Q(pk__in=[])))
        orders = orders | orm.OrderModel.objects.filter(customer_id__in=users.values("id"))
        if len(digits) >= 3:
            orders = orders | orm.OrderModel.objects.filter(shipping_phone__icontains=digits)
        match = Q(order_id__in=orders.values("id"))
        if self.kind == "return":
            match |= Q(return_number__icontains=term)
        else:
            match |= Q(id__startswith=term.lower().removeprefix("bek-")) if len(term) >= 4 else Q(pk__in=[])
        return queryset.filter(match), False

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        self._desk().annotate_rows(cl.result_list, self.kind)  # iterating fills the page's result cache
        return cl

    def changelist_view(self, request, extra_context=None):
        statuses, reasons = self._table()
        kpis = self._desk().list_kpis(self.model, statuses)
        current = request.GET.get("status__exact", "")
        counts = kpis["counts"]
        tabs = [{"key": "", "label": _("All"), "n": kpis["total"], "color": "#64748b", "icon": "fa-layer-group", "on": not current}]
        for key, (label, color, icon) in statuses.items():
            if key == "closed" and not counts.get(key):
                continue
            tabs.append({"key": key, "label": label, "n": counts.get(key, 0), "color": color, "icon": icon, "on": current == key})
        extra = {
            "nz_kind": self.kind, "nz_tabs": tabs, "nz_kpis": kpis, "nz_status": current, "nz_query": request.GET.get("q", ""),
            "nz_reason": request.GET.get("reason__exact", ""), "nz_reasons": list(reasons.items()),
            "title": _("Returns") if self.kind == "return" else _("Cancellations"),
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseRedirect
        from django.shortcuts import get_object_or_404
        from django.template.response import TemplateResponse

        obj = get_object_or_404(self.model, pk=object_id)
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        if request.method != "GET":
            return HttpResponseRedirect(request.path)
        desk = self._desk().workflow_snapshot(obj, self.kind)
        context = {
            **self.admin_site.each_context(request), "title": desk["number"], "opts": self.model._meta, "original": obj, "desk": desk,
            "has_change_permission": self.has_change_permission(request, obj), "has_delete_permission": self.has_delete_permission(request, obj),
            "preserved_filters": self.get_preserved_filters(request),
        }
        return TemplateResponse(request, self.change_form_template, context)

    def add_view(self, request, form_url="", extra_context=None):
        """New return / cancellation: find the order, choose items and quantities, pick a reason."""
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseRedirect
        from django.template.response import TemplateResponse
        from django.urls import reverse

        if not self.has_add_permission(request):
            raise PermissionDenied
        desk = self._desk()
        statuses, reasons = self._table()
        errors, posted = [], {}
        order_id = uuid_or_none(request.POST.get("order_id") or request.GET.get("order"))
        if request.method == "POST" and order_id:
            posted = request.POST
            try:
                obj_id = self._create(request, order_id, desk)
            except Exception as exc:  # noqa: BLE001
                errors.append(desk.error_text(exc))
            else:
                messages.success(request, _("Return request created.") if self.kind == "return" else _("Cancellation created."))
                return HttpResponseRedirect(reverse(f"admin:ordering_{self.model._meta.model_name}_change", args=[obj_id]))
        order = orm.OrderModel.objects.filter(pk=order_id).first() if order_id else None
        snapshot = desk.order_snapshot(order) if order else None
        eligible = bool(snapshot and (snapshot["can_return"] if self.kind == "return" else snapshot["can_request_cancellation"]))
        q = request.GET.get("q", "")
        context = {
            **self.admin_site.each_context(request), "opts": self.model._meta, "nz_kind": self.kind,
            "title": _("New return") if self.kind == "return" else _("New cancellation"),
            "q": q, "results": desk.find_orders(q, self.kind) if not order else [], "order": order, "snap": snapshot, "eligible": eligible,
            "reasons": list(reasons.items()), "errors": errors, "posted": posted,
            "window_expired": self._window_expired(snapshot) if self.kind == "return" and snapshot else False,
        }
        return TemplateResponse(request, f"admin/ordering/{self.model._meta.model_name}/add.html", context)

    def _window_expired(self, snapshot) -> bool:
        from datetime import timedelta

        from django.utils import timezone as tz

        delivered = next((h["at"] for h in reversed(snapshot["history"]) if h["key"] == "delivered"), None)
        return bool(delivered and tz.now() - delivered > timedelta(days=14))

    def get_urls(self):
        from django.urls import path

        name = self.model._meta.model_name
        return [path("<uuid:pk>/act/", self.admin_site.admin_view(self.act_view), name=f"ordering_{name}_act")] + super().get_urls()

    def act_view(self, request, pk):
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseNotAllowed
        from django.shortcuts import get_object_or_404
        from django.urls import reverse

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = get_object_or_404(self.model, pk=pk)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        back = reverse(f"admin:ordering_{self.model._meta.model_name}_change", args=[obj.pk])
        desk = self._desk()
        action = request.POST.get("action", "")
        try:
            text = self._act(request, obj, action, desk)
        except Exception as exc:  # noqa: BLE001
            messages.error(request, desk.error_text(exc))
        else:
            if text:
                messages.success(request, text)
        return _redirect_back(request, back)

    def _save_note(self, obj, addition: str) -> None:
        addition = (addition or "").strip()
        if addition:
            self.model.objects.filter(pk=obj.pk).update(note=_append_note(obj.note, addition)[:4000])


class ReturnLineItemInline(admin.TabularInline):
    model = orm.ReturnLineItemModel
    extra = 0


@admin.register(orm.OrderReturnModel)
class OrderReturnAdmin(ExcelExportMixin, _WorkflowAdmin):
    excel_title = "Buyurtma qaytarishlar"
    excel_columns = [
        Col("Qaytarish", "return_number", 16), Col("Buyurtma", lambda r: r.x_order, 18), Col("Holat", "status", 12), Col("Sabab", "reason", 18),
        Col("So'ralgan", "requested_at", 17), Col("Tasdiqlangan", "approved_at", 17), Col("Qabul qilingan", "received_at", 17), Col("Pul qaytarilgan", "refunded_at", 17),
        Col("Qaytarilgan summa", "refund_amount", 15, money=True), Col("Izoh", "note", 28), Col("Rad etish sababi", "rejection_reason", 24),
    ]

    def excel_prepare(self, objs):
        numbers = dict(orm.OrderModel.objects.filter(id__in=[r.order_id for r in objs]).values_list("id", "order_number"))
        for r in objs:
            r.x_order = numbers.get(r.order_id, "")

    kind = "return"
    list_display = ("return_number", "order_id", "status_badge", "reason", "refund_amount")
    search_fields = ("return_number",)
    change_list_template = "admin/ordering/orderreturnmodel/change_list.html"
    change_form_template = "admin/ordering/orderreturnmodel/change_form.html"

    def status_badge(self, obj: orm.OrderReturnModel) -> str:
        tones = {"requested": "warning", "approved": "info", "rejected": "danger", "received": "info", "refunded": "success", "closed": "neutral"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def get_urls(self):
        from django.urls import path

        return [path("<uuid:return_id>/refund/", self.admin_site.admin_view(self.refund_view), name="ordering_orderreturnmodel_refund")] + super().get_urls()

    def _create(self, request, order_id, desk):
        from django.db import transaction

        with transaction.atomic():  # request + approve in one commit: the customer is told once (approved), not twice
            return self._create_atomic(request, order_id, desk)

    def _create_atomic(self, request, order_id, desk):
        from apps.ordering.application.services.returns import ApproveReturn, RequestReturn
        from apps.ordering.infrastructure.repositories import DjangoOrderReturnRepository

        ctx = _admin_ctx(request)
        repo = DjangoOrderReturnRepository()
        created = RequestReturn(repo, DjangoOrderRepository(), ctx).execute(
            order_id, reason=request.POST.get("reason") or "other", lines=desk.parse_lines(request.POST),
            enforce_window=not request.POST.get("override_window"),
        )
        obj = orm.OrderReturnModel.objects.get(pk=created.id)
        self._save_note(obj, request.POST.get("note"))
        if request.POST.get("approve_now"):
            ApproveReturn(repo, ctx).execute(created.id)
        return created.id

    def _act(self, request, obj, action, desk):
        from apps.ordering.application.services.returns import ApproveReturn, ReceiveReturn, RejectReturn
        from apps.ordering.application.services.returns import RefundReturn as Refund
        from apps.ordering.infrastructure.repositories import DjangoOrderReturnRepository

        ctx = _admin_ctx(request)
        repo = DjangoOrderReturnRepository()
        if action == "approve":
            ApproveReturn(repo, ctx).execute(obj.id)
            return _("Return approved -- waiting for the goods.")
        if action == "reject":
            reason = (request.POST.get("note") or "").strip()
            if not reason:
                raise ValueError(_("Write why the return is rejected -- the customer will ask."))
            RejectReturn(repo, ctx).execute(obj.id, reason=reason)
            self._save_note(obj, f"{_('Rejected')}: {reason}")
            return _("Return rejected.")
        if action == "receive":
            restock = bool(request.POST.get("restock"))
            ReceiveReturn(repo, ctx, DjangoOrderRepository()).execute(obj.id, restock=restock)
            self._save_note(obj, request.POST.get("note"))
            return _("Goods received and put back on the shelf.") if restock else _("Goods received (not put back on the shelf).")
        if action == "refund":
            amount = desk.parse_amount(request.POST.get("amount"))
            if amount is None:
                raise ValueError(_("Enter the refund amount."))
            Refund(repo, ctx).execute(obj.id, amount, obj.refund_currency or "UZS")
            self._save_note(obj, request.POST.get("note"))
            return _("Refund of %(amount)s so'm recorded.") % {"amount": desk.money(amount)}
        if action == "note":
            self._save_note(obj, request.POST.get("note"))
            return _("Note saved.")
        raise ValueError(_("Unknown action."))

    def refund_view(self, request, return_id):
        """Stand-alone refund form (kept for links from older pages); the workspace has the same form inline."""
        from django.contrib import messages
        from django.contrib.admin.utils import unquote
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseRedirect
        from django.shortcuts import get_object_or_404
        from django.template.response import TemplateResponse
        from django.urls import reverse

        if not self.has_change_permission(request):
            raise PermissionDenied
        order_return = get_object_or_404(orm.OrderReturnModel, id=unquote(str(return_id)))
        back = reverse("admin:ordering_orderreturnmodel_change", args=[order_return.id])
        desk = self._desk()
        if request.method == "POST":
            amount = desk.parse_amount(request.POST.get("amount"))
            try:
                if amount is None:
                    raise ValueError(_("Enter the refund amount."))
                RefundReturn(build_order_return_repository(), _admin_ctx(request)).execute(order_return.id, amount, request.POST.get("currency") or order_return.refund_currency or "UZS")
                messages.success(request, _("Refund of %(amount)s so'm recorded.") % {"amount": desk.money(amount)})
            except Exception as exc:  # noqa: BLE001 -- e.g. refund above the paid amount: a message, never a 500
                messages.error(request, desk.error_text(exc))
            return HttpResponseRedirect(back)
        context = {**self.admin_site.each_context(request), "title": _("Refund %(number)s") % {"number": order_return.return_number}, "object": order_return, "desk": desk.workflow_snapshot(order_return, "return"), "opts": self.model._meta}
        return TemplateResponse(request, "admin/ordering/orderreturnmodel/refund_confirmation.html", context)


class CancellationLineItemInline(admin.TabularInline):
    model = orm.CancellationLineItemModel
    extra = 0


@admin.register(orm.OrderCancellationModel)
class OrderCancellationAdmin(ExcelExportMixin, _WorkflowAdmin):
    excel_title = "Buyurtmalarni bekor qilishlar"
    excel_columns = [
        Col("Buyurtma", lambda r: r.x_order, 18), Col("Holat", "status", 12), Col("Sabab", "reason", 18), Col("So'ralgan", "requested_at", 17),
        Col("Tasdiqlangan", "approved_at", 17), Col("Yakunlangan", "completed_at", 17), Col("Qaytarilgan summa", "refund_amount", 15, money=True),
        Col("Izoh", "note", 28), Col("Rad etish sababi", "rejection_reason", 24),
    ]

    def excel_prepare(self, objs):
        numbers = dict(orm.OrderModel.objects.filter(id__in=[r.order_id for r in objs]).values_list("id", "order_number"))
        for r in objs:
            r.x_order = numbers.get(r.order_id, "")

    kind = "cancel"
    list_display = ("id", "order_id", "status_badge", "reason", "refund_amount")
    search_fields = ("order_id",)
    change_list_template = "admin/ordering/ordercancellationmodel/change_list.html"
    change_form_template = "admin/ordering/ordercancellationmodel/change_form.html"

    def status_badge(self, obj: orm.OrderCancellationModel) -> str:
        tones = {"requested": "warning", "approved": "info", "rejected": "danger", "completed": "success"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def _create(self, request, order_id, desk):
        from django.db import transaction

        with transaction.atomic():  # request + approve + complete in one commit: one notification with the outcome
            return self._create_atomic(request, order_id, desk)

    def _create_atomic(self, request, order_id, desk):
        from apps.ordering.application.services.cancellations import (
            ApproveCancellation,
            CompleteCancellation,
            RequestCancellation,
        )
        from apps.ordering.infrastructure.repositories import DjangoOrderCancellationRepository

        ctx = _admin_ctx(request)
        repo = DjangoOrderCancellationRepository()
        lines = None if request.POST.get("scope") == "all" else desk.parse_lines(request.POST)
        created = RequestCancellation(repo, DjangoOrderRepository(), ctx).execute(order_id, reason=request.POST.get("reason") or "admin_action", lines=lines)
        obj = orm.OrderCancellationModel.objects.get(pk=created.id)
        self._save_note(obj, request.POST.get("note"))
        if request.POST.get("complete_now"):
            ApproveCancellation(repo, ctx).execute(created.id)
            CompleteCancellation(repo, ctx, DjangoOrderRepository()).execute(created.id, desk.parse_amount(request.POST.get("refund")))
        return created.id

    def _act(self, request, obj, action, desk):
        from apps.ordering.application.services.cancellations import (
            ApproveCancellation,
            CompleteCancellation,
            RejectCancellation,
        )
        from apps.ordering.infrastructure.repositories import DjangoOrderCancellationRepository

        ctx = _admin_ctx(request)
        repo = DjangoOrderCancellationRepository()
        if action == "approve":
            ApproveCancellation(repo, ctx).execute(obj.id)
            return _("Cancellation approved.")
        if action in ("complete", "approve_complete"):
            from django.db import transaction

            with transaction.atomic():
                if action == "approve_complete":
                    ApproveCancellation(repo, ctx).execute(obj.id)
                CompleteCancellation(repo, ctx, DjangoOrderRepository()).execute(obj.id, desk.parse_amount(request.POST.get("refund")))
            self._save_note(obj, request.POST.get("note"))
            return _("Cancellation completed -- the order and stock are updated.")
        if action == "reject":
            reason = (request.POST.get("note") or "").strip()
            if not reason:
                raise ValueError(_("Write why the cancellation is rejected."))
            RejectCancellation(repo, ctx).execute(obj.id, reason=reason)
            self._save_note(obj, f"{_('Rejected')}: {reason}")
            return _("Cancellation rejected.")
        if action == "note":
            self._save_note(obj, request.POST.get("note"))
            return _("Note saved.")
        raise ValueError(_("Unknown action."))


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (event-log) data an admin never creates or edits by hand.
# @admin.register(orm.OrderingOutboxEvent)
class OrderingOutboxEventAdmin(admin.ModelAdmin):
    """Read-only -- append-only/Outbox tables are never editable in admin, per MIC §9."""

    list_display = ("event_type", "event_version", "created_at", "published_at", "publish_attempts")
    list_filter = ("event_type",)
    readonly_fields = [f.name for f in orm.OrderingOutboxEvent._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


def _order_payments(order) -> list[dict]:
    """Online payment attempts for the order card (Dashboard → To'lovlar has the full conversation)."""
    from django.urls import reverse

    from apps.payment.infrastructure.admin import STATUS_STYLE, _logo, _money
    from apps.payment.infrastructure.models import PaymentModel
    from apps.payment.infrastructure.providers.registry import provider_label

    rows = []
    for p in PaymentModel.objects.filter(order_id=order.id).exclude(provider="cash").order_by("-created_at")[:5]:
        label, color, icon = STATUS_STYLE.get(p.status, (p.status, "#64748b", "fa-circle"))
        key = p.method or p.provider
        rows.append({"url": reverse("admin:payment_paymentmodel_change", args=[p.pk]), "logo": _logo(key), "name": provider_label(key), "amount": _money(p.amount),
                     "label": label, "color": color, "icon": icon, "test": p.is_test, "when": p.paid_at or p.created_at})
    return rows


@admin.register(orm.Courier)
class CourierAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    """Couriers picked on the delivery desk (Yetkazib berish markazi)."""

    list_display = ("name", "phone", "vehicle", "is_active", "created_at")
    search_fields = ("name", "phone", "vehicle")
    ordering = ("-is_active", "name")
    actions = None
    fieldsets = ((None, {"fields": ("name", "phone", "vehicle", "telegram_username", "is_active")}),)

    nz_icon, nz_tone, nz_title = "fa-motorcycle", "#0ea5e9", "Kuryerlar"
    nz_subtitle = "Buyurtmalarni mijozga olib boradigan xodimlar. Yetkazib berish markazida buyurtmaga biriktiriladi."
    nz_columns = (("Kuryer", ""), ("Telefon", ""), ("Transport", ""), ("Holat", ""), ("Yo'lda", "r"))
    nz_grid = "minmax(200px,2fr) 160px minmax(140px,1fr) 110px 90px"
    nz_search = "Ism, telefon yoki transport…"
    nz_empty = ("Kuryer yo'q", "«Qo'shish» bilan birinchi kuryerni kiriting.")

    def nz_prepare(self, request, objs):
        from django.db.models import Count

        loads = dict(orm.DeliveryAssignment.objects.filter(courier__in=objs, order__status="shipped").values_list("courier_id").annotate(n=Count("id")))
        for c in objs:
            c.nz_load = loads.get(c.id, 0)

    def nz_row(self, c):
        from apps.platform.infrastructure.premium_admin import chip, muted

        name = format_html('<b>{}</b>{}', c.name, format_html('<br><small>@{}</small>', c.telegram_username) if c.telegram_username else "")
        phone = format_html('<a href="tel:{}">{}</a>', c.phone, c.phone) if c.phone else muted()
        state = chip("Faol", "#16a34a", "fa-circle-check") if c.is_active else chip("Nofaol", "#64748b", "fa-circle-pause")
        return [name, phone, c.vehicle or muted(), state, format_html("<b>{}</b>", getattr(c, "nz_load", 0))]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Ism va telefon — yetkazib berish markazida ko'rinadi"}
        return {"title": obj.name, "subtitle": " · ".join(p for p in (obj.phone, obj.vehicle) if p)}
