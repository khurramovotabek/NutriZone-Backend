"""
Dashboard → Identity (Foydalanuvchilarni boshqarish): customers, their login sessions and devices, roles,
permissions and role assignments.

Every list uses the shared premium layout (admin_ui.PremiumListMixin); add/change pages use the premium form chrome
(hero + section bar + cards, CatalogFormMixin). Every state change goes through the identity Application Services
-- block / activate (AdminUpdateUserStatus), revoke a session (RevokeSession / LogoutAll), assign / remove a role
(AssignRole / RemoveRole), a role's permission set (SetRolePermissions) -- never a raw ORM save. Secrets
(refresh_token_hash, push_token) are never rendered.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.html import format_html, format_html_join

from apps.identity.infrastructure import admin_ui as ui
from apps.identity.infrastructure import models as orm
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.products.infrastructure.catalog_form_ui import CatalogFormMixin, stat
from common.exceptions import DomainException


def _actor(request):
    return request.user.pk


def _store_names(ids) -> dict:
    try:
        from apps.stores.infrastructure.models import Store

        return dict(Store.objects.filter(id__in=[i for i in ids if i]).values_list("id", "name"))
    except Exception:  # noqa: BLE001 - the stores app is optional for this page
        return {}


def _som(v) -> str:
    return f"{int(v or 0):,}".replace(",", " ")


def _order_totals(order_ids) -> dict:
    """{order_id: total} -- the order desk's formula (unit price × qty − discount + tax over active lines)."""
    from django.db.models import DecimalField, ExpressionWrapper, F, Sum

    from apps.ordering.infrastructure.models import OrderLineItemModel

    expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
    return dict(OrderLineItemModel.objects.filter(order_id__in=list(order_ids), status="active").values("order_id").annotate(t=Sum(expr)).values_list("order_id", "t"))


def _btn(url: str, label: str, icon: str, kind: str = "", confirm: str = "") -> str:
    """A submit button that posts to one of this page's action URLs (formaction) instead of saving the form."""
    return format_html('<button type="submit" class="nzi-act {}" formaction="{}" formnovalidate data-nzi-confirm="{}"><i class="fas {}" aria-hidden="true"></i> {}</button>',
                       kind, url, confirm, icon, label)


# ================================================================ users


class UserAdminForm(forms.ModelForm):
    avatar_upload = forms.ImageField(required=False, label="Yangi avatar", help_text="JPEG, PNG yoki WebP. Avtomatik optimallashtiriladi (WebP + kichik nusxalar).")

    class Meta:
        model = orm.User
        fields = "__all__"
        labels = {
            "full_name": "To'liq ism", "phone_number": "Telefon raqami", "username": "Username", "email": "Email", "language": "Til",
            "birthday": "Tug'ilgan sana", "bio": "O'zi haqida", "goal": "Fitness maqsadi", "height_cm": "Bo'yi (sm)", "weight_kg": "Vazni (kg)",
        }
        help_texts = {
            "phone_number": "Kirish shu raqam orqali (SMS kod) amalga oshadi: +998XXXXXXXXX",
            "username": "Ixtiyoriy, takrorlanmas. Profil havolasida ishlatiladi.",
            "language": "Sayt, Telegram va bildirishnomalar shu tilda yuboriladi.",
        }


class UserRoleFilter(admin.SimpleListFilter):
    title = "Rol"
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return [(r.code, r.name) for r in orm.Role.objects.order_by("name")] + [("store_owner", "Do'kon egasi"), ("none", "Rolsiz (mijoz)")]

    def queryset(self, request, queryset):
        if self.value() == "store_owner":
            from apps.stores.infrastructure.models import Store

            return queryset.filter(id__in=Store.objects.values("owner_id"))
        if self.value() == "none":
            return queryset.filter(user_roles__isnull=True)
        return queryset.filter(user_roles__role__code=self.value()).distinct() if self.value() else queryset


class TelegramFilter(admin.SimpleListFilter):
    title = "Telegram"
    parameter_name = "telegram"

    def lookups(self, request, model_admin):
        return [("1", "Ulangan"), ("0", "Ulanmagan")]

    def queryset(self, request, queryset):
        if self.value() in ("0", "1"):
            return queryset.filter(telegram_user_id__isnull=self.value() == "0")
        return queryset


class ActivityFilter(admin.SimpleListFilter):
    title = "Faollik"
    parameter_name = "seen"

    def lookups(self, request, model_admin):
        return [("7", "7 kunda kirgan"), ("30", "30 kunda kirgan"), ("never", "Hech kirmagan")]

    def queryset(self, request, queryset):
        if self.value() == "never":
            return queryset.filter(sessions__isnull=True)
        if self.value() in ("7", "30"):
            since = timezone.now() - timedelta(days=int(self.value()))
            return queryset.filter(sessions__last_activity__gte=since).distinct()
        return queryset


def _titled(base, title):
    """A stock field filter with a human (Uzbek) title instead of the raw field name."""
    return type(f"{base.__name__}_{title}", (base,), {"__init__": lambda self, *a, **k: (base.__init__(self, *a, **k), setattr(self, "title", title))[0]})


def _customer_excel_prepare(objs) -> None:
    """Purchases / spend / last purchase / segment from the RFM snapshot, coins from the wallet."""
    from apps.loyalty.infrastructure.models import Wallet
    from apps.platform.infrastructure import segments

    snap = segments.snapshot()
    seg_of = {cid: code for code, ids in snap["members"].items() for cid in ids}
    coins = dict(Wallet.objects.filter(user__in=objs).values_list("user_id", "balance"))
    for u in objs:
        p = snap["profiles"].get(str(u.id), {})
        u.x = {
            "purchases": p.get("purchases", 0),
            "revenue": p.get("revenue") and __import__("decimal").Decimal(p["revenue"]),
            "last": (p.get("last") or "")[:10],
            "channels": ", ".join(p.get("channels", [])),
            "segment": segments.SEGMENTS.get(seg_of.get(str(u.id)), {}).get("label", ""),
            "coins": coins.get(u.id, 0),
        }
@admin.register(orm.User)
class UserAdmin(ExcelExportMixin, ui.PremiumListMixin, CatalogFormMixin, admin.ModelAdmin):

    excel_title = "Mijozlar"
    excel_columns = [
        Col("Ism", "full_name", 26), Col("Telefon", "phone_number", 16), Col("Email", "email", 22), Col("Holat", "status", 10), Col("Til", "language", 6),
        Col("Telegram", lambda u: f"@{u.telegram_username}" if u.telegram_username else ("ulangan" if u.telegram_user_id else ""), 16),
        Col("Ro'yxatdan o'tgan", "created_at", 17), Col("Segment", lambda u: u.x["segment"], 18), Col("Xaridlar", lambda u: u.x["purchases"], 10, number=True),
        Col("Jami xarid (so'm)", lambda u: u.x["revenue"], 16, money=True), Col("Oxirgi xarid", lambda u: u.x["last"], 12),
        Col("Kanallar", lambda u: u.x["channels"], 14), Col("Coins", lambda u: u.x["coins"], 10, number=True), Col("Maqsad", "goal", 14),
    ]

    def excel_prepare(self, objs):
        _customer_excel_prepare(objs)

    """Foydalanuvchilar: every customer / store owner -- status, roles, loyalty, purchases, Telegram, activity; the card is a 360° profile."""

    form = UserAdminForm
    change_form_template = "admin/premium/form.html"
    list_display = ("user_col", "joined_col")  # ordering targets for ?o= (rows are rendered by nz_row)
    list_filter = (UserRoleFilter, TelegramFilter, ActivityFilter, ("language", _titled(admin.ChoicesFieldListFilter, "Til")),
                   ("created_at", _titled(admin.DateFieldListFilter, "Ro'yxatdan o'tgan")))
    search_fields = ("phone_number", "full_name", "username", "email", "telegram_username")
    list_per_page = 25
    ordering = ("-created_at",)
    actions = ["block_selected_users", "activate_selected_users", "logout_selected_users"]
    readonly_fields = ("id", "status_view", "created_at", "updated_at", "version", "telegram_username", "telegram_user_id", "telegram_linked_at",
                       "roles_panel", "security_panel", "orders_panel")
    fieldsets = (
        ("Asosiy ma'lumotlar", {"fields": ("full_name", "phone_number", "username", "email", "language")}),
        ("Profil", {"fields": ("avatar_upload", "birthday", "bio")}),
        ("Fitness maqsadi", {"classes": ("nzp-fold",), "fields": ("goal", "height_cm", "weight_kg")}),
        ("Rollar", {"classes": ("nzi-panel",), "fields": ("roles_panel",)}),
        ("Xavfsizlik: sessiyalar va qurilmalar", {"classes": ("nzi-panel",), "fields": ("security_panel",)}),
        ("Xaridlar", {"classes": ("nzi-panel",), "fields": ("orders_panel",)}),
        ("Telegram", {"classes": ("nzp-fold",), "fields": ("telegram_username", "telegram_user_id", "telegram_linked_at")}),
        ("Tizim", {"classes": ("nzp-fold",), "fields": ("id", "status_view", "created_at", "updated_at", "version")}),
    )
    PANELS = ("roles_panel", "security_panel", "orders_panel")

    nz_icon, nz_tone, nz_title = "fa-users", "#2563eb", "Foydalanuvchilar"
    nz_subtitle = "Sayt, Telegram va do'kon mijozlari: holat, rollar, loyalty, xaridlar va faollik bir joyda."
    nz_columns = (("Foydalanuvchi", ""), ("Holat", ""), ("Rol", ""), ("Loyalty", ""), ("Xaridlar", ""), ("Telegram", ""), ("Til", ""), ("Oxirgi faollik", "r"))
    nz_grid = "minmax(240px,2.3fr) 130px minmax(120px,1.4fr) 120px 110px minmax(110px,1fr) 52px 120px"
    nz_search = "Ism, telefon, username, email yoki Telegram…"
    nz_empty = ("Hali foydalanuvchi yo'q", "Mijozlar saytda, Telegram botda yoki kassada ro'yxatdan o'tganda shu yerda paydo bo'ladi.")
    nz_sorts = (("Yangilari", ""), ("Eskilari", "2"), ("Ism A–Z", "1"))

    hero_icon, hero_tone, hero_noun = "fa-user", "#2563eb", "foydalanuvchi"

    # ---------------------------------------------------------------- list

    def get_queryset(self, request):
        from django.db.models import Prefetch

        return super().get_queryset(request).prefetch_related(
            Prefetch("sessions", queryset=orm.UserSession.objects.order_by("-last_activity")),
            Prefetch("avatar_assets", queryset=orm.UserAvatarAsset.objects.order_by("-created_at")),
        )

    def nz_stats(self, request):
        week = timezone.now() - timedelta(days=7)
        k = orm.User.objects.aggregate(
            total=Count("id"), active=Count("id", filter=Q(status="active")), pending=Count("id", filter=Q(status="pending_verification")),
            blocked=Count("id", filter=Q(status="blocked")), new_week=Count("id", filter=Q(created_at__gte=week)),
            telegram=Count("id", filter=Q(telegram_user_id__isnull=False)),
        )
        seen = orm.UserSession.objects.filter(last_activity__gte=week).values("user_id").distinct().count()
        return [
            ui.stat_card("Jami foydalanuvchi", k["total"], "#2563eb", "fa-users", f"+{k['new_week']} shu hafta", "?"),
            ui.stat_card("Faol", k["active"], "#16a34a", "fa-circle-check", "telefon tasdiqlangan", "?status__exact=active"),
            ui.stat_card("7 kunda kirgan", seen, "#9333ea", "fa-bolt", "kamida bitta sessiya", "?seen=7"),
            ui.stat_card("Telegram ulangan", k["telegram"], "#0891b2", "fa-paper-plane", f"{round(k['telegram'] * 100 / k['total']) if k['total'] else 0}% mijozlar", "?telegram=1"),
            ui.stat_card("Tasdiqlanmagan", k["pending"], "#d97706", "fa-hourglass-half", "SMS kodni kiritmagan", "?status__exact=pending_verification"),
            ui.stat_card("Bloklangan", k["blocked"], "#dc2626", "fa-ban", "kira olmaydi", "?status__exact=blocked"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.User.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [
            ("", "Hammasi", sum(counts.values())), ("active", "Faol", counts.get("active", 0)),
            ("pending_verification", "Tasdiqlanmagan", counts.get("pending_verification", 0)), ("blocked", "Bloklangan", counts.get("blocked", 0)),
        ], {"active": "#16a34a", "pending_verification": "#d97706", "blocked": "#dc2626"})

    def nz_hero_actions(self, request):
        out = [{"label": "Rollar va ruxsatlar", "url": reverse("admin:nz_roles_overview"), "icon": "fa-user-shield"}]
        if self.has_add_permission(request):
            out.append({"label": "Yangi foydalanuvchi", "url": reverse("admin:identity_user_add"), "icon": "fa-user-plus", "primary": True})
        return out

    def nz_prepare(self, request, objs):
        ids = [u.id for u in objs]
        roles: dict = {}
        for ur in orm.UserRole.objects.filter(user_id__in=ids).select_related("role"):
            roles.setdefault(ur.user_id, []).append((ur.role.name, "#6366f1", "fa-user-shield"))
        try:
            from apps.stores.infrastructure.models import Store

            for owner_id, name in Store.objects.filter(owner_id__in=ids).values_list("owner_id", "name"):
                roles.setdefault(owner_id, []).append((name, "#ea580c", "fa-store"))
        except Exception:  # noqa: BLE001
            pass
        wallets, orders, pos = {}, {}, {}
        try:
            from apps.loyalty.infrastructure.models import Wallet

            wallets = {w.user_id: w for w in Wallet.objects.filter(user_id__in=ids).select_related("tier_override")}
        except Exception:  # noqa: BLE001
            pass
        try:
            from apps.ordering.infrastructure.models import OrderModel

            orders = dict(OrderModel.objects.filter(customer_id__in=ids).exclude(status="draft").values("customer_id").annotate(n=Count("id")).values_list("customer_id", "n"))
        except Exception:  # noqa: BLE001
            pass
        try:
            from apps.pos.infrastructure.models import SaleModel

            pos = dict(SaleModel.objects.filter(customer_id__in=ids, status="completed").values("customer_id").annotate(n=Count("id")).values_list("customer_id", "n"))
        except Exception:  # noqa: BLE001
            pass
        for u in objs:
            u._roles, u._wallet, u._orders, u._pos = roles.get(u.id, []), wallets.get(u.id), orders.get(u.id, 0), pos.get(u.id, 0)

    def nz_row(self, u):
        sessions = list(u.sessions.all())
        last = sessions[0].last_activity if sessions else None
        roles = format_html_join("", "{}", ((ui.chip(n, c, i),) for n, c, i in u._roles[:3])) if u._roles else ui.muted("Mijoz")
        w = u._wallet
        loyalty = ui.muted() if w is None or (not w.balance and not w.tier_override) else format_html(
            '<span class="nzi-coins">{}<b>{}</b> <small>coin</small></span>', f"{w.tier_override.name} · " if w.tier_override else "", _som(w.balance))
        buys = ui.muted() if not u._orders and not u._pos else format_html(
            '<span class="nzi-buys" title="Onlayn buyurtmalar · do\'konda xaridlar"><i class="fas fa-globe" aria-hidden="true"></i> {} <i class="fas fa-store" aria-hidden="true"></i> {}</span>', u._orders, u._pos)
        tg = format_html('<span class="nzi-tg"><i class="fab fa-telegram" aria-hidden="true"></i> {}</span>', f"@{u.telegram_username}" if u.telegram_username else "ulangan") if u.telegram_user_id else ui.muted()
        seen = format_html('<span title="{}">{}</span><small>{} sessiya</small>', ui.local(last), ui.ago(last), len(sessions)) if last else ui.muted("hali kirmagan")
        return [ui.user_cell(u), ui.status_pill(u.status), roles, loyalty, buys, tg, format_html('<span class="nzi-lang">{}</span>', (u.language or "").upper()), seen]

    @admin.display(description="Foydalanuvchi", ordering="full_name")
    def user_col(self, obj):
        return obj.full_name

    @admin.display(description="Ro'yxatdan o'tgan", ordering="created_at")
    def joined_col(self, obj):
        return ui.local(obj.created_at, "%d.%m.%Y")

    # ---------------------------------------------------------------- bulk actions (services)

    def _set_status(self, request, users, status: str) -> int:
        from apps.identity.infrastructure.composition import build_admin_update_user_status, build_logout_all

        service, done = build_admin_update_user_status(), 0
        for user in users:
            if user.status == status:
                continue
            try:
                service.execute(actor_user_id=_actor(request), target_user_id=user.id, new_status=status, reason="Dashboard")
            except DomainException as exc:
                messages.error(request, f"{user.full_name or user.phone_number}: {exc}")
                continue
            if status == "blocked":
                build_logout_all().execute(user.id)  # a blocked account must not stay signed in anywhere
            done += 1
        return done

    @admin.action(description="Bloklash (barcha sessiyalar yopiladi)", permissions=["change"])
    def block_selected_users(self, request, queryset):
        messages.success(request, f"{self._set_status(request, queryset, 'blocked')} ta foydalanuvchi bloklandi.")

    @admin.action(description="Faollashtirish", permissions=["change"])
    def activate_selected_users(self, request, queryset):
        messages.success(request, f"{self._set_status(request, queryset, 'active')} ta foydalanuvchi faollashtirildi.")

    @admin.action(description="Barcha qurilmalardan chiqarish", permissions=["change"])
    def logout_selected_users(self, request, queryset):
        from apps.identity.infrastructure.composition import build_logout_all

        for user in queryset:
            build_logout_all().execute(user.id)
        messages.success(request, f"{queryset.count()} ta foydalanuvchining barcha sessiyalari yopildi.")

    # ---------------------------------------------------------------- the profile card

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:  # a new account has no roles / sessions / orders yet
            return [fs for fs in fieldsets if not set(fs[1]["fields"]) & {*self.PANELS, "telegram_username", "id"}]
        return fieldsets

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Telefon raqami majburiy — mijoz shu raqam bilan SMS kod orqali kiradi"}
        label, color, _icon = ui.USER_STATUS.get(obj.status, (obj.status, "#64748b", ""))
        sessions = list(obj.sessions.all())
        live = [s for s in sessions if ui.session_state(s) in ("active", "idle")]
        orders_n, revenue, pos_n = self._purchases(obj)
        try:
            w = obj.wallet
        except Exception:  # noqa: BLE001 - no wallet yet
            w = None
        chips = [ui.status_pill(obj.status)]
        if obj.telegram_user_id:
            chips.append(ui.chip(f"@{obj.telegram_username}" if obj.telegram_username else "Telegram ulangan", "#0891b2", "fa-paper-plane"))
        chips.append(ui.chip(ui.LANGUAGE.get(obj.language, obj.language), "#64748b", "fa-language"))
        chips += [ui.chip(ur.role.name, "#6366f1", "fa-user-shield") for ur in obj.user_roles.select_related("role")]
        return {
            "title": obj.full_name or "Ismsiz foydalanuvchi",
            "subtitle": " · ".join(x for x in (obj.phone_number, f"@{obj.username}" if obj.username else "", obj.email or "",
                                                f"ro'yxatdan o'tgan {ui.local(obj.created_at, '%d.%m.%Y')}") if x),
            "image": ui.avatar_url(obj) or "", "icon": "fa-user", "tone": color, "chips": chips,
            "stats": [
                stat("Onlayn buyurtmalar", orders_n, "#9333ea", f"{_som(revenue)} so'm (bekor qilinganlarsiz)" if revenue else "buyurtma yo'q" if not orders_n else "summa yo'q", "fa-globe"),
                stat("Do'kondagi xaridlar", pos_n, "#ea580c", "kassa orqali", "fa-store"),
                stat("NutriZone Coins", _som(w.balance) if w else "0", "#d97706", (w.tier_override.name if w and w.tier_override else "loyalty hamyoni"), "fa-coins"),
                stat("Faol sessiyalar", len(live), "#16a34a" if live else "#64748b",
                     f"oxirgi: {ui.ago(sessions[0].last_activity)}" if sessions else "hali kirmagan", "fa-shield-halved"),
            ],
            "links": [
                {"label": "Buyurtmalari", "url": reverse("admin:ordering_ordermodel_changelist") + f"?q={obj.phone_number}", "icon": "fa-receipt"},
                *([{"label": "Hamyon", "url": reverse("admin:loyalty_wallet_change", args=[w.pk]), "icon": "fa-wallet"}] if w else []),
                {"label": "Sessiyalari", "url": reverse("admin:identity_usersession_changelist") + f"?user__id__exact={obj.pk}", "icon": "fa-shield-halved"},
            ],
        }

    @staticmethod
    def _purchases(obj) -> tuple[int, float, int]:
        orders_n, revenue, pos_n = 0, 0, 0
        try:
            from apps.ordering.infrastructure.models import OrderModel

            ids = list(OrderModel.objects.filter(customer_id=obj.id).exclude(status="draft").values_list("id", flat=True))
            paid = OrderModel.objects.filter(id__in=ids).exclude(status__in=("cancelled", "returned", "failed")).values_list("id", flat=True)
            totals = _order_totals(ids)
            orders_n, revenue = len(ids), sum((totals.get(i) or 0) for i in paid)
        except Exception:  # noqa: BLE001
            pass
        try:
            from apps.pos.infrastructure.models import SaleModel

            pos_n = SaleModel.objects.filter(customer_id=obj.id, status="completed").count()
        except Exception:  # noqa: BLE001
            pass
        return orders_n, revenue, pos_n

    @admin.display(description="Holat")
    def status_view(self, obj):
        return ui.status_pill(obj.status) if obj else "—"

    @admin.display(description="")
    def roles_panel(self, obj):
        if not obj or not obj.pk:
            return "—"
        rows = list(obj.user_roles.select_related("role").order_by("created_at"))
        stores = _store_names([r.store_id for r in rows])
        items = format_html_join("", '<li><span class="nzi-ico" style="--t:#6366f1"><i class="fas fa-user-shield" aria-hidden="true"></i></span><span><b>{}</b><small>{} · {}</small></span>{}</li>', (
            (r.role.name, f"faqat: {stores.get(r.store_id, 'do‘kon')}" if r.store_id else "barcha do'konlar", ui.local(r.created_at, "%d.%m.%Y"),
             _btn(reverse("admin:identity_user_role_remove", args=[obj.pk, r.pk]), "Olib tashlash", "fa-xmark", "danger", gettext("%(role)s roli olib tashlansinmi?") % {"role": r.role.name}))
            for r in rows))
        try:
            from apps.stores.infrastructure.models import Store

            store_opts = list(Store.objects.filter(kind="store").order_by("name").values_list("id", "name"))
        except Exception:  # noqa: BLE001
            store_opts = []
        role_opts = format_html_join("", '<option value="{}">{}</option>', orm.Role.objects.order_by("name").values_list("code", "name"))
        store_sel = format_html_join("", '<option value="{}">{}</option>', store_opts)
        return format_html(
            '<div class="nzi-panel-body">{}<div class="nzi-add"><select name="nzi_role" aria-label="Rol">{}</select>'
            '<select name="nzi_store" aria-label="Do\'kon"><option value="">Barcha do\'konlar</option>{}</select>{}</div>'
            '<p class="nzi-help">Rol mijozning sayt va ilovadagi ruxsatlarini belgilaydi. Do\'kon tanlansa, rol faqat o\'sha do\'konda amal qiladi.</p></div>',
            format_html('<ul class="nzi-items">{}</ul>', items) if rows else format_html('<p class="nzi-none">{}</p>', "Rol biriktirilmagan — oddiy mijoz."),
            role_opts, store_sel, _btn(reverse("admin:identity_user_role_add", args=[obj.pk]), "Rol biriktirish", "fa-plus", "primary"),
        )

    @admin.display(description="")
    def security_panel(self, obj):
        if not obj or not obj.pk:
            return "—"
        sessions = list(obj.sessions.all())
        live = [s for s in sessions if ui.session_state(s) in ("active", "idle")]
        rows = format_html_join("", '<li class="is-{}"><span class="nzi-ico" style="--t:{}"><i class="{} {}" aria-hidden="true"></i></span><span><b>{}</b><small>{} · IP {} · kirgan {}</small></span><span class="nzi-when"><b>{}</b><small>{}</small></span>{}</li>', (
            (st, ui.SESSION_STATE[st][1], ui.icon_family(ua["icon"]), ua["icon"], ua["label"] if not ua["tool"] else ui.DEVICE.get(s.device_type, ("Sessiya", ""))[0],
             ui.DEVICE.get(s.device_type, (s.device_type, ""))[0], s.ip_address or "—", ui.local(s.created_at, "%d.%m.%Y"),
             ui.ago(s.last_activity), ui.SESSION_STATE[st][0],
             _btn(reverse("admin:identity_user_session_revoke", args=[obj.pk, s.pk]), "Yopish", "fa-right-from-bracket", "danger") if st in ("active", "idle") else "")
            for s in sessions[:8] for st, ua in [(ui.session_state(s), ui.parse_ua(s.user_agent))]))
        devices = list(obj.devices.all()[:6])
        dev = format_html_join("", '<span class="nzi-chip" style="--t:{}"><i class="fas {}" aria-hidden="true"></i> {}{}</span>', (
            ("#16a34a" if d.is_trusted else "#64748b", ui.DEVICE.get(d.device_type, ("", "fa-mobile"))[1], d.device_name or ui.DEVICE.get(d.device_type, (d.device_type, ""))[0],
             " · ishonchli" if d.is_trusted else "") for d in devices))
        actions = []
        if live:
            actions.append(_btn(reverse("admin:identity_user_logout_all", args=[obj.pk]), f"Barcha qurilmalardan chiqarish ({len(live)})", "fa-power-off", "danger",
                                "Foydalanuvchi barcha qurilmalarda qayta kirishi kerak bo'ladi. Davom etilsinmi?"))
        if obj.status == "blocked":
            actions.append(_btn(reverse("admin:identity_user_status", args=[obj.pk, "active"]), "Blokdan chiqarish", "fa-unlock", "primary"))
        else:
            actions.append(_btn(reverse("admin:identity_user_status", args=[obj.pk, "blocked"]), "Bloklash", "fa-ban", "danger",
                                "Foydalanuvchi bloklanadi va barcha sessiyalari yopiladi. Davom etilsinmi?"))
            if obj.status == "pending_verification":
                actions.append(_btn(reverse("admin:identity_user_status", args=[obj.pk, "active"]), "Qo'lda tasdiqlash", "fa-user-check", "primary"))
        return format_html(
            '<div class="nzi-panel-body"><div class="nzi-sec-sum"><span><b>{}</b> faol sessiya</span><span><b>{}</b> jami</span><span><b>{}</b> qurilma</span></div>{}{}<div class="nzi-actions">{}</div></div>',
            len(live), len(sessions), len(devices),
            format_html('<ul class="nzi-items">{}</ul>', rows) if sessions else format_html('<p class="nzi-none">{}</p>', "Hali tizimga kirmagan."),
            format_html('<div class="nzi-devs"><small>Qurilmalar:</small> {}</div>', dev) if devices else "",
            format_html_join("", "{}", ((a,) for a in actions)),
        )

    @admin.display(description="")
    def orders_panel(self, obj):
        if not obj or not obj.pk:
            return "—"
        try:
            from apps.ordering.infrastructure.models import OrderModel

            orders = list(OrderModel.objects.filter(customer_id=obj.id).exclude(status="draft").order_by("-created_at")[:6])
            totals = _order_totals([o.pk for o in orders])
        except Exception:  # noqa: BLE001
            orders, totals = [], {}
        tone = {"delivered": "#16a34a", "completed": "#16a34a", "cancelled": "#dc2626", "returned": "#dc2626", "failed": "#dc2626", "pending_payment": "#d97706"}
        rows = format_html_join("", '<li><span class="nzi-ico" style="--t:{}"><i class="fas fa-receipt" aria-hidden="true"></i></span><span><a href="{}"><b>{}</b></a><small>{}</small></span><span class="nzi-when"><b>{}</b><small>{}</small></span></li>', (
            (tone.get(o.status, "#6366f1"), reverse("admin:ordering_ordermodel_change", args=[o.pk]), o.order_number, ui.local(o.created_at),
             f"{_som(totals.get(o.pk))} so'm" if totals.get(o.pk) else "—", o.get_status_display()) for o in orders))
        return format_html('<div class="nzi-panel-body">{}</div>', format_html('<ul class="nzi-items">{}</ul>', rows) if orders else format_html('<p class="nzi-none">{}</p>', "Onlayn buyurtma yo'q."))

    # ---------------------------------------------------------------- card actions (POST, services)

    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("<uuid:pk>/nz/status/<str:status>/", v(self.status_action), name="identity_user_status"),
            path("<uuid:pk>/nz/session/<uuid:sid>/revoke/", v(self.revoke_action), name="identity_user_session_revoke"),
            path("<uuid:pk>/nz/logout-all/", v(self.logout_all_action), name="identity_user_logout_all"),
            path("<uuid:pk>/nz/role/add/", v(self.role_add_action), name="identity_user_role_add"),
            path("<uuid:pk>/nz/role/<uuid:aid>/remove/", v(self.role_remove_action), name="identity_user_role_remove"),
            *super().get_urls(),
        ]

    def _guard(self, request, pk):
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied
        return get_object_or_404(orm.User, pk=pk)

    def _back(self, pk, anchor=""):
        return HttpResponseRedirect(reverse("admin:identity_user_change", args=[pk]) + anchor)

    def status_action(self, request, pk, status):
        user = self._guard(request, pk)
        if status not in ("active", "blocked"):
            raise PermissionDenied
        if self._set_status(request, [user], status):
            messages.success(request, "Foydalanuvchi bloklandi, barcha sessiyalari yopildi." if status == "blocked" else "Foydalanuvchi faollashtirildi.")
        return self._back(pk)

    def revoke_action(self, request, pk, sid):
        from apps.identity.infrastructure.composition import build_revoke_session

        self._guard(request, pk)
        session = get_object_or_404(orm.UserSession, pk=sid, user_id=pk)
        build_revoke_session().execute(requesting_user_id=_actor(request), target_session_id=session.pk, is_staff_override=True)
        messages.success(request, "Sessiya yopildi — bu qurilmada qayta kirish kerak bo'ladi.")
        return self._back(pk)

    def logout_all_action(self, request, pk):
        from apps.identity.infrastructure.composition import build_logout_all

        self._guard(request, pk)
        build_logout_all().execute(pk)
        messages.success(request, "Barcha sessiyalar yopildi.")
        return self._back(pk)

    def role_add_action(self, request, pk):
        from apps.identity.infrastructure.composition import build_assign_role

        self._guard(request, pk)
        store = request.POST.get("nzi_store") or None
        try:
            build_assign_role().execute(user_id=pk, role_code=request.POST.get("nzi_role", ""), store_id=uuid.UUID(store) if store else None)
        except (DomainException, ValueError) as exc:
            messages.error(request, f"Rol biriktirilmadi: {exc}")
        else:
            messages.success(request, "Rol biriktirildi.")
        return self._back(pk)

    def role_remove_action(self, request, pk, aid):
        from apps.identity.infrastructure.composition import build_remove_role

        self._guard(request, pk)
        get_object_or_404(orm.UserRole, pk=aid, user_id=pk)
        build_remove_role().execute(aid, actor_id=_actor(request))
        messages.success(request, "Rol olib tashlandi.")
        return self._back(pk)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        uploaded = form.cleaned_data.get("avatar_upload")
        if uploaded:
            from apps.identity.infrastructure.composition import build_upload_avatar

            build_upload_avatar().execute(user_id=obj.id, filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type)


# ================================================================ sessions


class SessionStateFilter(admin.SimpleListFilter):
    title = "Holat"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [(k, v[0]) for k, v in ui.SESSION_STATE.items()]

    def queryset(self, request, queryset):
        now, idle = timezone.now(), timezone.now() - timedelta(days=ui.IDLE_DAYS)
        return {
            "active": queryset.filter(revoked_at__isnull=True, expires_at__gt=now, last_activity__gte=idle),
            "idle": queryset.filter(revoked_at__isnull=True, expires_at__gt=now, last_activity__lt=idle),
            "expired": queryset.filter(revoked_at__isnull=True, expires_at__lte=now),
            "revoked": queryset.filter(revoked_at__isnull=False),
        }.get(self.value(), queryset)


@admin.register(orm.UserSession)
class UserSessionAdmin(ui.PremiumListMixin, admin.ModelAdmin):
    """
    Sessiyalar: every login (refresh-token session) -- who, which browser / device, IP, last activity, state; staff can
    close a session (RevokeSession) or sign a user out everywhere (LogoutAll). `refresh_token_hash` is a secret and is
    never listed or shown (readonly does not mean hidden).
    """

    list_display = ("user", "last_activity", "created_at")
    list_filter = (SessionStateFilter, ("device_type", _titled(admin.ChoicesFieldListFilter, "Qurilma turi")), ("last_activity", _titled(admin.DateFieldListFilter, "Oxirgi faollik")))
    search_fields = ("user__phone_number", "user__full_name", "ip_address")
    list_select_related = ("user",)
    list_per_page = 30
    ordering = ("-last_activity",)
    actions = ["revoke_selected"]
    fields = ("id", "user", "device", "device_name", "device_type", "ip_address", "user_agent", "last_activity", "expires_at", "revoked_at", "created_at")
    readonly_fields = fields

    nz_icon, nz_tone, nz_title = "fa-shield-halved", "#16a34a", "Sessiyalar"
    nz_subtitle = "Kim qaysi qurilmadan kirgan, qachon faol bo'lgan va qaysi sessiyalar ochiq. Shubhali sessiyani bir bosishda yopish mumkin."
    nz_columns = (("Foydalanuvchi", ""), ("Qurilma / brauzer", ""), ("IP manzil", ""), ("Kirgan", ""), ("Oxirgi faollik", ""), ("Tugaydi", ""), ("Holat", "r"))
    nz_grid = "minmax(220px,2fr) minmax(170px,1.5fr) 130px 110px 130px 120px 130px"
    nz_search = "Ism, telefon yoki IP…"
    nz_empty = ("Hali sessiya yo'q", "Mijoz saytga yoki ilovaga kirganda sessiya yaratiladi.")
    nz_sorts = (("Oxirgi faollik", ""), ("Yangi kirganlar", "-3"))

    def has_add_permission(self, request):
        return False  # sessions are created by signing in, never by hand

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        from django.db.models import Prefetch

        return super().get_queryset(request).prefetch_related(Prefetch("user__avatar_assets", queryset=orm.UserAvatarAsset.objects.order_by("-created_at")))

    def nz_stats(self, request):
        now, idle, day = timezone.now(), timezone.now() - timedelta(days=ui.IDLE_DAYS), timezone.now() - timedelta(days=1)
        qs = orm.UserSession.objects
        open_ = qs.filter(revoked_at__isnull=True, expires_at__gt=now)
        return [
            ui.stat_card("Ochiq sessiyalar", open_.count(), "#16a34a", "fa-shield-halved", f"{open_.values('user_id').distinct().count()} foydalanuvchi", "?state=active"),
            ui.stat_card("24 soatda faol", qs.filter(last_activity__gte=day).count(), "#2563eb", "fa-bolt", "oxirgi sutka", ""),
            ui.stat_card("Yangi kirishlar (7 kun)", qs.filter(created_at__gte=idle).count(), "#9333ea", "fa-right-to-bracket", "", ""),
            ui.stat_card("Yopilgan", qs.filter(revoked_at__isnull=False).count(), "#dc2626", "fa-lock", "chiqish yoki admin tomonidan", "?state=revoked"),
        ]

    def nz_tabs(self, request):
        now, idle = timezone.now(), timezone.now() - timedelta(days=ui.IDLE_DAYS)
        k = orm.UserSession.objects.aggregate(
            all=Count("id"), active=Count("id", filter=Q(revoked_at__isnull=True, expires_at__gt=now, last_activity__gte=idle)),
            idle=Count("id", filter=Q(revoked_at__isnull=True, expires_at__gt=now, last_activity__lt=idle)),
            expired=Count("id", filter=Q(revoked_at__isnull=True, expires_at__lte=now)), revoked=Count("id", filter=Q(revoked_at__isnull=False)))
        return ui.tabs_for(request, "state", [("", "Hammasi", k["all"]), ("active", "Faol", k["active"]), ("idle", f"{ui.IDLE_DAYS}+ kun faol emas", k["idle"]),
                                              ("expired", "Muddati tugagan", k["expired"]), ("revoked", "Yopilgan", k["revoked"])],
                           {k2: v[1] for k2, v in ui.SESSION_STATE.items()})

    def nz_href(self, obj):
        return reverse("admin:identity_user_change", args=[obj.user_id])

    def nz_row(self, s):
        st, ua = ui.session_state(s), ui.parse_ua(s.user_agent)
        dev_label, dev_icon = ui.DEVICE.get(s.device_type, (s.device_type, "fa-circle"))
        device = format_html('<span class="nzi-dev"><i class="fas {}" aria-hidden="true"></i><span><b>{}</b><small>{}</small></span></span>',
                             dev_icon, dev_label if ua["tool"] else ua["label"], s.device_name or (dev_label if not ua["tool"] else "brauzer ma'lumoti yo'q"))
        return [
            ui.user_cell(s.user), device, format_html("<code>{}</code>", s.ip_address or "—"),
            format_html('<span title="{}">{}</span>', ui.local(s.created_at), ui.local(s.created_at, "%d.%m.%Y")),
            format_html('<span title="{}">{}</span>', ui.local(s.last_activity), ui.ago(s.last_activity)),
            ui.muted(ui.local(s.revoked_at, "%d.%m.%Y")) if s.revoked_at else format_html('<span title="{}">{}</span>', ui.local(s.expires_at), ui.ago(s.expires_at)),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>', ui.SESSION_STATE[st][1], ui.SESSION_STATE[st][0]),
        ]

    @admin.action(description="Tanlangan sessiyalarni yopish")
    def revoke_selected(self, request, queryset):
        from apps.identity.infrastructure.composition import build_revoke_session

        if not request.user.has_perm("identity.change_user"):
            raise PermissionDenied
        service, n = build_revoke_session(), 0
        for s in queryset.filter(revoked_at__isnull=True):
            service.execute(requesting_user_id=_actor(request), target_session_id=s.pk, is_staff_override=True)
            n += 1
        messages.success(request, f"{n} ta sessiya yopildi.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm("identity.change_user"):
            actions.pop("revoke_selected", None)
        return actions


# ================================================================ devices


@admin.register(orm.Device)
class DeviceAdmin(ui.PremiumListMixin, admin.ModelAdmin):
    """
    Qurilmalar: registered app / POS devices per user, trusted or not. `push_token` (abusable if leaked -- pushes can be
    sent to the device with it) is never listed or shown, only whether one exists.
    """

    list_display = ("device_name", "created_at")
    list_filter = (("device_type", _titled(admin.ChoicesFieldListFilter, "Qurilma turi")), ("is_trusted", _titled(admin.BooleanFieldListFilter, "Ishonchli")))
    search_fields = ("device_name", "user__phone_number", "user__full_name")
    list_select_related = ("user",)
    list_per_page = 30
    ordering = ("-created_at",)
    fields = ("id", "user", "device_type", "device_name", "is_trusted", "created_at")
    readonly_fields = fields

    nz_icon, nz_tone, nz_title = "fa-mobile-screen", "#0891b2", "Qurilmalar"
    nz_subtitle = "Mijozlar ilovasi va kassalardagi ro'yxatdan o'tgan qurilmalar: turi, egasi, ishonchliligi va push bildirishnoma holati."
    nz_columns = (("Qurilma", ""), ("Egasi", ""), ("Turi", ""), ("Push", ""), ("Sessiyalar", "r"), ("Ro'yxatga olingan", "r"))
    nz_grid = "minmax(200px,1.6fr) minmax(220px,2fr) 140px 120px 110px 130px"
    nz_search = "Qurilma nomi, ism yoki telefon…"
    nz_empty = ("Hali qurilma ro'yxatdan o'tmagan", "Qurilmalar mobil ilova yoki kassa push bildirishnomaga ulanganda yoziladi. Veb-saytdagi kirishlar «Sessiyalar» bo'limida ko'rinadi.")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def nz_stats(self, request):
        k = orm.Device.objects.aggregate(all=Count("id"), trusted=Count("id", filter=Q(is_trusted=True)), push=Count("id", filter=Q(push_token__isnull=False) & ~Q(push_token="")),
                                         mobile=Count("id", filter=Q(device_type="mobile")), pos=Count("id", filter=Q(device_type="pos")))
        return [
            ui.stat_card("Jami qurilma", k["all"], "#0891b2", "fa-mobile-screen", f"{k['mobile']} mobil · {k['pos']} kassa"),
            ui.stat_card("Ishonchli", k["trusted"], "#16a34a", "fa-circle-check", "tasdiqlangan qurilmalar", "?is_trusted__exact=1"),
            ui.stat_card("Push yoqilgan", k["push"], "#9333ea", "fa-bell", "bildirishnoma oladi"),
            ui.stat_card("Veb sessiyalar", orm.UserSession.objects.filter(revoked_at__isnull=True, expires_at__gt=timezone.now(), device__isnull=True).count(),
                         "#2563eb", "fa-globe", "qurilmasiz (brauzer) kirishlar", reverse("admin:identity_usersession_changelist") + "?state=active"),
        ]

    def nz_prepare(self, request, objs):
        counts = dict(orm.UserSession.objects.filter(device__in=objs).values("device_id").annotate(n=Count("id")).values_list("device_id", "n"))
        for d in objs:
            d._sessions = counts.get(d.pk, 0)

    def nz_href(self, obj):
        return reverse("admin:identity_user_change", args=[obj.user_id]) if obj.user_id else super().nz_href(obj)

    def nz_row(self, d):
        label, icon = ui.DEVICE.get(d.device_type, (d.device_type, "fa-mobile"))
        return [
            format_html('<span class="nzi-dev"><i class="fas {}" aria-hidden="true"></i><span><b>{}</b><small>{}</small></span></span>', icon, d.device_name or label,
                        "ishonchli" if d.is_trusted else "tasdiqlanmagan"),
            ui.user_cell(d.user), ui.chip(label, "#0891b2", icon),
            ui.chip("Yoqilgan", "#9333ea", "fa-bell") if d.push_token else ui.muted("yo'q"),
            format_html("<b>{}</b>", d._sessions), ui.local(d.created_at, "%d.%m.%Y"),
        ]


# ================================================================ roles & permissions


class PermissionCheckboxes(forms.CheckboxSelectMultiple):
    """Each checkbox carries its module (label / icon / colour) and code, so the page JS can group them into module cards."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        _key, mod, icon, color = ui.module_of(str(value))
        option["attrs"].update({"data-module": mod, "data-icon": icon, "data-color": color, "data-code": str(value), "data-label": str(label), "data-nzi-perm": "1"})
        return option


class RoleAdminForm(forms.ModelForm):
    permissions = forms.MultipleChoiceField(required=False, widget=PermissionCheckboxes, label="Ruxsatlar")

    class Meta:
        model = orm.Role
        fields = ("name", "code", "is_system_role")
        labels = {"name": "Rol nomi", "code": "Kod", "is_system_role": "Tizim roli"}
        help_texts = {
            "code": "Lotin harflari, raqam va _ (masalan: store_manager). Kod orqali dasturda tekshiriladi — keyin o'zgartirmang.",
            "is_system_role": "Tizim roli avtomatik beriladi (masalan, har bir yangi mijozga «customer») va o'chirilmaydi.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        perms = list(orm.Permission.objects.order_by("code").values_list("code", "description"))
        self.fields["permissions"].choices = [(c, ui.permission_label(c, d)) for c, d in perms]
        if self.instance and self.instance.pk:
            self.fields["permissions"].initial = list(orm.RolePermission.objects.filter(role=self.instance).values_list("permission__code", flat=True))
            if self.instance.is_system_role:
                self.fields["code"].disabled = True

    def clean_code(self):
        import re

        code = (self.cleaned_data.get("code") or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,62}", code):
            raise forms.ValidationError("Faqat kichik lotin harflari, raqamlar va _ (harf bilan boshlansin), 2–63 belgi.")
        return code


@admin.register(orm.Role)
class RoleAdmin(ui.PremiumListMixin, CatalogFormMixin, admin.ModelAdmin):
    """Rollar: what each role may do (permission matrix, SetRolePermissions) and who holds it."""

    form = RoleAdminForm
    change_form_template = "admin/premium/form.html"
    list_display = ("name", "created_at")
    search_fields = ("code", "name")
    list_per_page = 30
    ordering = ("name",)
    fieldsets = (
        ("Rol", {"fields": ("name", "code", "is_system_role")}),
        ("Ruxsatlar", {"classes": ("nzi-perms",), "fields": ("permissions",)}),
        ("Kimlarda bor", {"classes": ("nzi-panel",), "fields": ("holders_panel",)}),
    )
    readonly_fields = ("holders_panel",)

    nz_icon, nz_tone, nz_title = "fa-user-shield", "#6366f1", "Rollar"
    nz_subtitle = "Har bir rol mijoz sayt va ilovada nima qila olishini belgilaydi. Rolni oching — ruxsatlarni modul bo'yicha belgilang."
    nz_columns = (("Rol", ""), ("Turi", ""), ("Ruxsatlar", ""), ("Foydalanuvchilar", "r"), ("Yaratilgan", "r"))
    nz_grid = "minmax(220px,1.6fr) 130px minmax(260px,2.4fr) 140px 120px"
    nz_search = "Rol nomi yoki kodi…"
    nz_empty = ("Hali rol yo'q", "Rol yarating va unga ruxsatlarni biriktiring.")
    hero_icon, hero_tone, hero_noun = "fa-user-shield", "#6366f1", "rol"

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        return [fs for fs in fieldsets if obj is not None or "holders_panel" not in fs[1]["fields"]]

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.is_system_role or obj.user_roles.exists()):
            return False  # a system role, or one people still hold, is never deleted from here
        return super().has_delete_permission(request, obj)

    def nz_stats(self, request):
        total, perms = orm.Role.objects.count(), orm.Permission.objects.count()
        orphan = orm.Permission.objects.filter(role_permissions__isnull=True).count()
        holders = orm.UserRole.objects.values("user_id").distinct().count()
        return [
            ui.stat_card("Rollar", total, "#6366f1", "fa-user-shield", f"{orm.Role.objects.filter(is_system_role=True).count()} tizim roli"),
            ui.stat_card("Ruxsatlar", perms, "#0891b2", "fa-key", "tizimdagi barcha ruxsatlar", reverse("admin:identity_permission_changelist")),
            ui.stat_card("Rolga ega foydalanuvchilar", holders, "#16a34a", "fa-users", f"{orm.UserRole.objects.count()} ta biriktirish", reverse("admin:identity_userrole_changelist")),
            ui.stat_card("Hech bir rolda yo'q", orphan, "#d97706" if orphan else "#16a34a", "fa-triangle-exclamation" if orphan else "fa-circle-check",
                         "ishlatilmayotgan ruxsatlar" if orphan else "barcha ruxsatlar biriktirilgan", reverse("admin:identity_permission_changelist") + "?used=0"),
        ]

    def nz_hero_actions(self, request):
        out = [{"label": "Ruxsatlar matritsasi", "url": reverse("admin:nz_roles_overview"), "icon": "fa-table-cells"}]
        if self.has_add_permission(request):
            out.append({"label": "Yangi rol", "url": reverse("admin:identity_role_add"), "icon": "fa-plus", "primary": True})
        return out

    def nz_prepare(self, request, objs):
        perms: dict = {}
        for role_id, code in orm.RolePermission.objects.filter(role__in=objs).values_list("role_id", "permission__code"):
            perms.setdefault(role_id, []).append(code)
        users = dict(orm.UserRole.objects.filter(role__in=objs).values("role_id").annotate(n=Count("user_id", distinct=True)).values_list("role_id", "n"))
        for r in objs:
            r._perms, r._users = perms.get(r.pk, []), users.get(r.pk, 0)

    def nz_row(self, r):
        modules: dict = {}
        for code in r._perms:
            key, label, icon, color = ui.module_of(code)
            modules.setdefault(key, [label, icon, color, 0])[3] += 1
        mods = format_html_join("", "{}", ((ui.chip(f"{m[0]} {m[3]}", m[2], m[1]),) for m in sorted(modules.values(), key=lambda m: -m[3]))) if modules else ui.muted("ruxsat yo'q")
        return [
            format_html('<span class="nzi-role"><span class="nzi-ico" style="--t:#6366f1"><i class="fas fa-user-shield" aria-hidden="true"></i></span><span><b>{}</b><small><code>{}</code></small></span></span>', r.name, r.code),
            ui.chip("Tizim", "#0891b2", "fa-lock") if r.is_system_role else ui.chip("Maxsus", "#64748b", "fa-pen"),
            format_html('<span class="nzi-mods"><b>{}</b> {}</span>', len(r._perms), mods),
            format_html('<a href="{}?role__id__exact={}"><b>{}</b> <small>kishi</small></a>', reverse("admin:identity_userrole_changelist"), r.pk, r._users),
            ui.local(r.created_at, "%d.%m.%Y"),
        ]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Nom va kodni kiriting, so'ng ruxsatlarni belgilang"}
        codes = list(orm.RolePermission.objects.filter(role=obj).values_list("permission__code", flat=True))
        users = obj.user_roles.values("user_id").distinct().count()
        total = orm.Permission.objects.count()
        return {
            "title": obj.name, "subtitle": f"kod: {obj.code}",
            "chips": [ui.chip("Tizim roli", "#0891b2", "fa-lock") if obj.is_system_role else ui.chip("Maxsus rol", "#64748b", "fa-pen")],
            "stats": [
                stat("Ruxsatlar", f"{len(codes)} / {total}", "#6366f1", "biriktirilgan", "fa-key"),
                stat("Modullar", len({ui.module_of(c)[0] for c in codes}), "#0891b2", "qamrab olingan", "fa-layer-group"),
                stat("Foydalanuvchilar", users, "#16a34a", "shu rolga ega", "fa-users"),
            ],
            "links": [{"label": "Kimlarda bor", "url": reverse("admin:identity_userrole_changelist") + f"?role__id__exact={obj.pk}", "icon": "fa-users"},
                      {"label": "Matritsa", "url": reverse("admin:nz_roles_overview"), "icon": "fa-table-cells"}],
        }

    @admin.display(description="")
    def holders_panel(self, obj):
        if not obj or not obj.pk:
            return "—"
        rows = list(obj.user_roles.select_related("user").prefetch_related("user__avatar_assets").order_by("-created_at")[:12])
        stores = _store_names([r.store_id for r in rows])
        items = format_html_join("", '<li><a href="{}">{}</a><span class="nzi-when"><b>{}</b><small>{}</small></span></li>', (
            (reverse("admin:identity_user_change", args=[r.user_id]), ui.user_cell(r.user), stores.get(r.store_id, "barcha do'konlar") if r.store_id else "barcha do'konlar",
             ui.local(r.created_at, "%d.%m.%Y")) for r in rows))
        more = obj.user_roles.count() - len(rows)
        return format_html('<div class="nzi-panel-body">{}{}</div>', format_html('<ul class="nzi-items">{}</ul>', items) if rows else format_html('<p class="nzi-none">{}</p>', "Hali hech kimga berilmagan."),
                           format_html('<a class="nzi-more" href="{}?role__id__exact={}">yana {} ta →</a>', reverse("admin:identity_userrole_changelist"), obj.pk, more) if more > 0 else "")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from apps.identity.infrastructure.composition import build_set_role_permissions

        try:
            added, removed = build_set_role_permissions().execute(form.instance.pk, form.cleaned_data.get("permissions") or [], actor_id=_actor(request))
        except DomainException as exc:
            messages.error(request, f"Ruxsatlar saqlanmadi: {exc}")
            return
        if added or removed:
            messages.info(request, f"Ruxsatlar yangilandi: +{len(added)} / −{len(removed)}. Foydalanuvchilarda bir necha daqiqada kuchga kiradi.")


class PermissionUsageFilter(admin.SimpleListFilter):
    title = "Ishlatilishi"
    parameter_name = "used"

    def lookups(self, request, model_admin):
        return [("1", "Rolga biriktirilgan"), ("0", "Hech bir rolda yo'q")]

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(role_permissions__isnull=False).distinct()
        if self.value() == "0":
            return queryset.filter(role_permissions__isnull=True)
        return queryset


class PermissionModuleFilter(admin.SimpleListFilter):
    title = "Modul"
    parameter_name = "module"

    def lookups(self, request, model_admin):
        keys = sorted({c.split(".")[0] for c in orm.Permission.objects.values_list("code", flat=True)})
        return [(k, ui.module_of(k)[1]) for k in keys]

    def queryset(self, request, queryset):
        return queryset.filter(code__startswith=f"{self.value()}.") if self.value() else queryset


class PermissionAdminForm(forms.ModelForm):
    class Meta:
        model = orm.Permission
        fields = ("code", "description")
        labels = {"code": "Kod", "description": "Tavsif"}
        help_texts = {"code": "modul.resurs.amal ko'rinishida, masalan: reviews.review.create. Dasturdagi tekshiruvlar shu kodni ishlatadi.",
                      "description": "Inson tushunadigan izoh — rol tahririda shu matn ko'rinadi."}

    def clean_code(self):
        import re

        code = (self.cleaned_data.get("code") or "").strip().lower()
        if not re.fullmatch(r"[a-z_]+(\.[a-z_]+){2,}", code):
            raise forms.ValidationError("Kod modul.resurs.amal ko'rinishida bo'lsin (kichik lotin harflari va _).")
        return code


@admin.register(orm.Permission)
class PermissionAdmin(ui.PremiumListMixin, CatalogFormMixin, admin.ModelAdmin):
    """Ruxsatlar: every permission code, grouped by module, with the roles that grant it."""

    form = PermissionAdminForm
    change_form_template = "admin/premium/form.html"
    list_display = ("code", "created_at")
    list_filter = (PermissionModuleFilter, PermissionUsageFilter)
    search_fields = ("code", "description")
    list_per_page = 50
    ordering = ("code",)
    fieldsets = (("Ruxsat", {"fields": ("code", "description")}), ("Qaysi rollarda bor", {"classes": ("nzi-panel",), "fields": ("roles_panel",)}))
    readonly_fields = ("roles_panel",)

    nz_icon, nz_tone, nz_title = "fa-key", "#0891b2", "Ruxsatlar"
    nz_subtitle = "Mijoz ilovada bajarishi mumkin bo'lgan har bir amal. Ruxsat rolga biriktiriladi, rol esa foydalanuvchiga."
    nz_columns = (("Ruxsat", ""), ("Modul", ""), ("Kod", ""), ("Rollar", ""))
    nz_grid = "minmax(240px,2fr) 170px minmax(220px,1.6fr) minmax(160px,1.4fr)"
    nz_search = "Kod yoki tavsif…"
    nz_empty = ("Ruxsatlar yo'q", "")
    hero_icon, hero_tone, hero_noun = "fa-key", "#0891b2", "ruxsat"

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        return [fs for fs in fieldsets if obj is not None or "roles_panel" not in fs[1]["fields"]]

    def nz_tabs(self, request):
        counts: dict = {}
        for code in orm.Permission.objects.values_list("code", flat=True):
            key = code.split(".")[0]
            counts[key] = counts.get(key, 0) + 1
        return ui.tabs_for(request, "module", [("", "Hammasi", sum(counts.values()))] + [(k, ui.module_of(k)[1], n) for k, n in sorted(counts.items())],
                           {k: ui.module_of(k)[3] for k in counts})

    def nz_hero_actions(self, request):
        out = [{"label": "Rollar", "url": reverse("admin:identity_role_changelist"), "icon": "fa-user-shield"},
               {"label": "Matritsa", "url": reverse("admin:nz_roles_overview"), "icon": "fa-table-cells"}]
        if self.has_add_permission(request):
            out.append({"label": "Yangi ruxsat", "url": reverse("admin:identity_permission_add"), "icon": "fa-plus", "primary": True})
        return out

    def nz_prepare(self, request, objs):
        roles: dict = {}
        for pid, name in orm.RolePermission.objects.filter(permission__in=objs).values_list("permission_id", "role__name"):
            roles.setdefault(pid, []).append(name)
        for p in objs:
            p._roles = roles.get(p.pk, [])

    def nz_row(self, p):
        _key, label, icon, color = ui.module_of(p.code)
        return [
            format_html('<span class="nzi-role"><span class="nzi-ico" style="--t:{}"><i class="fas {}" aria-hidden="true"></i></span><span><b>{}</b></span></span>', color, icon, ui.permission_label(p.code, p.description)),
            ui.chip(label, color, icon), format_html("<code>{}</code>", p.code),
            format_html_join("", "{}", ((ui.chip(n, "#6366f1", "fa-user-shield"),) for n in p._roles)) if p._roles else ui.chip("hech bir rolda yo'q", "#d97706", "fa-triangle-exclamation"),
        ]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Kod: modul.resurs.amal"}
        _key, label, icon, color = ui.module_of(obj.code)
        return {"title": ui.permission_label(obj.code, obj.description), "subtitle": obj.code, "icon": icon, "tone": color, "chips": [ui.chip(label, color, icon)]}

    @admin.display(description="")
    def roles_panel(self, obj):
        if not obj or not obj.pk:
            return "—"
        roles = list(orm.Role.objects.filter(role_permissions__permission=obj).order_by("name"))
        items = format_html_join("", '<li><span class="nzi-ico" style="--t:#6366f1"><i class="fas fa-user-shield" aria-hidden="true"></i></span><span><a href="{}"><b>{}</b></a><small>{}</small></span></li>',
                                 ((reverse("admin:identity_role_change", args=[r.pk]), r.name, r.code) for r in roles))
        return format_html('<div class="nzi-panel-body">{}</div>', format_html('<ul class="nzi-items">{}</ul>', items) if roles else format_html('<p class="nzi-none">{}</p>', "Hech bir rolga biriktirilmagan — rolni ochib belgilang."))


# ================================================================ role assignments


class UserRoleAdminForm(forms.ModelForm):
    store = forms.ChoiceField(required=False, label="Do'kon (ixtiyoriy)", help_text="Tanlansa, rol faqat shu do'kon doirasida amal qiladi.")

    class Meta:
        model = orm.UserRole
        fields = ("user", "role")
        labels = {"user": "Foydalanuvchi", "role": "Rol"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from apps.stores.infrastructure.models import Store

            opts = list(Store.objects.filter(kind="store").order_by("name").values_list("id", "name"))
        except Exception:  # noqa: BLE001
            opts = []
        self.fields["store"].choices = [("", "Barcha do'konlar")] + [(str(i), n) for i, n in opts]


@admin.register(orm.UserRole)
class UserRoleAdmin(ui.PremiumListMixin, CatalogFormMixin, admin.ModelAdmin):
    """Foydalanuvchi rollari: who holds which role (optionally scoped to one store); assigning / removing goes through AssignRole / RemoveRole."""

    form = UserRoleAdminForm
    change_form_template = "admin/premium/form.html"
    list_display = ("user", "created_at")
    list_filter = (("role", _titled(admin.RelatedFieldListFilter, "Rol")),)
    search_fields = ("user__phone_number", "user__full_name", "role__name")
    list_select_related = ("user", "role")
    autocomplete_fields = ("user",)
    list_per_page = 30
    ordering = ("-created_at",)
    actions = ["remove_selected"]
    fieldsets = (("Biriktirish", {"fields": ("user", "role", "store")}),)

    nz_icon, nz_tone, nz_title = "fa-id-badge", "#9333ea", "Foydalanuvchi rollari"
    nz_subtitle = "Kimga qaysi rol berilgan va qaysi do'kon doirasida. Rol berish yoki olib tashlash darhol ruxsatlarga ta'sir qiladi."
    nz_columns = (("Foydalanuvchi", ""), ("Rol", ""), ("Doirasi", ""), ("Ruxsatlar", "r"), ("Berilgan", "r"))
    nz_grid = "minmax(240px,2fr) minmax(160px,1.2fr) minmax(160px,1.2fr) 110px 120px"
    nz_search = "Ism, telefon yoki rol…"
    nz_empty = ("Hali hech kimga rol berilmagan", "«Rol biriktirish» tugmasi bilan boshlang.")
    hero_icon, hero_tone, hero_noun = "fa-id-badge", "#9333ea", "rol biriktirish"

    def has_change_permission(self, request, obj=None):
        return False if obj is not None else super().has_change_permission(request, obj)  # an assignment is added or removed, never edited

    def has_delete_permission(self, request, obj=None):
        return False  # removal runs through RemoveRole (the list action / the user's card)

    def get_queryset(self, request):
        from django.db.models import Prefetch

        return super().get_queryset(request).prefetch_related(Prefetch("user__avatar_assets", queryset=orm.UserAvatarAsset.objects.order_by("-created_at")))

    def nz_stats(self, request):
        k = orm.UserRole.objects.aggregate(all=Count("id"), users=Count("user_id", distinct=True), scoped=Count("id", filter=Q(store_id__isnull=False)), last=Max("created_at"))
        return [
            ui.stat_card("Biriktirishlar", k["all"], "#9333ea", "fa-id-badge", f"oxirgisi {ui.ago(k['last'])}" if k["last"] else ""),
            ui.stat_card("Foydalanuvchilar", k["users"], "#2563eb", "fa-users", "kamida bitta rol"),
            ui.stat_card("Do'kon doirasida", k["scoped"], "#ea580c", "fa-store", "faqat bitta do'konda"),
            ui.stat_card("Rollar", orm.Role.objects.count(), "#6366f1", "fa-user-shield", "", reverse("admin:identity_role_changelist")),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.UserRole.objects.values_list("role_id").annotate(n=Count("id")))
        return ui.tabs_for(request, "role__id__exact", [("", "Hammasi", sum(counts.values()))] +
                           [(str(r.pk), r.name, counts.get(r.pk, 0)) for r in orm.Role.objects.order_by("name")])

    def nz_hero_actions(self, request):
        return [{"label": "Rol biriktirish", "url": reverse("admin:identity_userrole_add"), "icon": "fa-plus", "primary": True}] if self.has_add_permission(request) else []

    def nz_prepare(self, request, objs):
        self._stores = _store_names([r.store_id for r in objs])
        self._perm_n = dict(orm.RolePermission.objects.filter(role_id__in={r.role_id for r in objs}).values("role_id").annotate(n=Count("id")).values_list("role_id", "n"))

    def nz_href(self, obj):
        return reverse("admin:identity_user_change", args=[obj.user_id])

    def nz_row(self, r):
        return [
            ui.user_cell(r.user), ui.chip(r.role.name, "#6366f1", "fa-user-shield"),
            ui.chip(self._stores.get(r.store_id, "do'kon"), "#ea580c", "fa-store") if r.store_id else ui.muted("barcha do'konlar"),
            format_html("<b>{}</b>", self._perm_n.get(r.role_id, 0)), ui.local(r.created_at, "%d.%m.%Y"),
        ]

    def form_hero(self, request, obj):
        return {"title": "Rol biriktirish", "subtitle": "Foydalanuvchini qidirib toping, rolni va (kerak bo'lsa) do'konni tanlang"}

    def save_model(self, request, obj, form, change):
        """Through AssignRole (duplicate check, event, permission cache) -- never a raw save."""
        from apps.identity.infrastructure.composition import build_assign_role

        store = form.cleaned_data.get("store") or None
        saved = build_assign_role().execute(user_id=obj.user_id, role_code=obj.role.code, store_id=uuid.UUID(store) if store else None)
        obj.pk = saved.id

    def add_view(self, request, form_url="", extra_context=None):
        try:
            return super().add_view(request, form_url, extra_context)
        except DomainException as exc:
            messages.error(request, f"Rol biriktirilmadi: {exc}")
            return HttpResponseRedirect(request.path)

    def response_add(self, request, obj, post_url_continue=None):
        messages.success(request, "Rol biriktirildi.")
        return HttpResponseRedirect(reverse("admin:identity_userrole_changelist"))

    @admin.action(description="Tanlangan rollarni olib tashlash", permissions=["add"])
    def remove_selected(self, request, queryset):
        from apps.identity.infrastructure.composition import build_remove_role

        service, n = build_remove_role(), 0
        for r in list(queryset):
            service.execute(r.pk, actor_id=_actor(request))
            n += 1
        messages.success(request, f"{n} ta rol olib tashlandi.")
