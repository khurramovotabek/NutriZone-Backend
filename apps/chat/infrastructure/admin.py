"""
Dashboard → Chat: the conversation and message registers (premium lists). Answering happens in the Chat markazi
desk (apps/platform/infrastructure/chat_view.py) -- every row opens there. Close / reopen / archive run through the
chat Application Services; messages are the customers' own words and are never edited or deleted from here.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.chat.infrastructure import models as orm
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumListMixin
from common.exceptions import DomainException

STATUS = {"open": ("Ochiq", "#16a34a"), "closed": ("Yopilgan", "#64748b"), "archived": ("Arxivda", "#94a3b8")}
TYPE = {"customer_support": ("Qo'llab-quvvatlash", "#4f46e5", "fa-headset"), "customer_sales": ("Do'kon suhbati", "#ea580c", "fa-store"),
        "internal_support": ("Ichki", "#64748b", "fa-building")}


def _desk(conversation_id) -> str:
    return reverse("admin:nz_chat_admin") + f"?c={conversation_id}"


def _titled(base, title):
    return type(f"{base.__name__}_{title}", (base,), {"__init__": lambda self, *a, **k: (base.__init__(self, *a, **k), setattr(self, "title", title))[0]})


class WaitingFilter(admin.SimpleListFilter):
    title = "Javob"
    parameter_name = "reply"

    def lookups(self, request, model_admin):
        return [("waiting", "Javob kutmoqda"), ("unassigned", "Hech kimga biriktirilmagan")]

    def queryset(self, request, queryset):
        if self.value() == "unassigned":
            return queryset.filter(assigned_operator_id__isnull=True).exclude(conversation_type="customer_sales")
        if self.value() == "waiting":
            from apps.platform.infrastructure.chat_view import _waiting_ids

            return queryset.filter(id__in=_waiting_ids())
        return queryset


@admin.register(orm.ConversationModel)
class ConversationAdmin(ExcelExportMixin, PremiumListMixin, admin.ModelAdmin):
    """Suhbatlar: every chat -- customer, type, last message, unread, who handles it; opens in the Chat markazi."""
    excel_title = "Suhbatlar"
    excel_columns = [Col("Turi", "conversation_type", 16), Col("Holat", "status", 12), Col("Operator", lambda c: c.x_operator[0], 20),
                     Col("Oxirgi faollik", "last_activity_at", 17), Col("Yaratilgan", "created_at", 17)]

    def excel_prepare(self, objs):
        who = xl.people(c.assigned_operator_id for c in objs)
        for c in objs:
            c.x_operator = who.get(c.assigned_operator_id, ("", ""))


    list_display = ("last_activity_at", "created_at")
    list_filter = (WaitingFilter, ("conversation_type", _titled(admin.ChoicesFieldListFilter, "Turi")), ("last_activity_at", _titled(admin.DateFieldListFilter, "Oxirgi faollik")))
    ordering = ("-last_activity_at",)
    list_per_page = 30
    actions = ["close_selected", "reopen_selected", "archive_selected"]

    nz_icon, nz_tone, nz_title = "fa-comments", "#4f46e5", "Suhbatlar"
    nz_subtitle = "Mijozlar bilan barcha suhbatlar: kim yozdi, oxirgi xabar, o'qilmaganlar va kim javob beryapti. Suhbatni bosing — Chat markazida ochiladi."
    nz_columns = (("Mijoz", ""), ("Turi", ""), ("Oxirgi xabar", ""), ("Xabarlar", "r"), ("Operator", ""), ("Faollik", ""), ("Holat", "r"))
    nz_grid = "minmax(210px,1.6fr) minmax(150px,1.1fr) minmax(220px,2fr) 90px minmax(120px,1fr) 110px 120px"
    nz_empty = ("Hali suhbat yo'q", "Mijoz saytda «Yordam» chatini ochganda yoki do'konga yozganda shu yerda paydo bo'ladi.")
    nz_sorts = (("Oxirgi faollik", ""), ("Yangi ochilganlar", "-2"))
    nz_css = ("admin/css/nutrizone-chat-desk.css",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from django.http import HttpResponseRedirect

        return HttpResponseRedirect(_desk(object_id))

    def nz_href(self, obj):
        return _desk(obj.pk)

    def nz_stats(self, request):
        from apps.platform.infrastructure.chat_view import _first_reply_minutes, _waiting_ids

        day = timezone.now() - timedelta(days=1)
        k = orm.ConversationModel.objects.aggregate(open=Count("id", filter=Q(status="open")), stores=Count("id", filter=Q(status="open", conversation_type="customer_sales")),
                                                    unassigned=Count("id", filter=Q(status="open", assigned_operator_id__isnull=True) & ~Q(conversation_type="customer_sales")))
        waiting = orm.ConversationModel.objects.filter(id__in=_waiting_ids()).exclude(conversation_type="customer_sales").count()
        first = _first_reply_minutes()
        return [
            ui.stat_card("Javob kutmoqda", waiting, "#d97706" if waiting else "#16a34a", "fa-hourglass-half", "qo'llab-quvvatlash, mijoz oxirgi yozgan" if waiting else "hammasiga javob berilgan", "?reply=waiting&conversation_type__exact=customer_support"),
            ui.stat_card("Ochiq suhbatlar", k["open"], "#4f46e5", "fa-comments", f"{k['unassigned']} tasi biriktirilmagan", "?status__exact=open"),
            ui.stat_card("Do'kon suhbatlari", k["stores"], "#ea580c", "fa-store", "do'kon egasi javob beradi", "?conversation_type__exact=customer_sales"),
            ui.stat_card("24 soatda xabarlar", orm.MessageModel.objects.filter(created_at__gte=day).count(), "#0891b2", "fa-message", "", reverse("admin:chat_messagemodel_changelist")),
            ui.stat_card("Birinchi javob", f"{first} daq" if first is not None else "—", "#16a34a", "fa-stopwatch", "mediana, 30 kun"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.ConversationModel.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values()))] + [(k, v[0], counts[k]) for k, v in STATUS.items() if counts.get(k)],
                           {k: v[1] for k, v in STATUS.items()})

    def nz_hero_actions(self, request):
        return [{"label": "Xabarlar", "url": reverse("admin:chat_messagemodel_changelist"), "icon": "fa-message"},
                {"label": "Chat markazi", "url": reverse("admin:nz_chat_admin"), "icon": "fa-headset", "primary": True}]

    def nz_prepare(self, request, objs):
        from apps.platform.infrastructure.chat_view import _preview, _staff_names, _stores, _users

        ids = [c.pk for c in objs]
        customers = dict(orm.ParticipantModel.objects.filter(conversation_id__in=ids, role="customer").values_list("conversation_id", "user_id"))
        self._u, self._s, self._staff = _users(customers.values()), _stores(c.store_id for c in objs), _staff_names()
        last = {m.conversation_id: m for m in orm.MessageModel.objects.filter(conversation_id__in=ids).order_by("conversation_id", "-created_at").distinct("conversation_id")}
        counts = dict(orm.MessageModel.objects.filter(conversation_id__in=ids).values("conversation_id").annotate(n=Count("id")).values_list("conversation_id", "n"))
        unread = dict(orm.MessageModel.objects.filter(conversation_id__in=ids, read_at__isnull=True, sender_id__in=list(customers.values())).values("conversation_id")
                      .annotate(n=Count("id")).values_list("conversation_id", "n"))
        for c in objs:
            m = last.get(c.pk)
            c._customer, c._last, c._count, c._unread = customers.get(c.pk), m, counts.get(c.pk, 0), unread.get(c.pk, 0)
            c._preview, c._waiting = _preview(m), m is not None and m.sender_id == customers.get(c.pk)

    def nz_row(self, c):
        label, color, icon = TYPE.get(c.conversation_type, (c.conversation_type, "#64748b", "fa-comments"))
        store = self._s.get(c.store_id)
        st_label, st_color = STATUS.get(c.status, (c.status, "#64748b"))
        operator = self._staff.get(c.assigned_operator_id, "") if c.assigned_operator_id else (f"{store.name} (do'kon)" if store else "")
        last = format_html('<span class="nzc-last{}">{}{}</span>', " wait" if c._waiting else "", format_html("<b>{}</b> ", c._unread) if c._unread else "", c._preview or "—")
        return [
            ui.user_cell(self._u.get(c._customer)), format_html("{}<small>{}</small>", ui.chip(label, color, icon), store.name if store else ""), last,
            format_html("<b>{}</b>", c._count), operator or ui.muted("biriktirilmagan"),
            format_html('<span title="{}">{}</span>', ui.local(c.last_activity_at), ui.ago(c.last_activity_at)) if c.last_activity_at else ui.muted(),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>{}', st_color, st_label, format_html("<small>{}</small>", "javob kutmoqda") if c._waiting and c.status == "open" else ""),
        ]

    def _bulk(self, request, queryset, builder, done_text):
        from apps.chat.infrastructure import composition
        from apps.platform.infrastructure.chat_view import _actor_id

        ok, skipped = 0, 0
        for c in queryset:
            try:
                getattr(composition, builder)(_actor_id(request)).execute(conversation_id=c.pk)
                ok += 1
            except DomainException:
                skipped += 1
        self.message_user(request, f"{ok} ta suhbat {done_text}." + (f" {skipped} tasi bu holatda o'zgartirib bo'lmaydi." if skipped else ""), messages.SUCCESS if ok else messages.WARNING)

    @admin.action(description="Yopish", permissions=["change"])
    def close_selected(self, request, queryset):
        self._bulk(request, queryset, "build_close_conversation", "yopildi")

    @admin.action(description="Qayta ochish", permissions=["change"])
    def reopen_selected(self, request, queryset):
        self._bulk(request, queryset, "build_reopen_conversation", "qayta ochildi")

    @admin.action(description="Arxivlash", permissions=["change"])
    def archive_selected(self, request, queryset):
        self._bulk(request, queryset, "build_archive_conversation", "arxivlandi")


class SenderFilter(admin.SimpleListFilter):
    title = "Kim yozgan"
    parameter_name = "from"

    def lookups(self, request, model_admin):
        return [("customer", "Mijoz"), ("staff", "Bizning xodim"), ("store", "Do'kon")]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        from apps.platform.infrastructure.chat_view import _staff_names

        customers = orm.ParticipantModel.objects.filter(role="customer").values("user_id")
        staff = list(_staff_names())
        if self.value() == "customer":
            return queryset.filter(sender_id__in=customers)
        if self.value() == "staff":
            return queryset.filter(sender_id__in=staff)
        return queryset.exclude(sender_id__in=customers).exclude(sender_id__in=staff)


@admin.register(orm.MessageModel)
class MessageAdmin(PremiumListMixin, admin.ModelAdmin):
    """Xabarlar: every message across all chats (read-only) -- who wrote it, what, read or not; opens its conversation in the Chat markazi."""

    list_display = ("created_at",)
    list_filter = (SenderFilter, ("message_type", _titled(admin.ChoicesFieldListFilter, "Turi")), ("created_at", _titled(admin.DateFieldListFilter, "Sana")))
    search_fields = ("content", "attachment_filename")
    ordering = ("-created_at",)
    list_per_page = 50

    nz_icon, nz_tone, nz_title = "fa-message", "#0891b2", "Xabarlar"
    nz_subtitle = "Barcha suhbatlardagi xabarlar: matn, rasm va stikerlar, kim yozgani va o'qilgani. Xabarni bosing — suhbat Chat markazida ochiladi."
    nz_columns = (("Kim yozgan", ""), ("Xabar", ""), ("Suhbat", ""), ("Vaqt", ""), ("Holat", "r"))
    nz_grid = "minmax(200px,1.4fr) minmax(280px,2.8fr) minmax(150px,1fr) 120px 120px"
    nz_search = "Xabar matni…"
    nz_empty = ("Hali xabar yo'q", "")
    nz_sorts = (("Yangilari", ""), ("Eskilari", "1"))
    nz_css = ("admin/css/nutrizone-chat-desk.css",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def nz_href(self, obj):
        return _desk(obj.conversation_id)

    def nz_stats(self, request):
        day = timezone.now() - timedelta(days=1)
        customers = orm.ParticipantModel.objects.filter(role="customer").values("user_id")
        k = orm.MessageModel.objects.aggregate(n=Count("id"), day=Count("id", filter=Q(created_at__gte=day)), media=Count("id", filter=Q(message_type="attachment")),
                                               stickers=Count("id", filter=Q(message_type="sticker")), last=Max("created_at"))
        unread = orm.MessageModel.objects.filter(read_at__isnull=True, sender_id__in=customers).count()
        return [
            ui.stat_card("Jami xabarlar", k["n"], "#0891b2", "fa-message", f"oxirgisi {ui.ago(k['last'])}" if k["last"] else ""),
            ui.stat_card("24 soatda", k["day"], "#4f46e5", "fa-bolt", ""),
            ui.stat_card("Mijozdan o'qilmagan", unread, "#d97706" if unread else "#16a34a", "fa-envelope", "javob kutayotganlar", "?from=customer"),
            ui.stat_card("Rasm / video", k["media"], "#db2777", "fa-image", f"{k['stickers']} ta stiker", "?message_type__exact=attachment"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.MessageModel.objects.values_list("message_type").annotate(n=Count("id")))
        labels = {"text": ("Matn", "#0891b2"), "attachment": ("Rasm / video", "#db2777"), "sticker": ("Stiker", "#d97706"), "system": ("Tizim", "#64748b")}
        return ui.tabs_for(request, "message_type__exact", [("", "Hammasi", sum(counts.values()))] + [(k, v[0], counts[k]) for k, v in labels.items() if counts.get(k)],
                           {k: v[1] for k, v in labels.items()})

    def nz_hero_actions(self, request):
        return [{"label": "Suhbatlar", "url": reverse("admin:chat_conversationmodel_changelist"), "icon": "fa-comments"},
                {"label": "Chat markazi", "url": reverse("admin:nz_chat_admin"), "icon": "fa-headset", "primary": True}]

    def nz_prepare(self, request, objs):
        from apps.platform.infrastructure.chat_view import _staff_names, _users

        conv_ids = {m.conversation_id for m in objs}
        self._roles = {(p.conversation_id, p.user_id): p.role for p in orm.ParticipantModel.objects.filter(conversation_id__in=conv_ids)}
        self._convs = {c.pk: c for c in orm.ConversationModel.objects.filter(pk__in=conv_ids)}
        self._u, self._staff = _users(m.sender_id for m in objs), _staff_names()

    def nz_row(self, m):
        from apps.chat.infrastructure.realtime import attachment_url
        from apps.platform.infrastructure.chat_view import STICKERS

        if m.sender_id in self._staff:
            who = format_html('<span class="nzi-user"><span class="nzi-av" style="--c:#4f46e5"><i class="fas fa-headset" aria-hidden="true"></i></span><span><b>{}</b><small>{}</small></span></span>', self._staff[m.sender_id], "xodim")
        elif self._roles.get((m.conversation_id, m.sender_id)) == "customer":
            who = ui.user_cell(self._u.get(m.sender_id))
        elif (self._convs.get(m.conversation_id) and self._convs[m.conversation_id].conversation_type == "customer_sales"):
            who = format_html('<span class="nzi-user"><span class="nzi-av" style="--c:#ea580c"><i class="fas fa-store" aria-hidden="true"></i></span><span><b>{}</b><small>{}</small></span></span>', "Do'kon", "do'kon egasi")
        else:
            who = format_html('<span class="nzi-user"><span class="nzi-av" style="--c:#4f46e5"><i class="fas fa-headset" aria-hidden="true"></i></span><span><b>{}</b><small>{}</small></span></span>', "Operator", "qo'llab-quvvatlash")
        if m.status == "deleted":
            body = ui.muted("xabar o'chirilgan")
        elif m.message_type == "sticker":
            emoji, label = STICKERS.get(m.content or "", ("🏷️", m.content or "Stiker"))
            body = format_html('<span class="nzc-row-sticker">{} <b>{}</b></span>', emoji, label)
        elif m.attachment_url:
            thumb = format_html('<img src="{}" alt="" class="nzc-row-img">', attachment_url(m.attachment_url, absolute=False)) if m.attachment_type == "image" else format_html('<i class="fas fa-film" aria-hidden="true"></i> {}', m.attachment_filename or "video")
            body = format_html('<span class="nzc-row-att">{}<span>{}</span></span>', thumb, m.content or "")
        else:
            body = format_html('<span class="nzc-row-text">{}</span>', m.content or "")
        conv = self._convs.get(m.conversation_id)
        label, color, icon = TYPE.get(conv.conversation_type if conv else "", ("Suhbat", "#64748b", "fa-comments"))
        read = format_html('<span class="nzi-pill" style="--t:#16a34a">{}</span>', "o'qildi") if m.read_at else format_html('<span class="nzi-pill" style="--t:#94a3b8">{}</span>', "yuborildi")
        return [who, body, ui.chip(label, color, icon),
                format_html('<span title="{}">{}</span><small>{}</small>', ui.local(m.created_at), ui.ago(m.created_at), ui.local(m.created_at, "%d.%m.%Y %H:%M")), read]


# ================================================================ desk settings, quick replies, ratings


from django import forms  # noqa: E402
from django.shortcuts import redirect  # noqa: E402

from apps.platform.infrastructure.premium_admin import PremiumFormMixin, hero_stat  # noqa: E402

WEEKDAYS = [(0, "Dushanba"), (1, "Seshanba"), (2, "Chorshanba"), (3, "Payshanba"), (4, "Juma"), (5, "Shanba"), (6, "Yakshanba")]


class ChatSettingsForm(forms.ModelForm):
    days = forms.MultipleChoiceField(label="Ish kunlari", choices=WEEKDAYS, widget=forms.CheckboxSelectMultiple(attrs={"data-no-switch": "1", "class": "nzc-day"}), required=False)
    reply_uz = forms.CharField(label="Avtomatik javob (o'zbekcha)", widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=600)
    reply_ru = forms.CharField(label="Avtomatik javob (ruscha)", widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=600)
    reply_en = forms.CharField(label="Avtomatik javob (inglizcha)", widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=600)

    class Meta:
        model = orm.ChatSettings
        fields = ("work_start", "work_end", "auto_reply_enabled", "alert_enabled", "alert_after_minutes", "alert_only_work_hours", "rating_enabled", "low_rating_alert",
                  "order_bot_enabled", "delivery_days")
        help_texts = {
            "work_start": "Toshkent vaqti bilan. Kechasi ishlasangiz (masalan 20:00–02:00) ham to'g'ri hisoblanadi.",
            "auto_reply_enabled": "Mijoz ish vaqtidan tashqari yozsa, bir marta (12 soatda ko'pi bilan bir marta) avtomatik javob oladi; javob oxirida ish vaqti ko'rsatiladi.",
            "alert_enabled": "Mijoz javob kutayotgan suhbat xodimlar Telegram kanaliga (buyurtmalar kanali) «Javob berish» tugmasi bilan yuboriladi.",
            "alert_after_minutes": "Mijozning oxirgi xabaridan shuncha daqiqa o'tib javob bo'lmasa — ogohlantirish. Har bir xabar uchun bir marta.",
            "rating_enabled": "Qo'llab-quvvatlash suhbati yopilganda mijozdan 1–5 yulduz bilan baho so'raladi (bildirishnoma + Telegram).",
            "low_rating_alert": "1–2 yulduz qo'yilsa, suhbat «Nazoratda» belgisini oladi va xodimlar Telegram kanaliga xabar boradi. Menejer mijoz bilan bog'lanib, Chat markazida «Hal qilindi» deydi.",
            "order_bot_enabled": "Mijoz «Buyurtmam qayerda?», «где мой заказ» deb yoki buyurtma raqamini yozsa, bot darhol (kechasi ham) buyurtma kartasini yuboradi. Suhbat baribir operator navbatida qoladi.",
            "delivery_days": "Buyurtma berilgandan necha kunda yetkaziladi — kartadagi va {yetkazish_sanasi} o'zgaruvchisidagi taxminiy sana shundan hisoblanadi (yakshanba → dushanba).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        self.fields["days"].initial = [str(d) for d in (inst.work_days or [])]
        for code in ("uz", "ru", "en"):
            self.fields[f"reply_{code}"].initial = (inst.auto_reply_text or {}).get(code, "")

    def clean_delivery_days(self):
        v = self.cleaned_data["delivery_days"]
        if not 0 <= v <= 30:
            raise forms.ValidationError("0 dan 30 kungacha bo'lsin.")
        return v

    def clean_alert_after_minutes(self):
        v = self.cleaned_data["alert_after_minutes"]
        if not 1 <= v <= 1440:
            raise forms.ValidationError("1 dan 1440 daqiqagacha bo'lsin.")
        return v

    def save(self, commit=True):
        inst = super().save(commit=False)
        inst.work_days = sorted(int(d) for d in self.cleaned_data.get("days") or [])
        inst.auto_reply_text = {code: (self.cleaned_data.get(f"reply_{code}") or "").strip() for code in ("uz", "ru", "en") if (self.cleaned_data.get(f"reply_{code}") or "").strip()}
        if commit:
            inst.save()
        return inst


@admin.register(orm.ChatSettings)
class ChatSettingsAdmin(PremiumFormMixin, admin.ModelAdmin):
    """Chat sozlamalari: the singleton -- working hours, auto-reply, staff alert, rating."""

    form = ChatSettingsForm
    fieldsets = (
        ("Ish vaqti", {"fields": ("work_start", "work_end", "days")}),
        ("Ish vaqtidan tashqari avtomatik javob", {"fields": ("auto_reply_enabled", "reply_uz", "reply_ru", "reply_en")}),
        ("Javobsiz suhbatlar — Telegram ogohlantirish", {"fields": ("alert_enabled", "alert_after_minutes", "alert_only_work_hours")}),
        ("Mijoz bahosi", {"fields": ("rating_enabled", "low_rating_alert")}),
        ("Buyurtma boti va yetkazish muddati", {"fields": ("order_bot_enabled", "delivery_days")}),
    )
    hero_icon, hero_tone = "fa-sliders", "#4f46e5"
    nz_css = ("admin/css/nutrizone-chat-desk.css",)

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:chat_chatsettings_change", args=[orm.ChatSettings.load().pk]))

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def response_change(self, request, obj):
        messages.success(request, "Chat sozlamalari saqlandi — darhol kuchga kiradi.")
        return redirect(request.path)

    def form_hero(self, request, obj):
        from django.conf import settings as dj

        from apps.chat.infrastructure.automation import hours_label, is_open

        rated = orm.ConversationRating.objects.filter(created_at__gte=timezone.now() - timedelta(days=30))
        from django.db.models import Avg

        avg = rated.aggregate(a=Avg("score"))["a"]
        channel = bool(getattr(dj, "TELEGRAM_ORDERS_CHAT_ID", None))
        return {
            "title": "Chat sozlamalari", "subtitle": f"hozir: {'ish vaqti' if is_open(cfg=obj) else 'ish vaqtidan tashqari'} · {hours_label(obj)}",
            "chips": [ui.chip("Avto-javob yoqilgan" if obj.auto_reply_enabled else "Avto-javob o'chiq", "#16a34a" if obj.auto_reply_enabled else "#64748b", "fa-robot"),
                      ui.chip("Telegram ogohlantirish" if obj.alert_enabled and channel else "Telegram kanali sozlanmagan" if obj.alert_enabled else "Ogohlantirish o'chiq",
                              "#0891b2" if obj.alert_enabled and channel else "#d97706", "fa-paper-plane"),
                      ui.chip("Baho so'raladi" if obj.rating_enabled else "Baho so'ralmaydi", "#eab308" if obj.rating_enabled else "#64748b", "fa-star"),
                      ui.chip("Buyurtma boti yoqilgan" if obj.order_bot_enabled else "Buyurtma boti o'chiq", "#4f46e5" if obj.order_bot_enabled else "#64748b", "fa-truck-fast")],
            "stats": [
                hero_stat("Ish vaqti", hours_label(obj), "#4f46e5", "Toshkent vaqti", "fa-clock"),
                hero_stat("Ogohlantirish", f"{obj.alert_after_minutes} daq", "#0891b2", "javobsiz qolsa", "fa-bell"),
                hero_stat("O'rtacha baho", f"{avg:.1f} ★" if avg else "—", "#eab308", f"{rated.count()} ta baho, 30 kun", "fa-star"),
                hero_stat("Tayyor javoblar", orm.ChatQuickReply.objects.filter(is_active=True).count(), "#16a34a", "faol", "fa-bolt"),
            ],
            "links": [{"label": "Chat markazi", "url": reverse("admin:nz_chat_admin"), "icon": "fa-headset", "primary": True},
                      {"label": "Tayyor javoblar", "url": reverse("admin:chat_chatquickreply_changelist"), "icon": "fa-bolt"},
                      {"label": "Operatorlar hisoboti", "url": reverse("admin:nz_chat_report"), "icon": "fa-chart-column"}],
        }


def _marked(text: str):
    """A quick reply's text with its {variables} highlighted (escaped first)."""
    from django.utils.html import escape

    from apps.chat.infrastructure.automation import VARIABLE_RE

    return mark_safe(VARIABLE_RE.sub(lambda m: f'<mark class="nzc-var">{m.group(0)}</mark>', str(escape(text))))


class QuickReplyForm(forms.ModelForm):
    class Meta:
        model = orm.ChatQuickReply
        fields = ("title", "text", "sort_order", "is_active")
        help_texts = {"title": "Ro'yxatda ko'rinadigan qisqa nom, masalan «Buyurtma yo'lda».", "sort_order": "Kichik raqam — ro'yxatda yuqorida."}

    def __init__(self, *args, **kwargs):
        from apps.chat.infrastructure.automation import VARIABLES

        super().__init__(*args, **kwargs)
        self.fields["text"].help_text = mark_safe(
            "Operator bosganda javob maydoniga mijoz ma'lumotlari bilan to'ldirilib qo'yiladi — yuborishdan oldin o'zgartirish mumkin. O'zgaruvchilar: "
            + " ".join(f'<mark class="nzc-var" title="{label}">{{{name}}}</mark>' for name, label in VARIABLES.items())
            + "<br>Masalan: «Assalomu alaykum, {ism}! {buyurtma_raqami} buyurtmangiz taxminan {yetkazish_sanasi} yetkaziladi.»")

    def clean_text(self):
        import re

        from apps.chat.infrastructure.automation import VARIABLES

        text = self.cleaned_data["text"]
        unknown = sorted({m for m in re.findall(r"\{([^{}\s]{1,40})\}", text) if m not in VARIABLES})
        if unknown:
            raise forms.ValidationError("Noma'lum o'zgaruvchi: " + ", ".join("{" + u + "}" for u in unknown) + ". Mavjudlari: " + ", ".join("{" + v + "}" for v in VARIABLES))
        return text


@admin.register(orm.ChatQuickReply)
class ChatQuickReplyAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    """Tayyor javoblar: canned answers for the Chat markazi -- edited here, used with one click (usage counted)."""

    form = QuickReplyForm
    list_display = ("sort_order", "uses")
    list_filter = (("is_active", _titled(admin.BooleanFieldListFilter, "Faol")),)
    search_fields = ("title", "text")
    ordering = ("sort_order", "title")
    actions = ["activate", "deactivate"]

    nz_icon, nz_tone, nz_title = "fa-bolt", "#16a34a", "Tayyor javoblar"
    nz_subtitle = "Chat markazida ⚡ tugmasi bilan bir bosishda qo'yiladigan javoblar. Ko'p ishlatiladiganlarini yuqoriga qo'ying."
    nz_columns = (("Javob", ""), ("Tartib", "r"), ("Ishlatilgan", "r"), ("Holat", "r"))
    nz_grid = "minmax(320px,3fr) 90px 110px 110px"
    nz_search = "Nom yoki matn…"
    nz_empty = ("Tayyor javob yo'q", "«Yangi javob» bilan qo'shing.")
    nz_sorts = (("Tartib bo'yicha", ""), ("Ko'p ishlatilgan", "-2"))
    hero_icon, hero_tone, hero_noun = "fa-bolt", "#16a34a", "tayyor javob"
    nz_css = ("admin/css/nutrizone-chat-desk.css",)

    def nz_hero_actions(self, request):
        return [{"label": "Chat markazi", "url": reverse("admin:nz_chat_admin"), "icon": "fa-headset"},
                {"label": "Yangi javob", "url": reverse("admin:chat_chatquickreply_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, q):
        return [format_html('<span class="nzc-qr"><b>{}</b><small>{}</small></span>', q.title, _marked(q.text)), format_html("<b>{}</b>", q.sort_order), format_html("<b>{}</b>", q.uses),
                format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#16a34a" if q.is_active else "#94a3b8", "Faol" if q.is_active else "O'chirilgan")]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Qisqa nom va javob matnini yozing"}
        from apps.chat.infrastructure.automation import VARIABLE_RE

        used = sorted(set(VARIABLE_RE.findall(obj.text)))
        return {"title": obj.title, "subtitle": obj.text[:120], "stats": [hero_stat("Ishlatilgan", obj.uses, "#16a34a", "marta", "fa-bolt"),
                                                                          hero_stat("O'zgaruvchi", len(used), "#4f46e5", ", ".join("{" + u + "}" for u in used) or "yo'q", "fa-wand-magic-sparkles")]}

    @admin.action(description="Faollashtirish")
    def activate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} ta javob faollashtirildi.")

    @admin.action(description="O'chirish (ro'yxatdan yashirish)")
    def deactivate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} ta javob yashirildi.")


@admin.register(orm.ConversationRating)
class ConversationRatingAdmin(ExcelExportMixin, PremiumListMixin, admin.ModelAdmin):
    """Suhbat baholari: customers' 1–5 ★ scores for closed support chats -- CSAT trend, low scores to follow up."""
    excel_title = "Suhbat baholari"
    excel_columns = [Col("Sana", "created_at", 17), Col("Mijoz", lambda r: r.x_people.get(r.customer_id, ("", ""))[0], 22), Col("Operator", lambda r: r.x_people.get(r.operator_id, ("", ""))[0], 20),
                     Col("Baho", "score", 7, number=True), Col("Izoh", "comment", 36), Col("Nazorat holati", "review_status", 14), Col("Menejer izohi", "review_note", 28)]

    def excel_prepare(self, objs):
        who = xl.people([r.customer_id for r in objs] + [r.operator_id for r in objs])
        for r in objs:
            r.x_people = who


    list_display = ("score", "created_at")
    list_filter = (("created_at", _titled(admin.DateFieldListFilter, "Sana")),)
    search_fields = ("comment", "review_note")
    actions = ["mark_resolved"]
    ordering = ("-created_at",)
    list_per_page = 40

    nz_icon, nz_tone, nz_title = "fa-star", "#eab308", "Suhbat baholari"
    nz_subtitle = "Mijozlar qo'llab-quvvatlash suhbatini 1–5 yulduz bilan baholaydi. Past baholarni ko'rib, mijoz bilan qayta bog'laning."
    nz_columns = (("Mijoz", ""), ("Izoh", ""), ("Operator", ""), ("Sana", ""), ("Baho", "r"))
    nz_grid = "minmax(210px,1.6fr) minmax(240px,2.4fr) minmax(130px,1fr) 120px 130px"
    nz_search = "Izoh matni…"
    nz_empty = ("Hali baho yo'q", "Suhbat yopilgach mijozdan baho so'raladi (Chat sozlamalarida yoqiladi).")
    nz_sorts = (("Yangilari", ""), ("Past baho", "1"))
    nz_css = ("admin/css/nutrizone-chat-desk.css",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def nz_href(self, obj):
        return _desk(obj.conversation_id)

    def nz_stats(self, request):
        from django.db.models import Avg

        month = orm.ConversationRating.objects.filter(created_at__gte=timezone.now() - timedelta(days=30))
        k = orm.ConversationRating.objects.aggregate(n=Count("id"), avg=Avg("score"), low=Count("id", filter=Q(score__lte=2)), top=Count("id", filter=Q(score=5)))
        m_avg = month.aggregate(a=Avg("score"))["a"]
        closed = orm.ConversationModel.objects.filter(status__in=("closed", "archived")).exclude(conversation_type="customer_sales").count()
        return [
            ui.stat_card("O'rtacha baho (30 kun)", f"{m_avg:.1f} ★" if m_avg else "—", "#eab308", "fa-star", f"umumiy {k['avg']:.1f} ★" if k["avg"] else ""),
            ui.stat_card("Baholar", k["n"], "#4f46e5", "fa-square-poll-vertical", f"{round(k['n'] * 100 / closed) if closed else 0}% yopilgan suhbatlar baholangan"),
            ui.stat_card("5 yulduz", k["top"], "#16a34a", "fa-face-smile", f"{round(k['top'] * 100 / k['n']) if k['n'] else 0}% mamnun", "?score__exact=5"),
            ui.stat_card("Nazoratda", orm.ConversationRating.objects.filter(review_status="open").count(), "#dc2626" if k["low"] else "#64748b", "fa-eye",
                         f"past baho (1–2 ★): {k['low']} ta", "?review_status=open"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.ConversationRating.objects.values_list("score").annotate(n=Count("id")))
        return ui.tabs_for(request, "score__exact", [("", "Hammasi", sum(counts.values()))] + [(str(sc), "★" * sc, counts.get(sc, 0)) for sc in (5, 4, 3, 2, 1) if counts.get(sc)],
                           {"5": "#16a34a", "4": "#22c55e", "3": "#eab308", "2": "#f97316", "1": "#dc2626"})

    def lookup_allowed(self, lookup, value, request=None):
        return lookup in ("score__exact", "score__lte", "review_status") or super().lookup_allowed(lookup, value, request)

    @admin.action(description="Hal qilindi deb belgilash")
    def mark_resolved(self, request, queryset):
        from apps.chat.infrastructure.automation import resolve_review

        n = sum(resolve_review(cid, request.user.get_full_name() or request.user.get_username()) for cid in set(queryset.filter(review_status="open").values_list("conversation_id", flat=True)))
        self.message_user(request, f"{n} ta past baho nazoratdan chiqarildi." if n else "Tanlanganlar orasida nazoratdagi baho yo'q.")

    def nz_prepare(self, request, objs):
        from apps.platform.infrastructure.chat_view import _staff_names, _users

        self._u, self._staff = _users(r.customer_id for r in objs), _staff_names()

    def nz_row(self, r):
        color = {5: "#16a34a", 4: "#22c55e", 3: "#eab308", 2: "#f97316", 1: "#dc2626"}.get(r.score, "#64748b")
        return [ui.user_cell(self._u.get(r.customer_id)), format_html('<span class="nzc-last">{}</span>', r.comment) if r.comment else ui.muted("izohsiz"),
                self._staff.get(r.operator_id, "") or ui.muted(), format_html('<span title="{}">{}</span>', ui.local(r.created_at), ui.ago(r.created_at)),
                format_html('<span class="nzc-stars" style="--t:{}">{}<i>{}</i></span>{}', color, "★" * r.score, "★" * (5 - r.score), self._review(r))]

    @staticmethod
    def _review(r):
        if r.review_status == "open":
            return mark_safe('<br><span class="nzi-chip" style="--t:#dc2626"><i class="fas fa-eye" aria-hidden="true"></i> Nazoratda</span>')
        if r.review_status == "resolved":
            return format_html('<br><span class="nzi-chip" style="--t:#16a34a" title="{}"><i class="fas fa-check" aria-hidden="true"></i> Hal qilindi</span>', f"{r.reviewed_by}: {r.review_note}".strip(": "))
        return ""
