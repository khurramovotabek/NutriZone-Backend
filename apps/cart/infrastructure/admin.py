"""
Dashboard → Savat: what customers hold in their carts, abandoned carts to win back, and the cart history.

Pages (premium, templates/admin/cart/):
  * Savatlar         tabs (with products / abandoned / ordered / empty / all, plus "products in carts"), KPIs,
                     conversion = carts that became an order (OrderModel.cart_id) -- the storefront clears the cart
                     after checkout instead of converting it, so the order link is the truth.
  * Savat kartochkasi customer, products at today's price (and the price they were added at), the orders placed
                     from it, its timeline; "remind the customer" (inbox + Telegram) for an abandoned cart; archive / restore.
  * Savat tarixi     every cart event in plain words (added / removed / quantity / cleared / coupon / sign-in).
Price snapshots, cart reservations, cart snapshots and the raw cart-items table are internal bookkeeping of the
cart engine and are not on the Dashboard (the product view of cart items lives on the carts page).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from apps.cart.application.services._shared import CartServiceContext
from apps.cart.application.services.lifecycle import ArchiveCart, RestoreCart
from apps.cart.infrastructure import models as orm
from apps.cart.infrastructure.repositories import DjangoCartRepository
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from core.outbox import stage_event

ABANDONED_AFTER_HOURS = 24
REMIND_AGAIN_AFTER_HOURS = 24
CART_STATUS = {
    "active": (_("Faol"), "#10b981"), "saved": (_("Saqlangan"), "#6366f1"), "locked": (_("Qulflangan"), "#f59e0b"),
    "expired": (_("Muddati o'tgan"), "#e11d48"), "archived": (_("Arxiv"), "#64748b"), "converted": (_("Buyurtmaga aylangan"), "#0ea5e9"),
}
ACTION_STYLE = {
    "item_added": ("#10b981", "fa-cart-plus"), "item_quantity_increased": ("#10b981", "fa-plus"), "item_quantity_updated": ("#0ea5e9", "fa-pen"),
    "item_removed": ("#e11d48", "fa-trash"), "cart_cleared": ("#64748b", "fa-broom"), "coupon_applied": ("#f59e0b", "fa-ticket"),
    "coupon_removed": ("#94a3b8", "fa-ticket"), "customer_assigned": ("#6366f1", "fa-user-check"), "cart_archived": ("#64748b", "fa-box-archive"),
    "cart_restored": ("#10b981", "fa-rotate-left"), "reminder_sent": ("#2563eb", "fa-bell"),
}
SOURCE = {"web": (_("Sayt"), "fa-globe"), "mobile": (_("Mobil"), "fa-mobile-screen"), "pos": ("POS", "fa-cash-register"), "api": (_("Bot / API"), "fa-plug")}


def _stage_cart_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.CartOutboxEvent, event_type, payload)


def _admin_ctx(request) -> CartServiceContext:
    return CartServiceContext(stage_events=_stage_cart_events, actor_id=getattr(request.user, "id", None))


def _variant_cards(variant_ids) -> dict:
    """variant_id -> {"name", "sku", "thumb", "price"} in one pass (names in Uzbek first)."""
    from apps.products.infrastructure.models import ProductMedia, ProductTranslation, ProductVariant
    from apps.products.infrastructure.selectors import bulk_variant_prices

    variants = list(ProductVariant.all_objects.filter(id__in=set(variant_ids)).values("id", "product_id", "sku"))
    pids = {v["product_id"] for v in variants}
    names, thumbs = {}, {}
    for t in ProductTranslation.objects.filter(product_id__in=pids).values("product_id", "locale_code", "name"):
        if t["locale_code"] == "uz" or t["product_id"] not in names:
            names[t["product_id"]] = t["name"]
    for m in ProductMedia.objects.filter(product_id__in=pids).order_by("sort_order").values("product_id", "storage_path", "thumbnail_paths"):
        thumbs.setdefault(m["product_id"], (m["thumbnail_paths"] or {}).get("small") or m["storage_path"])
    prices = bulk_variant_prices([v["id"] for v in variants])
    return {
        v["id"]: {"name": names.get(v["product_id"], v["sku"]), "sku": v["sku"], "thumb": f"/media/{thumbs[v['product_id']]}" if v["product_id"] in thumbs else None,
                  "price": Decimal(prices[v["id"]]["amount"]) if v["id"] in prices else None, "product_id": v["product_id"]}
        for v in variants
    }


def _money(n) -> str:
    return f"{int(round(n or 0)):,}".replace(",", " ")


def _ago(dt) -> str:
    if not dt:
        return "—"
    secs = (timezone.now() - dt).total_seconds()
    if secs < 60:
        return _t("just now")
    if secs < 3600:
        return _t("%d min ago") % (secs // 60)
    if secs < 86400:
        return _t("%d h ago") % (secs // 3600)
    days = int(secs // 86400)
    return ngettext("%d day ago", "%d days ago", days) % days


def _local(dt, fmt="%d.%m.%Y %H:%M") -> str:
    return timezone.localtime(dt).strftime(fmt) if dt else ""


def _has_items():
    return Exists(orm.CartItemModel.objects.filter(cart=OuterRef("pk"), status="active"))


def _ordered_cart_ids(cart_ids=None) -> dict:
    """cart id -> [orders placed from it] (number, status, total, when)."""
    from apps.ordering.infrastructure.models import OrderModel

    qs = OrderModel.objects.exclude(cart_id=None)
    if cart_ids is not None:
        qs = qs.filter(cart_id__in=list(cart_ids))
    out: dict = {}
    for o in qs.order_by("-created_at").values("id", "cart_id", "order_number", "status", "invoice_total_amount", "created_at"):
        out.setdefault(o["cart_id"], []).append(o)
    return out


def _purge_count() -> int:
    from apps.cart.infrastructure.tasks import stale_guest_carts

    return stale_guest_carts().count()


def _users(ids) -> dict:
    from apps.identity.infrastructure.models import User

    return {u.id: u for u in User.objects.filter(id__in={i for i in ids if i}).only("id", "full_name", "phone_number", "telegram_user_id")}


def _is_abandoned(cart, active_items) -> bool:
    return cart.status == "active" and bool(active_items) and cart.updated_at < timezone.now() - timedelta(hours=ABANDONED_AFTER_HOURS)


def describe(entry, cards: dict, items_by_id: dict) -> str:
    """One cart event in plain words."""
    d = entry.details or {}

    def product(vid=None, item_id=None):
        if item_id and item_id in items_by_id:
            vid = items_by_id[item_id]
        card = cards.get(_uuid(vid)) if vid else None
        return card["name"] if card else _t("a product")

    a = entry.action
    if a == "item_added":
        return _t("Added %(product)s × %(n)s") % {"product": product(d.get("product_variant_id")), "n": d.get("quantity", 1)}
    if a == "item_quantity_increased":
        return _t("Added %(n)s more of %(product)s") % {"product": product(d.get("product_variant_id")), "n": d.get("added", 1)}
    if a == "item_quantity_updated":
        return _t("%(product)s: quantity %(old)s → %(new)s") % {"product": product(item_id=d.get("item_id")), "old": d.get("old_quantity", "?"), "new": d.get("new_quantity", "?")}
    if a == "item_removed":
        return _t("Removed %(product)s") % {"product": product(item_id=d.get("item_id"))}
    if a == "cart_cleared":
        return _t("Cart emptied (%(n)s product(s))") % {"n": d.get("items_removed", 0)}
    if a == "coupon_applied":
        return _t("Coupon applied")
    if a == "customer_assigned":
        return _t("The customer signed in -- the cart is now theirs")
    if a == "reminder_sent":
        return _t("Reminder sent to the customer")
    return a.replace("_", " ").capitalize()


def _uuid(v):
    import uuid

    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError):
        return None


def _entry_cards(entries) -> tuple[dict, dict]:
    """Product cards for every variant mentioned by these events, and item id -> variant id."""
    vids, item_ids = set(), set()
    for e in entries:
        d = e.details or {}
        if d.get("product_variant_id"):
            vids.add(_uuid(d["product_variant_id"]))
        if d.get("item_id"):
            item_ids.add(_uuid(d["item_id"]))
    items_by_id = {str(i["id"]): i["product_variant_id"] for i in orm.CartItemModel.all_objects.filter(id__in=item_ids - {None}).values("id", "product_variant_id")} if hasattr(orm.CartItemModel, "all_objects") else \
        {str(i["id"]): i["product_variant_id"] for i in orm.CartItemModel.objects.filter(id__in=item_ids - {None}).values("id", "product_variant_id")}
    vids |= set(items_by_id.values())
    return _variant_cards(vids - {None}), items_by_id


# ====================================================================== carts


class CartViewFilter(admin.SimpleListFilter):
    title = _("Cart")
    parameter_name = "view"

    def lookups(self, request, model_admin):
        return [("items", _("With products")), ("abandoned", _("Abandoned")), ("ordered", _("Ordered")), ("empty", _("Empty")), ("all", _("All")), ("products", _("Products in carts"))]

    def queryset(self, request, qs):
        v = self.value() or "items"
        if v in ("items", "products"):
            return qs.filter(_has_items())
        if v == "abandoned":
            return qs.filter(_has_items(), status="active", updated_at__lt=timezone.now() - timedelta(hours=ABANDONED_AFTER_HOURS))
        if v == "ordered":
            return qs.filter(id__in=list(_ordered_cart_ids()))
        if v == "empty":
            return qs.exclude(_has_items())
        return qs


@admin.register(orm.CartModel)
class CartAdmin(ExcelExportMixin, admin.ModelAdmin):
    excel_title = "Savatlar"
    excel_columns = [
        Col("Savat", "code", 14), Col("Yangilangan", "updated_at", 17), Col("Holat", lambda c: c.x_state, 14),
        Col("Mijoz", lambda c: c.x_user.full_name if c.x_user else "Mehmon", 24), Col("Telefon", lambda c: c.x_user.phone_number if c.x_user else "", 16),
        Col("Telegram", lambda c: bool(c.x_user and c.x_user.telegram_user_id), 9),
        Col("Mahsulotlar", lambda c: c.x_names, 50), Col("Dona", lambda c: c.x_units, 8, number=True), Col("Qiymati (so'm)", lambda c: c.x_value, 15, money=True),
        Col("Buyurtma", lambda c: ", ".join(o["order_number"] for o in c.x_orders), 18),
    ]

    def excel_prepare(self, objs):
        items = list(orm.CartItemModel.objects.filter(cart__in=objs, status="active").values("cart_id", "product_variant_id", "quantity"))
        cards = _variant_cards([i["product_variant_id"] for i in items])
        users, ordered = _users(c.customer_id for c in objs), _ordered_cart_ids([c.id for c in objs])
        by_cart: dict = {}
        for i in items:
            by_cart.setdefault(i["cart_id"], []).append(i)
        for c in objs:
            mine = by_cart.get(c.id, [])
            c.x_user, c.x_orders = users.get(c.customer_id), ordered.get(c.id, [])
            c.x_units = sum(i["quantity"] for i in mine)
            c.x_value = sum(((cards.get(i["product_variant_id"], {}).get("price") or Decimal(0)) * i["quantity"] for i in mine), Decimal(0))
            c.x_names = "; ".join(f"{cards.get(i['product_variant_id'], {}).get('name', '—')} × {i['quantity']}" for i in mine)
            c.x_state = "Buyurtma qilingan" if c.x_orders else ("Tashlab ketilgan" if _is_abandoned(c, mine) else ("Bo'sh" if not mine else "Faol"))

    list_display = ("code", "status", "updated_at")
    list_filter = (CartViewFilter,)
    search_fields = ("code",)
    change_list_template = "admin/cart/carts.html"
    ordering = ("-updated_at",)
    list_per_page = 30
    actions = None

    def has_add_permission(self, request):
        return False  # carts are created by the storefront

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("items")

    def get_search_results(self, request, queryset, search_term):
        """Cart code, or the customer's name / phone."""
        qs, dup = super().get_search_results(request, queryset, search_term)
        term = (search_term or "").strip()
        if term:
            from apps.identity.infrastructure.models import User

            ids = list(User.objects.filter(Q(full_name__icontains=term) | Q(phone_number__icontains=term.replace(" ", ""))).values_list("id", flat=True)[:200])
            if ids:
                qs = qs | queryset.filter(customer_id__in=ids)
        return qs, dup

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        rows = list(cl.result_list)
        cards = _variant_cards([i.product_variant_id for c in rows for i in c.items.all() if i.status == "active"])
        users = _users(c.customer_id for c in rows)
        orders = _ordered_cart_ids([c.id for c in rows])
        for c in rows:
            items = [i for i in c.items.all() if i.status == "active"]
            value = sum(((cards.get(i.product_variant_id, {}).get("price") or Decimal(0)) * i.quantity for i in items), Decimal(0))
            label, tone = CART_STATUS.get(c.status, (c.status, "#64748b"))
            if c.id in orders:
                label, tone = _t("Ordered"), "#0ea5e9"
            elif _is_abandoned(c, items):
                label, tone = _t("Abandoned"), "#e11d48"
            elif not items:
                label, tone = _t("Empty"), "#94a3b8"
            u = users.get(c.customer_id)
            src_label, src_icon = SOURCE.get(c.source, (c.source, "fa-globe"))
            c.nz = {
                "items": [{"thumb": cards.get(i.product_variant_id, {}).get("thumb"), "name": cards.get(i.product_variant_id, {}).get("name", _t("Deleted product"))} for i in items[:4]],
                "more": max(0, len(items) - 4), "units": sum(i.quantity for i in items), "first": cards.get(items[0].product_variant_id, {}).get("name", "") if items else "",
                "value": _money(value) if value else "", "label": label, "tone": tone, "ago": _ago(c.updated_at), "when": _local(c.updated_at),
                "user": u, "initials": "".join(p[0] for p in (u.full_name or "?").split()[:2]).upper() if u else "", "orders": orders.get(c.id, []),
                "source": src_label, "source_icon": src_icon,
            }
        return cl

    def changelist_view(self, request, extra_context=None):
        now = timezone.now()
        live = orm.CartModel.objects.filter(_has_items(), status="active")
        items = list(orm.CartItemModel.objects.filter(cart__in=live, status="active").values("cart_id", "product_variant_id", "quantity", "cart__updated_at", "cart__customer_id"))
        cards = _variant_cards([i["product_variant_id"] for i in items])
        ordered = _ordered_cart_ids()
        carts = {i["cart_id"]: i for i in items}
        stale = now - timedelta(hours=ABANDONED_AFTER_HOURS)
        abandoned_ids = {cid for cid, c in carts.items() if c["cart__updated_at"] < stale and cid not in ordered}

        def worth(rows):
            return sum(((cards.get(i["product_variant_id"], {}).get("price") or Decimal(0)) * i["quantity"] for i in rows), Decimal(0))

        value = worth(items)
        abandoned_value = worth([i for i in items if i["cart_id"] in abandoned_ids])
        reachable = sum(1 for cid in abandoned_ids if carts[cid]["cart__customer_id"])
        known = sum(1 for c in carts.values() if c["cart__customer_id"])
        # conversion: carts that got products in the last 30 days and those of them that became an order
        month_ids = set(orm.CartAuditEntryModel.objects.filter(action="item_added", occurred_at__gte=now - timedelta(days=30)).values_list("cart_id", flat=True))
        converted = sum(1 for cid in month_ids if cid in ordered)
        view = request.GET.get("view") or "items"
        counts = {
            "items": len(carts), "abandoned": len(abandoned_ids), "ordered": len(ordered),
            "empty": orm.CartModel.objects.exclude(_has_items()).count(), "all": orm.CartModel.objects.count(),
        }
        tabs = [(k, label, icon, color, counts.get(k)) for k, label, icon, color in (
            ("items", _t("With products"), "fa-cart-shopping", "#2563eb"), ("abandoned", _t("Abandoned"), "fa-person-walking-arrow-right", "#e11d48"),
            ("ordered", _t("Ordered"), "fa-bag-shopping", "#0ea5e9"), ("products", _t("Products in carts"), "fa-boxes-stacked", "#8b5cf6"),
            ("empty", _t("Empty"), "fa-circle", "#94a3b8"), ("all", _t("All"), "fa-layer-group", "#64748b"))]
        extra = {
            "title": _t("Savatlar"), "view": view, "tabs": tabs, "q": request.GET.get("q", ""),
            "purge_soon": _purge_count() if view == "empty" else 0,
            "kpi": {
                "carts": len(carts), "value": _money(value), "abandoned": len(abandoned_ids), "abandoned_value": _money(abandoned_value), "reachable": reachable,
                "avg": _money(value / len(carts)) if carts else "0", "avg_units": round(sum(i["quantity"] for i in items) / len(carts), 1) if carts else 0,
                "known": round(known * 100 / len(carts)) if carts else 0, "conversion": round(converted * 100 / len(month_ids)) if month_ids else 0,
                "converted": converted, "month": len(month_ids),
            },
        }
        if view == "products":
            demand: dict = {}
            for i in items:
                d = demand.setdefault(i["product_variant_id"], {"units": 0, "carts": set(), "customers": set(), "abandoned": 0})
                d["units"] += i["quantity"]
                d["carts"].add(i["cart_id"])
                if i["cart__customer_id"]:
                    d["customers"].add(i["cart__customer_id"])
                if i["cart_id"] in abandoned_ids:
                    d["abandoned"] += i["quantity"]
            lead = max((d["units"] for d in demand.values()), default=1)
            extra["products"] = sorted(({
                "card": cards.get(v) or {"name": _t("Deleted product"), "sku": "", "thumb": None, "price": None}, "units": d["units"], "carts": len(d["carts"]),
                "customers": len(d["customers"]), "abandoned": d["abandoned"], "pct": max(4, round(d["units"] * 100 / lead)),
                "value": _money((cards.get(v, {}).get("price") or 0) * d["units"]),
            } for v, d in demand.items()), key=lambda r: -r["units"])
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    # ------------------------------------------------------------------ detail + actions
    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("<uuid:pk>/remind/", v(self.remind_view), name="cart_cartmodel_remind"),
            path("<uuid:pk>/archive/", v(self.archive_view), name="cart_cartmodel_archive"),
            path("<uuid:pk>/restore/", v(self.restore_view), name="cart_cartmodel_restore"),
            *super().get_urls(),
        ]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        c = get_object_or_404(orm.CartModel.objects.prefetch_related("items"), pk=object_id)
        items = [i for i in c.items.all() if i.status == "active"]
        removed = [i for i in c.items.all() if i.status != "active"]
        refs = {r.item_id: r for r in orm.PriceSnapshotReferenceModel.objects.filter(item__cart=c)}
        entries = list(orm.CartAuditEntryModel.objects.filter(cart=c).order_by("-occurred_at")[:60])
        cards, items_by_id = _entry_cards(entries)
        cards.update(_variant_cards([i.product_variant_id for i in c.items.all()]))
        lines, total = [], Decimal(0)
        for i in items:
            card = cards.get(i.product_variant_id) or {"name": _t("Deleted product"), "sku": "", "thumb": None, "price": None}
            price = card["price"]
            added = refs[i.id].unit_amount if i.id in refs else None
            line = (price or 0) * i.quantity
            total += line
            lines.append({"i": i, "card": card, "price": _money(price) if price is not None else "", "line": _money(line) if price is not None else "",
                          "added_price": _money(added) if added is not None and price is not None and added != price else "",
                          "cheaper": added is not None and price is not None and price < added, "added": _ago(i.added_at)})
        u = _users([c.customer_id]).get(c.customer_id)
        orders = _ordered_cart_ids([c.id]).get(c.id, [])
        from apps.ordering.infrastructure.models import OrderModel

        customer_orders = OrderModel.objects.filter(customer_id=c.customer_id).count() if c.customer_id else 0
        coupons = []
        coupon_ids = [u for u in (_uuid(x) for x in (c.coupon_ids or [])) if u]
        if coupon_ids:
            from apps.pricing.infrastructure.models import CouponModel

            manager = getattr(CouponModel, "all_objects", CouponModel.objects)
            coupons = list(manager.filter(id__in=coupon_ids).values_list("code", flat=True))
        last_reminder = next((e for e in entries if e.action == "reminder_sent"), None)
        abandoned = _is_abandoned(c, items) and not orders
        label, tone = CART_STATUS.get(c.status, (c.status, "#64748b"))
        if orders:
            label, tone = _t("Ordered"), "#0ea5e9"
        elif abandoned:
            label, tone = _t("Abandoned"), "#e11d48"
        src_label, src_icon = SOURCE.get(c.source, (c.source, "fa-globe"))
        timeline = [{"e": e, "text": describe(e, cards, items_by_id), "color": ACTION_STYLE.get(e.action, ("#64748b", "fa-circle"))[0],
                     "icon": ACTION_STYLE.get(e.action, ("#64748b", "fa-circle"))[1], "when": _local(e.occurred_at), "ago": _ago(e.occurred_at)} for e in entries]
        can_remind = bool(u and items and not orders and request.user.has_perm("cart.change_cartmodel")
                          and not (last_reminder and last_reminder.occurred_at > timezone.now() - timedelta(hours=REMIND_AGAIN_AFTER_HOURS)))
        return render(request, "admin/cart/cart_detail.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": c.code, "c": c, "lines": lines, "removed": len(removed),
            "total": _money(total), "units": sum(i.quantity for i in items), "u": u, "orders": [{**o, "total": _money(o["invoice_total_amount"]), "when": _local(o["created_at"])} for o in orders],
            "customer_orders": customer_orders, "coupons": coupons, "timeline": timeline, "label": label, "tone": tone, "abandoned": abandoned,
            "last_reminder": _local(last_reminder.occurred_at) if last_reminder else "", "can_remind": can_remind,
            "can_change": request.user.has_perm("cart.change_cartmodel"), "created": _local(c.created_at), "updated": _local(c.updated_at), "ago": _ago(c.updated_at),
            "source": src_label, "source_icon": src_icon,
        })

    def remind_view(self, request, pk):
        """Abandoned cart: a reminder in the customer's inbox (and Telegram), at most once a day."""
        if request.method != "POST" or not request.user.has_perm("cart.change_cartmodel"):
            raise PermissionDenied
        c = get_object_or_404(orm.CartModel, pk=pk)
        items = list(c.items.filter(status="active"))
        back = HttpResponseRedirect(reverse("admin:cart_cartmodel_change", args=[c.pk]))
        if not c.customer_id or not items:
            messages.error(request, _t("Only a signed-in customer's cart with products can be reminded."))
            return back
        recent = orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent", occurred_at__gt=timezone.now() - timedelta(hours=REMIND_AGAIN_AFTER_HOURS)).exists()
        if recent:
            messages.error(request, _t("A reminder was already sent in the last 24 hours."))
            return back
        cards = _variant_cards([i.product_variant_id for i in items])
        names = [cards[i.product_variant_id]["name"] for i in items if i.product_variant_id in cards]
        products = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
        from apps.notifications.infrastructure.notify import notify

        now = timezone.now()
        notify(c.customer_id, "cart_reminder", {"products": products}, link="/cart", dedupe_key=f"cart_reminder:{c.id}:{now:%Y%m%d}")
        orm.CartAuditEntryModel.objects.create(cart=c, action="reminder_sent", actor_id=getattr(request.user, "id", None), occurred_at=now,
                                               details={"by": request.user.get_full_name() or request.user.get_username()})
        messages.success(request, _t("Reminder sent -- the customer sees it in their notifications and on Telegram."))
        return back

    def _lifecycle(self, request, pk, service_cls, ok_text):
        if request.method != "POST" or not request.user.has_perm("cart.change_cartmodel"):
            raise PermissionDenied
        try:
            service_cls(DjangoCartRepository(), _admin_ctx(request)).execute(pk)
        except Exception as exc:  # noqa: BLE001 - domain refusal (e.g. a converted cart can't be archived)
            messages.error(request, str(exc))
        else:
            messages.success(request, ok_text)
        return HttpResponseRedirect(reverse("admin:cart_cartmodel_change", args=[pk]))

    def archive_view(self, request, pk):
        return self._lifecycle(request, pk, ArchiveCart, _t("Cart archived."))

    def restore_view(self, request, pk):
        return self._lifecycle(request, pk, RestoreCart, _t("Cart restored."))


# ====================================================================== history


@admin.register(orm.CartAuditEntryModel)
class CartAuditEntryAdmin(admin.ModelAdmin):
    """Savat tarixi: every cart event in plain words, read-only."""

    list_display = ("cart", "action", "occurred_at")
    list_filter = ("action",)
    search_fields = ("cart__code",)
    list_select_related = ("cart",)
    ordering = ("-occurred_at",)
    list_per_page = 50
    change_list_template = "admin/cart/history.html"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        e = get_object_or_404(orm.CartAuditEntryModel, pk=object_id)
        return HttpResponseRedirect(reverse("admin:cart_cartmodel_change", args=[e.cart_id]))

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        rows = list(cl.result_list)
        cards, items_by_id = _entry_cards(rows)
        users = _users(e.cart.customer_id for e in rows)
        for e in rows:
            color, icon = ACTION_STYLE.get(e.action, ("#64748b", "fa-circle"))
            d = e.details or {}
            vid = _uuid(d.get("product_variant_id")) or (items_by_id.get(d.get("item_id")) if d.get("item_id") else None)
            card = cards.get(vid) if vid else None
            e.nz = {"text": describe(e, cards, items_by_id), "color": color, "icon": icon, "when": _local(e.occurred_at), "ago": _ago(e.occurred_at),
                    "thumb": card["thumb"] if card else None, "user": users.get(e.cart.customer_id)}
        return cl

    def changelist_view(self, request, extra_context=None):
        today = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        week = timezone.now() - timedelta(days=7)
        counts = dict(orm.CartAuditEntryModel.objects.filter(occurred_at__gte=week).values_list("action").annotate(n=Count("id")))
        current = request.GET.get("action__exact", "")
        labels = {"item_added": _t("Added"), "item_quantity_increased": _t("More of the same"), "item_quantity_updated": _t("Quantity changed"),
                  "item_removed": _t("Removed"), "cart_cleared": _t("Emptied"), "coupon_applied": _t("Coupon"), "customer_assigned": _t("Signed in"),
                  "reminder_sent": _t("Reminders")}
        all_counts = dict(orm.CartAuditEntryModel.objects.values_list("action").annotate(n=Count("id")))
        chips = [{"key": "", "label": _t("All"), "color": "#64748b", "icon": "fa-layer-group", "n": sum(all_counts.values()), "on": not current}]
        for key, label in labels.items():
            if key in all_counts:
                color, icon = ACTION_STYLE[key]
                chips.append({"key": key, "label": label, "color": color, "icon": icon, "n": all_counts[key], "on": current == key})
        added = counts.get("item_added", 0) + counts.get("item_quantity_increased", 0)
        removed = counts.get("item_removed", 0) + counts.get("cart_cleared", 0)
        extra = {
            "title": _t("Savat tarixi"), "chips": chips, "q": request.GET.get("q", ""),
            "kpi": {"today": orm.CartAuditEntryModel.objects.filter(occurred_at__gte=today).count(), "added": added, "removed": removed,
                    "coupons": counts.get("coupon_applied", 0), "signins": counts.get("customer_assigned", 0)},
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})

