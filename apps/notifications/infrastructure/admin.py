"""
Dashboard → Bildirishnomalar: the history of every notification customers received (read-only, with "mark read" /
"hide from inbox" bulk actions) and of every broadcast (reach, read rate, Telegram delivery, per-language texts).
New messages are written in the composer (broadcast_view.py, "Xabar yuborish"), never in a raw add form.

Both lists use the shared premium layout (platform.premium_admin). Notification preferences, deliveries and the
outbox stay off the dashboard: backend-managed state nobody edits by hand.
"""
from __future__ import annotations

from django.contrib import admin
from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.notifications.infrastructure import models as orm
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat

KIND_META = {
    # kind: (label, font-awesome icon, colour)
    "order_confirmed": ("Buyurtma tasdiqlandi", "fa-circle-check", "#16a34a"), "order_processing": ("Buyurtma yig'ilmoqda", "fa-box", "#0ea5e9"),
    "order_shipped": ("Buyurtma yo'lda", "fa-truck-fast", "#2563eb"), "order_delivered": ("Buyurtma yetkazildi", "fa-house-circle-check", "#16a34a"),
    "order_cancelled": ("Buyurtma bekor qilindi", "fa-circle-xmark", "#e11d48"), "order_returned": ("Buyurtma qaytarildi", "fa-rotate-left", "#f59e0b"),
    "order_failed": ("To'lov o'tmadi", "fa-triangle-exclamation", "#e11d48"),
    "coins_earned": ("Coin (cashback)", "fa-coins", "#f59e0b"), "coins_earned_pos": ("Coin (do'kon)", "fa-coins", "#f59e0b"),
    "coins_granted": ("Coin sovg'a", "fa-gift", "#16a34a"), "coins_deducted": ("Coin yechildi", "fa-coins", "#64748b"),
    "coins_expiring": ("Coin kuyadi", "fa-hourglass-half", "#f59e0b"), "tier_up": ("Yangi daraja", "fa-trophy", "#8b5cf6"), "tier_at_risk": ("Daraja xavf ostida", "fa-shield-halved", "#f59e0b"),
    "payment_received": ("To'lov qabul qilindi", "fa-circle-check", "#10b981"), "payment_refunded": ("To'lov qaytarildi", "fa-rotate-left", "#f59e0b"),
    "payment_reminder": ("To'lov eslatmasi", "fa-credit-card", "#f59e0b"), "order_payment_expired": ("To'lanmagan — bekor", "fa-circle-xmark", "#e11d48"),
    "tier_changed": ("Daraja o'zgardi", "fa-crown", "#8b5cf6"), "referral_bonus": ("Taklif bonusi", "fa-user-group", "#16a34a"),
    "welcome_bonus": ("Xush kelibsiz bonusi", "fa-gift", "#16a34a"), "promo_code": ("Promokod", "fa-ticket", "#2563eb"),
    "campaign": ("Aksiya", "fa-wand-magic-sparkles", "#8b5cf6"), "welcome": ("Xush kelibsiz", "fa-hand-sparkles", "#0d9488"),
    "announcement": ("E'lon", "fa-bullhorn", "#db2777"), "shift_closed": ("Smena yopildi", "fa-cash-register", "#64748b"),
    "chat_message": ("Chat xabari", "fa-comments", "#4f46e5"),
}
STATUS_META = {"unseen": ("Yangi", "#f59e0b"), "seen": ("Ko'rildi", "#0ea5e9"), "read": ("O'qildi", "#16a34a"), "cancelled": ("Bekor", "#64748b")}
AUDIENCE_LABEL = {"all": "Barcha mijozlar", "active": "Faol mijozlar", "buyers": "Xarid qilganlar", "telegram": "Telegram ulanganlar", "new": "Yangi mijozlar", "tier": "Loyalty darajasi", "segment": "Segment", "phone": "Bitta mijoz"}


LOYALTY_KINDS = ("coins_earned", "coins_earned_pos", "coins_granted", "coins_deducted", "coins_expiring", "tier_up", "tier_changed", "tier_at_risk", "referral_bonus", "welcome_bonus")


def _titled(base, title):
    return type(f"{base.__name__}_{title}", (base,), {"__init__": lambda self, *a, **k: (base.__init__(self, *a, **k), setattr(self, "title", title))[0]})


class KindFilter(admin.SimpleListFilter):
    title = "Turi"
    parameter_name = "kind"

    def lookups(self, request, model_admin):
        return [
            ("orders", "Buyurtmalar"), ("loyalty", "Coin va darajalar"), ("marketing", "Promokod va aksiyalar"),
            ("announcement", "E'lonlar (dashboard)"), ("welcome", "Xush kelibsiz"),
        ]

    def queryset(self, request, qs):
        v = self.value()
        if v == "orders":
            return qs.filter(kind__startswith="order_")
        if v == "loyalty":
            return qs.filter(kind__in=LOYALTY_KINDS)
        if v == "marketing":
            return qs.filter(kind__in=["promo_code", "campaign"])
        if v in ("announcement", "welcome"):
            return qs.filter(kind=v)
        return qs


class NotificationStatusFilter(admin.SimpleListFilter):
    title = "Holat"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [("unread", "O'qilmagan"), ("read", "O'qilgan"), ("cancelled", "Bekor qilingan")]

    def queryset(self, request, qs):
        v = self.value()
        if v == "unread":
            return qs.filter(status__in=["unseen", "seen"])
        if v in ("read", "cancelled"):
            return qs.filter(status=v)
        return qs


class TelegramDeliveryFilter(admin.SimpleListFilter):
    title = "Telegram"
    parameter_name = "tg"

    def lookups(self, request, model_admin):
        return [("sent", "Yuborilgan"), ("failed", "Xato"), ("none", "Yuborilmagan")]

    def queryset(self, request, qs):
        v = self.value()
        if v in ("sent", "failed"):
            return qs.filter(deliveries__channel="telegram", deliveries__status=v)
        if v == "none":
            return qs.exclude(deliveries__channel="telegram")
        return qs


class PriorityFilter(admin.SimpleListFilter):
    title = "Muhimlik"
    parameter_name = "prio"

    def lookups(self, request, model_admin):
        return [("high", "Muhim"), ("normal", "Oddiy"), ("low", "Past")]

    def queryset(self, request, qs):
        v = self.value()
        if v == "high":
            return qs.filter(priority__in=["high", "urgent"])
        return qs.filter(priority=v) if v else qs


class _DateFilter(admin.DateFieldListFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = "Sana"


def _users(ids) -> dict:
    from django.db.models import Prefetch

    from apps.identity.infrastructure.models import User, UserAvatarAsset

    return {u.id: u for u in User._base_manager.filter(id__in=list(ids)).prefetch_related(Prefetch("avatar_assets", queryset=UserAvatarAsset.objects.order_by("-created_at")))}


def _kind_cell(kind: str, title: str, body: str, template_key: str = "") -> str:
    label, icon, tone = KIND_META.get(kind, (template_key or "Xabar", "fa-bell", "#64748b"))
    return format_html('<span class="ntf-msg" style="--t:{}"><span class="ic"><i class="fas {}" aria-hidden="true"></i></span><span><b>{}</b><small>{}</small></span></span>', tone, icon, title, body)


def _telegram_cell(delivery) -> str:
    if delivery is None:
        return ui.muted()
    if delivery.status == "failed":
        return format_html('<span class="nzi-chip" style="--t:#e11d48" title="{}"><i class="fab fa-telegram" aria-hidden="true"></i> Xato</span>', delivery.failure_reason or "")
    return mark_safe('<span class="nzi-chip" style="--t:#0ea5e9"><i class="fab fa-telegram" aria-hidden="true"></i> Yuborildi</span>')


def _category_tabs(request):
    counts: dict = {}
    for kind, n in orm.NotificationModel.objects.values_list("kind").annotate(n=Count("id")):
        cat = "orders" if (kind or "").startswith("order_") else "loyalty" if kind in LOYALTY_KINDS else "marketing" if kind in ("promo_code", "campaign") else kind if kind in ("announcement", "welcome") else "other"
        counts[cat] = counts.get(cat, 0) + n
    labels = [("orders", "Buyurtmalar", "#2563eb"), ("loyalty", "Coin va darajalar", "#f59e0b"), ("marketing", "Promokod va aksiyalar", "#8b5cf6"),
              ("announcement", "E'lonlar", "#db2777"), ("welcome", "Xush kelibsiz", "#0d9488")]
    return ui.tabs_for(request, "kind", [("", "Hammasi", sum(counts.values()))] + [(k, label, counts[k]) for k, label, _c in labels if counts.get(k)],
                       {k: c for k, _l, c in labels})


@admin.register(orm.NotificationModel)
class NotificationAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    """Bildirishnomalar: every notification any customer received (read-only history). New messages are written in the composer (Xabar yuborish)."""

    list_display = ("title", "created_at")
    list_filter = (KindFilter, NotificationStatusFilter, TelegramDeliveryFilter, PriorityFilter, ("created_at", _DateFilter))
    search_fields = ("title", "body", "link")
    list_per_page = 40
    ordering = ("-created_at",)
    actions = ("mark_read", "cancel_selected")
    readonly_fields = ("message_panel", "delivery_panel")
    fieldsets = (("Xabar", {"classes": ("nzi-panel",), "fields": ("message_panel",)}), ("Yetkazish", {"classes": ("nzi-panel",), "fields": ("delivery_panel",)}))

    nz_icon, nz_tone, nz_title = "fa-bell", "#2563eb", "Bildirishnomalar"
    nz_subtitle = "Mijozlarga yuborilgan har bir xabar: buyurtma holati, coin, promokod va e'lonlar — kim oldi, o'qidimi va Telegram'ga yetib bordimi."
    nz_columns = (("Xabar", ""), ("Mijoz", ""), ("Turi", ""), ("Telegram", ""), ("Vaqt", ""), ("Holat", "r"))
    nz_grid = "minmax(260px,2.6fr) minmax(200px,1.5fr) minmax(150px,1.1fr) 110px 120px 110px"
    nz_search = "Sarlavha, matn yoki havola…"
    nz_empty = ("Hali bildirishnoma yo'q", "Buyurtma holati o'zgarganda yoki e'lon yuborilganda shu yerda paydo bo'ladi.")
    nz_sorts = (("Yangilari", ""), ("Eskilari", "2"))
    nz_css = ("admin/css/nutrizone-notify.css",)
    hero_icon, hero_tone = "fa-bell", "#2563eb"

    def has_add_permission(self, request) -> bool:
        return False  # the composer (nz_notify_send) replaces the raw add form

    def has_change_permission(self, request, obj=None) -> bool:
        return False  # history is read-only; the bulk actions below don't need the change form

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("deliveries")

    def nz_stats(self, request):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        k = orm.NotificationModel.objects.aggregate(
            total=Count("id"), today=Count("id", filter=Q(created_at__gte=today)), week=Count("id", filter=Q(created_at__gte=timezone.now() - timedelta(days=7))),
            unread=Count("id", filter=Q(status__in=["unseen", "seen"])), read=Count("id", filter=Q(status="read")),
        )
        tg = orm.NotificationDeliveryModel.objects.filter(channel="telegram").aggregate(sent=Count("id", filter=Q(status="sent")), failed=Count("id", filter=Q(status="failed")))
        rate = round(k["read"] * 100 / k["total"]) if k["total"] else 0
        return [
            ui.stat_card("Jami", k["total"], "#2563eb", "fa-bell", f"7 kunda {k['week']} · bugun {k['today']}"),
            ui.stat_card("O'qilmagan", k["unread"], "#f59e0b", "fa-envelope", "mijozlar hali ochmagan", "?state=unread"),
            ui.stat_card("O'qilish darajasi", f"{rate}%", "#8b5cf6", "fa-envelope-open", f"{k['read']} ta o'qilgan", "?state=read"),
            ui.stat_card("Telegram", tg["sent"], "#0ea5e9", "fa-paper-plane", f"{tg['failed']} ta xato" if tg["failed"] else "hammasi yetkazildi", "?tg=failed" if tg["failed"] else "?tg=sent"),
            ui.stat_card("E'lonlar", orm.NotificationBroadcast.objects.count(), "#db2777", "fa-bullhorn", "ommaviy yuborilgan", reverse("admin:notifications_notificationbroadcast_changelist")),
        ]

    def nz_tabs(self, request):
        return _category_tabs(request)

    def nz_hero_actions(self, request):
        out = [{"label": "Yuborilgan xabarlar", "url": reverse("admin:notifications_notificationbroadcast_changelist"), "icon": "fa-clock-rotate-left"}]
        if request.user.has_perm("notifications.add_notificationbroadcast"):
            out.append({"label": "Xabar yuborish", "url": reverse("admin:nz_notify_send"), "icon": "fa-paper-plane", "primary": True})
        return out

    def nz_prepare(self, request, objs):
        self._u = _users({o.recipient_id for o in objs})

    def nz_row(self, o):
        label, icon, tone = KIND_META.get(o.kind, (o.template_key or "Boshqa", "fa-bell", "#64748b"))
        st_label, st_tone = STATUS_META.get(o.status, (o.status, "#64748b"))
        prio = format_html(' <span class="nzi-chip" style="--t:#e11d48">{}</span>', "muhim") if o.priority in ("high", "urgent") else ""
        return [
            format_html("{}{}", _kind_cell(o.kind, o.title, o.body, o.template_key or ""), prio), ui.user_cell(self._u.get(o.recipient_id)), ui.chip(label, tone, icon),
            _telegram_cell(next((d for d in o.deliveries.all() if d.channel == "telegram"), None)),
            format_html('<span title="{}">{}</span><small>{}</small>', ui.local(o.created_at), ui.ago(o.created_at), ui.local(o.created_at, "%d.%m.%Y")),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>{}', st_tone, st_label, format_html("<small>{}</small>", ui.local(o.read_at)) if o.read_at else ""),
        ]

    def form_hero(self, request, obj):
        label, icon, tone = KIND_META.get(obj.kind, (obj.template_key or "Xabar", "fa-bell", "#64748b"))
        u = _users([obj.recipient_id]).get(obj.recipient_id)
        st_label, st_tone = STATUS_META.get(obj.status, (obj.status, "#64748b"))
        return {
            "title": obj.title, "subtitle": f"{(u.full_name or u.phone_number) if u else 'mijoz topilmadi'} · {ui.local(obj.created_at)}", "icon": icon, "tone": tone,
            "chips": [ui.chip(label, tone, icon), format_html('<span class="nzi-pill" style="--t:{}">{}</span>', st_tone, st_label)],
            "links": [l for l in ({"label": "Mijoz", "url": reverse("admin:identity_user_change", args=[u.pk]), "icon": "fa-user"} if u else None,
                                  {"label": "E'lon", "url": reverse("admin:notifications_notificationbroadcast_change", args=[obj.broadcast_id]), "icon": "fa-bullhorn"} if obj.broadcast_id else None) if l],
        }

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, {**(extra_context or {}), "show_save": False, "show_save_and_continue": False, "show_delete": False})

    @admin.display(description="")
    def message_panel(self, obj):
        texts = obj.i18n or {}
        langs = format_html_join("", '<div class="ntf-lang"><span>{}</span><b>{}</b><p>{}</p></div>', (
            (code.upper(), (texts.get(code) or {}).get("title", ""), (texts.get(code) or {}).get("body", "")) for code in ("uz", "ru", "en") if texts.get(code)))
        link = format_html('<p class="nzi-help"><i class="fas fa-link" aria-hidden="true"></i> {}</p>', obj.link) if obj.link else ""
        return format_html('<div class="nzi-panel-body">{}{}</div>', langs or format_html('<div class="ntf-lang"><b>{}</b><p>{}</p></div>', obj.title, obj.body), link)

    @admin.display(description="")
    def delivery_panel(self, obj):
        rows = [("Ilova ichida", "fa-bell", "#2563eb", f"yaratildi {ui.local(obj.created_at)}", ("ko'rildi " + ui.local(obj.seen_at)) if obj.seen_at else "", ("o'qildi " + ui.local(obj.read_at)) if obj.read_at else "")]
        for d in obj.deliveries.all():
            rows.append((d.channel.title(), "fa-paper-plane", "#e11d48" if d.status == "failed" else "#0ea5e9", f"{d.status} · {ui.local(d.attempted_at)}", d.failure_reason or "", ""))
        items = format_html_join("", '<li><span class="nzi-ico" style="--t:{}"><i class="fas {}" aria-hidden="true"></i></span><span><b>{}</b><small>{} {} {}</small></span></li>', (
            (c, i, n, a, b, x) for n, i, c, a, b, x in rows))
        return format_html('<div class="nzi-panel-body"><ul class="nzi-items">{}</ul></div>', items)

    @admin.action(description="O'qilgan deb belgilash")
    def mark_read(self, request, queryset):
        from django.utils import timezone

        n = queryset.exclude(status="read").update(status="read", read_at=timezone.now())
        self.message_user(request, f"{n} ta bildirishnoma o'qilgan deb belgilandi.")

    @admin.action(description="Mijozlardan yashirish (bekor qilish)")
    def cancel_selected(self, request, queryset):
        n = queryset.exclude(status="cancelled").update(status="cancelled")
        self.message_user(request, f"{n} ta bildirishnoma mijozlarning inboxidan olib tashlandi.")


BROADCAST_STATUS = {"queued": ("Navbatda", "#64748b"), "sending": ("Yuborilmoqda", "#f59e0b"), "sent": ("Yuborildi", "#16a34a"), "failed": ("Xato", "#e11d48")}


def _channels(b) -> str:
    parts = []
    if b.send_in_app:
        parts.append(ui.chip("Ilova", "#2563eb", "fa-bell"))
    if b.send_telegram:
        parts.append(format_html('<span class="nzi-chip" style="--t:#0ea5e9"><i class="fab fa-telegram" aria-hidden="true"></i> {}</span>', "Telegram"))
    return format_html_join("", "{}", ((p,) for p in parts)) if parts else ui.muted()


def _read_bar(read: int, total: int) -> str:
    pct = round(read * 100 / total) if total else 0
    return format_html('<span class="ntf-read"><b>{}%</b><small>{} / {}</small><span class="ntf-bar"><span style="width:{}%"></span></span></span>', pct, read, total, pct)


@admin.register(orm.NotificationBroadcast)
class NotificationBroadcastAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    """Yuborilgan xabarlar: every dashboard announcement (and automatic promo / campaign announcements) with reach, read rate and Telegram delivery."""

    list_display = ("title", "created_at")
    list_filter = (("audience", _titled(admin.ChoicesFieldListFilter, "Auditoriya")),)
    search_fields = ("title", "body", "created_by")
    list_per_page = 30
    ordering = ("-created_at",)
    change_form_template = "admin/notifications/notificationbroadcast/change_form.html"
    readonly_fields = ("texts_panel", "recipients_panel")
    fieldsets = (("Matn", {"classes": ("nzi-panel",), "fields": ("texts_panel",)}), ("Kimlar oldi", {"classes": ("nzi-panel",), "fields": ("recipients_panel",)}))

    nz_icon, nz_tone, nz_title = "fa-bullhorn", "#db2777", "Yuborilgan xabarlar"
    nz_subtitle = "Dashboard'dan yuborilgan e'lonlar va avtomatik promokod / aksiya xabarlari: qancha mijozga yetdi, nechtasi o'qidi, Telegram natijasi."
    nz_columns = (("Xabar", ""), ("Auditoriya", ""), ("Kanallar", ""), ("Qamrov", "r"), ("O'qilgan", ""), ("Vaqt", ""), ("Holat", "r"))
    nz_grid = "minmax(260px,2.4fr) minmax(150px,1.2fr) 170px 120px minmax(140px,1fr) 130px 120px"
    nz_search = "Sarlavha, matn yoki kim yuborgan…"
    nz_empty = ("Hali xabar yuborilmagan", "«Xabar yuborish» orqali mijozlarga e'lon, aksiya yoki yangilik yuboring.")
    nz_css = ("admin/css/nutrizone-notify.css",)
    hero_icon, hero_tone = "fa-bullhorn", "#db2777"

    def has_add_permission(self, request) -> bool:
        return False  # created from the composer

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(read_n=Count("notifications", filter=Q(notifications__status="read")))

    def nz_stats(self, request):
        k = orm.NotificationBroadcast.objects.aggregate(n=Count("id"), reach=Sum("recipients"), tg=Sum("telegram_sent"), tg_failed=Sum("telegram_failed"),
                                                        manual=Count("id", filter=Q(source="dashboard")))
        read = orm.NotificationModel.objects.filter(broadcast__isnull=False, status="read").count()
        return [
            ui.stat_card("Xabarlar", k["n"], "#db2777", "fa-bullhorn", f"{k['manual']} tasi qo'lda, {k['n'] - k['manual']} tasi avtomatik", "?source=dashboard"),
            ui.stat_card("Umumiy qamrov", k["reach"] or 0, "#2563eb", "fa-users", "yetkazilgan bildirishnomalar"),
            ui.stat_card("O'qilish darajasi", f"{round(read * 100 / k['reach']) if k['reach'] else 0}%", "#8b5cf6", "fa-envelope-open", f"{read} ta o'qilgan"),
            ui.stat_card("Telegram", k["tg"] or 0, "#0ea5e9", "fa-paper-plane", f"{k['tg_failed']} ta xato" if k["tg_failed"] else "xatosiz"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.NotificationBroadcast.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values()))] + [(k, v[0], counts[k]) for k, v in BROADCAST_STATUS.items() if counts.get(k)],
                           {k: v[1] for k, v in BROADCAST_STATUS.items()})

    def lookup_allowed(self, lookup, value, request=None):
        return lookup in ("status__exact", "source") or super().lookup_allowed(lookup, value, request)

    def nz_hero_actions(self, request):
        out = [{"label": "Barcha bildirishnomalar", "url": reverse("admin:notifications_notificationmodel_changelist"), "icon": "fa-bell"}]
        if request.user.has_perm("notifications.add_notificationbroadcast"):
            out.append({"label": "Yangi xabar", "url": reverse("admin:nz_notify_send"), "icon": "fa-paper-plane", "primary": True})
        return out

    def nz_row(self, b):
        st_label, st_tone = BROADCAST_STATUS.get(b.status, (b.status, "#64748b"))
        auto = format_html(' <span class="nzi-chip" style="--t:#64748b">{}</span>', "avto") if b.source != "dashboard" else ""
        audience = AUDIENCE_LABEL.get(b.audience, b.audience)
        tg = format_html("<small>Telegram {}{}</small>", b.telegram_sent, f" · xato {b.telegram_failed}" if b.telegram_failed else "") if b.send_telegram else ""
        return [
            format_html("{}{}", _kind_cell(b.kind, b.title, b.body), auto), format_html("{}<small>{}</small>", audience, b.target or ""), _channels(b),
            format_html("<b>{}</b> <small>mijoz</small>{}", b.recipients, tg), _read_bar(getattr(b, "read_n", 0), b.recipients),
            format_html('<span title="{}">{}</span><small>{}</small>', ui.local(b.created_at), ui.ago(b.created_at), b.created_by or ""),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>', st_tone, st_label),
        ]

    def form_hero(self, request, obj):
        st_label, st_tone = BROADCAST_STATUS.get(obj.status, (obj.status, "#64748b"))
        read = obj.notifications.filter(status="read").count()
        took = f"{max(int((obj.finished_at - obj.created_at).total_seconds()), 0)} soniyada tugadi" if obj.finished_at else "yuborilmoqda…"
        return {
            "title": obj.title, "subtitle": f"{ui.local(obj.created_at)} · {obj.created_by if obj.created_by and obj.created_by != 'auto' else 'Avtomatik (promokod / aksiya)'}",
            "icon": "fa-bullhorn", "tone": st_tone,
            "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', st_tone, st_label), _channels(obj),
                      ui.chip(AUDIENCE_LABEL.get(obj.audience, obj.audience) + (f": {obj.target}" if obj.target else ""), "#64748b", "fa-users")],
            "stats": [
                hero_stat("Qamrov", obj.recipients, "#2563eb", took, "fa-users"),
                hero_stat("O'qildi", f"{round(read * 100 / obj.recipients) if obj.recipients else 0}%", "#8b5cf6", f"{read} ta mijoz", "fa-envelope-open"),
                hero_stat("Telegram", obj.telegram_sent if obj.send_telegram else "—", "#0ea5e9", f"{obj.telegram_failed} ta xato" if obj.telegram_failed else "yoqilmagan" if not obj.send_telegram else "xatosiz", "fa-paper-plane"),
            ],
            "links": [{"label": "Nusxa olib yangi xabar", "url": reverse("admin:nz_notify_send") + f"?from={obj.pk}", "icon": "fa-copy", "primary": True},
                      {"label": "Yangi xabar", "url": reverse("admin:nz_notify_send"), "icon": "fa-paper-plane"}],
        }

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        obj = self.get_object(request, object_id) if object_id else None
        refresh = obj is not None and obj.status in ("queued", "sending")
        return super().changeform_view(request, object_id, form_url, {**(extra_context or {}), "ntf_refresh": refresh, "show_save": False, "show_save_and_continue": False, "show_delete": False})

    @admin.display(description="")
    def texts_panel(self, obj):
        texts = obj.i18n or {"uz": {"title": obj.title, "body": obj.body}}
        langs = format_html_join("", '<div class="ntf-lang"><span>{}</span><b>{}</b><p>{}</p></div>', (
            (code.upper(), (texts.get(code) or {}).get("title", ""), (texts.get(code) or {}).get("body", "")) for code in ("uz", "ru", "en") if texts.get(code)))
        link = format_html('<p class="nzi-help"><i class="fas fa-link" aria-hidden="true"></i> {}</p>', obj.link) if obj.link else ""
        return format_html('<div class="nzi-panel-body"><div class="ntf-langs">{}</div>{}</div>', langs, link)

    @admin.display(description="")
    def recipients_panel(self, obj):
        rows = list(obj.notifications.prefetch_related("deliveries").order_by(F("read_at").desc(nulls_last=True), "-created_at")[:12])
        users = _users({n.recipient_id for n in rows})
        items = format_html_join("", '<li><span>{}</span><span class="nzi-when">{}{}</span></li>', (
            (ui.user_cell(users.get(n.recipient_id)), format_html('<span class="nzi-pill" style="--t:{}">{}</span>', *STATUS_META.get(n.status, (n.status, "#64748b"))[::-1]),
             _telegram_cell(next((d for d in n.deliveries.all() if d.channel == "telegram"), None))) for n in rows))
        more = obj.notifications.count() - len(rows)
        tail = format_html('<a class="nzi-more" href="{}?q={}">yana {} ta →</a>', reverse("admin:notifications_notificationmodel_changelist"), obj.title[:40], more) if more > 0 else ""
        return format_html('<div class="nzi-panel-body"><ul class="nzi-items">{}</ul>{}</div>', items, tail) if rows else format_html('<p class="nzi-none">{}</p>', "Hali hech kimga yetkazilmagan.")


# Real, product-required simplification: removed from Dashboard -- backend-managed opt-out state (disabled channel/type combinations) an operator never edits by hand. See this module's own docstring.
# @admin.register(orm.NotificationPreferenceModel)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user_id", "disabled_combination_count")
    search_fields = ("user_id",)
    readonly_fields = ("id", "created_at", "updated_at", "disabled_combinations")

    def disabled_combination_count(self, obj: orm.NotificationPreferenceModel) -> int:
        return len(obj.disabled_combinations)


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (event-log) data an admin never creates or edits by hand.
# @admin.register(orm.NotificationOutboxEvent)
class NotificationOutboxEventAdmin(admin.ModelAdmin):
    """Read-only -- append-only/Outbox tables are never editable in admin, per MIC §9."""

    list_display = ("event_type", "event_version", "created_at", "published_at", "publish_attempts")
    list_filter = ("event_type",)
    readonly_fields = [f.name for f in orm.NotificationOutboxEvent._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
