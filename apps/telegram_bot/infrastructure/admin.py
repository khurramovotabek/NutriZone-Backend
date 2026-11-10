"""
Dashboard → Telegram → Postlar: compose a rich post (RichText editor, photo or product, URL buttons), preview it,
send a test copy to your own Telegram, then send it to the channel / news subscribers / all Telegram customers.
"""
from __future__ import annotations

from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.telegram_bot.infrastructure import posts
from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings, ChannelPostSlot, TelegramPost, TelegramPostStatus, TelegramStaffMember
from apps.telegram_bot.infrastructure.rich_text_field import TelegramRichTextField
from apps.telegram_bot.infrastructure.telegram_html import CAPTION_LIMIT, to_plain, visible_length

STATUS_TONE = {"draft": "#64748b", "scheduled": "#7c3aed", "queued": "#f59e0b", "sending": "#0ea5e9", "sent": "#16a34a", "failed": "#dc2626"}


def _default_channel() -> str:
    """@username from Sayt sozlamalari → Telegram kanal havolasi (https://t.me/<name>)."""
    try:
        from apps.platform.infrastructure.models import SiteSettings

        row = SiteSettings.objects.filter(pk=1).only("telegram_channel_url").first()
        url = ((row.telegram_channel_url if row else "") or "").strip().rstrip("/")
    except Exception:  # noqa: BLE001
        return ""
    name = url.rsplit("/", 1)[-1] if "t.me/" in url else ""
    return f"@{name}" if name and not name.startswith(("+", "joinchat")) else ""


class TelegramPostForm(forms.ModelForm):
    body = TelegramRichTextField(label="Post matni", required=False, placeholder="🔥 Yangi kelgan mahsulot! …")
    button1_text = forms.CharField(label="1-tugma matni", required=False, max_length=64)
    button1_url = forms.URLField(label="1-tugma havolasi", required=False, assume_scheme="https")
    button2_text = forms.CharField(label="2-tugma matni", required=False, max_length=64)
    button2_url = forms.URLField(label="2-tugma havolasi", required=False, assume_scheme="https")
    button3_text = forms.CharField(label="3-tugma matni", required=False, max_length=64)
    button3_url = forms.URLField(label="3-tugma havolasi", required=False, assume_scheme="https")
    scheduled_at = forms.DateTimeField(
        label="Yuborish vaqti", required=False, input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        help_text="Bo'sh — «Saqlash va yuborish» darhol yuboradi. Vaqt tanlansa — post shu daqiqada o'zi yuboriladi (Toshkent vaqti).")
    test_chat = forms.CharField(label="Sinov uchun Telegram ID", required=False, max_length=32,
                                help_text="O'z Telegram ID raqamingiz (@userinfobot ko'rsatadi). «Sinov yuborish» faqat shu chatga yuboradi.")

    class Meta:
        model = TelegramPost
        help_texts = {"image": f"JPG / PNG. Matn {CAPTION_LIMIT} belgigacha bo'lsa rasm ostida chiqadi, uzunroq bo'lsa — rasmdan keyin alohida xabar."}
        fields = ("title", "body", "image", "product", "to_channel", "channel", "to_subscribers", "to_customers",
                  "to_orders_channel", "to_orders_staff", "to_analytics_staff", "scheduled_at", "silent", "pin")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i, b in enumerate((self.instance.buttons or [])[:3], start=1):
            self.fields[f"button{i}_text"].initial = b.get("text", "")
            self.fields[f"button{i}_url"].initial = b.get("url", "")
        if self.instance._state.adding and not self.initial.get("channel"):  # UUID pk is set even on a new post
            self.initial["channel"] = _default_channel()

    def clean(self):
        data = super().clean()
        if not (data.get("body") or data.get("image") or data.get("product")):
            raise forms.ValidationError("Post bo'sh: matn yozing yoki rasm / mahsulot tanlang.")
        if data.get("to_channel") and not (data.get("channel") or "").strip():
            self.add_error("channel", "Kanal @username yoki ID sini kiriting.")
        if data.get("to_orders_channel"):
            from apps.telegram_bot.infrastructure.orders_chat import chat_id

            if not chat_id():
                self.add_error("to_orders_channel", "Buyurtmalar kanali ulanmagan (Telegram botlar markazi → Buyurtmalar kanali).")
        when = data.get("scheduled_at")
        if when and when < timezone.now() - timedelta(minutes=1) and self.instance.status in ("draft", "scheduled", "failed", "sent"):
            self.add_error("scheduled_at", "Bu vaqt o'tib ketgan. Kelajakdagi vaqtni tanlang yoki bo'sh qoldiring (darhol yuboriladi).")
        for i in (1, 2, 3):
            if bool(data.get(f"button{i}_text")) != bool(data.get(f"button{i}_url")):
                self.add_error(f"button{i}_url", "Tugma uchun matn ham, havola ham kerak.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        d = self.cleaned_data
        obj.buttons = [{"text": d[f"button{i}_text"].strip(), "url": d[f"button{i}_url"].strip()} for i in (1, 2, 3) if d.get(f"button{i}_text") and d.get(f"button{i}_url")]
        if commit:
            obj.save()
        return obj


@admin.register(TelegramPost)
class TelegramPostAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    excel_title = "Telegram postlar"
    excel_columns = [Col("Nom", "title", 30), Col("Holat", "status", 12), Col("Kanal", "channel", 18), Col("Obunachilar", "to_subscribers", 11), Col("Mijozlar", "to_customers", 10),
                     Col("Qabul qiluvchilar", "recipients", 12, number=True), Col("Yetkazildi", "sent_count", 11, number=True), Col("Xato", "failed_count", 8, number=True),
                     Col("Yuborilgan", "sent_at", 17), Col("Kim", "created_by", 18), Col("Matn", lambda p: to_plain(p.body), 60)]

    form = TelegramPostForm
    change_form_template = "admin/telegram_bot/telegrampost/change_form.html"
    list_display = ("title", "created_at")
    search_fields = ("title", "body")
    ordering = ("-created_at",)
    list_per_page = 30
    autocomplete_fields = ("product",)
    readonly_fields = ("result_panel",)
    fieldsets = (
        ("Post", {"fields": ("title", "body")}),
        ("Rasm va mahsulot", {"fields": ("image", "product")}),
        ("Tugmalar", {"fields": (("button1_text", "button1_url"), ("button2_text", "button2_url"), ("button3_text", "button3_url"))}),
        ("Do'kon boti: kanal va mijozlar", {"fields": ("to_channel", "channel", "pin", "to_subscribers", "to_customers")}),
        ("Xodimlar botlari", {"fields": ("to_orders_channel", "to_orders_staff", "to_analytics_staff")}),
        ("Qachon", {"fields": ("scheduled_at", "silent")}),
        ("Sinov", {"fields": ("test_chat",)}),
    )

    nz_icon, nz_tone, nz_title = "fa-paper-plane", "#0ea5e9", "Telegram postlar"
    nz_subtitle = "Kanal, yangilik obunachilari va mijozlarga formatlangan post: rasm, mahsulot, tugmalar — oldindan ko'rish va sinov bilan."
    nz_columns = (("Post", ""), ("Kimga", ""), ("Natija", "r"), ("Vaqt", ""), ("Holat", "r"))
    nz_grid = "minmax(280px,2.6fr) minmax(180px,1.3fr) 150px 140px 120px"
    nz_search = "Nom yoki matn…"
    nz_empty = ("Hali post yo'q", "«Qo'shish» tugmasi bilan birinchi Telegram postini tayyorlang.")
    hero_icon, hero_tone, hero_noun = "fa-paper-plane", "#0ea5e9", "post"

    def get_fieldsets(self, request, obj=None):
        fs = list(super().get_fieldsets(request, obj))
        if obj is not None and obj.status != TelegramPostStatus.DRAFT:
            fs.insert(0, ("Natija", {"classes": ("nzi-panel",), "fields": ("result_panel",)}))
        return fs

    # ---------------------------------------------------------------- list

    def nz_stats(self, request):
        k = TelegramPost.objects.aggregate(n=Count("id"), sent=Count("id", filter=Q(status="sent")), reach=Sum("sent_count"), failed=Sum("failed_count"),
                                           drafts=Count("id", filter=Q(status="draft")))
        return [
            ui.stat_card("Postlar", k["n"], "#0ea5e9", "fa-paper-plane", f"{k['drafts']} ta qoralama"),
            ui.stat_card("Yuborilgan", k["sent"], "#16a34a", "fa-circle-check", "post"),
            ui.stat_card("Yetkazilgan", k["reach"] or 0, "#2563eb", "fa-users", "kanal va shaxsiy chatlar"),
            ui.stat_card("Xatolar", k["failed"] or 0, "#dc2626", "fa-triangle-exclamation", "bloklagan / topilmagan chatlar"),
        ]

    def nz_tabs(self, request):
        counts = dict(TelegramPost.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values()))] + [(v, label, counts[v]) for v, label in TelegramPostStatus.choices if counts.get(v)], STATUS_TONE)

    def lookup_allowed(self, lookup, value, request=None):
        return lookup == "status__exact" or super().lookup_allowed(lookup, value, request)

    def nz_hero_actions(self, request):
        from django.urls import reverse

        return [{"label": "Botlar markazi", "url": reverse("admin:nz_telegram_status"), "icon": "fa-robot"},
                {"label": "Yangi post", "url": reverse("admin:telegram_bot_telegrampost_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, p):
        thumb = format_html('<img src="{}" alt="" style="width:40px;height:40px;object-fit:cover;border-radius:10px;margin-right:10px">', p.image.url) if p.image else ""
        text = to_plain(p.body)
        targets = posts.audience(p)
        return [
            format_html('<span style="display:flex;align-items:center">{}<span><b>{}</b><small>{}</small></span></span>', thumb, p.title, (text[:90] + "…") if len(text) > 90 else text),
            format_html("{}", ", ".join(targets) or "—"),
            format_html("<b>{}</b> <small>yetdi</small>{}", p.sent_count, format_html("<small>xato {}</small>", p.failed_count) if p.failed_count else ""),
            (format_html("<span>⏰ {}</span><small>{}</small>", ui.local(p.scheduled_at, "%d.%m %H:%M"), p.created_by) if p.status == "scheduled" and p.scheduled_at
             else format_html("<span>{}</span><small>{}</small>", ui.ago(p.sent_at or p.created_at), p.created_by)),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE.get(p.status, "#64748b"), p.get_status_display()),
        ]

    # ---------------------------------------------------------------- form

    def form_hero(self, request, obj):
        if obj is None:
            return {"title": "Yangi Telegram post", "subtitle": "Matnni formatlang, rasm yoki mahsulot qo'shing, avval o'zingizga sinov yuboring."}
        n = visible_length(obj.body)
        return {
            "title": obj.title, "subtitle": (f"⏰ {ui.local(obj.scheduled_at)} da yuboriladi · " if obj.status == "scheduled" and obj.scheduled_at else "")
            + f"{ui.local(obj.created_at)} · {obj.created_by}", "icon": "fa-paper-plane", "tone": STATUS_TONE.get(obj.status, "#0ea5e9"),
            "image": obj.image.url if obj.image else None,
            "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE.get(obj.status, "#64748b"), obj.get_status_display())],
            "stats": [
                hero_stat("Yetkazildi", obj.sent_count, "#16a34a", f"{obj.recipients} qabul qiluvchidan" if obj.recipients else "hali yuborilmagan", "fa-users"),
                hero_stat("Xato", obj.failed_count, "#dc2626", "bloklagan / topilmagan", "fa-triangle-exclamation"),
                hero_stat("Matn", n, "#0ea5e9", "belgi" + (" · rasmdan keyin alohida xabar" if (obj.image or obj.product_id) and n > CAPTION_LIMIT else ""), "fa-align-left"),
            ],
        }

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.get_full_name() or request.user.get_username()
        super().save_model(request, obj, form, change)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context.update({"show_save_and_add_another": False, "nztg_post": True, "nztg_can_send": obj is None or obj.status in (TelegramPostStatus.DRAFT, TelegramPostStatus.FAILED, TelegramPostStatus.SENT, TelegramPostStatus.SCHEDULED),
                        "nztg_scheduled": obj is not None and obj.status == TelegramPostStatus.SCHEDULED})
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def response_add(self, request, obj, post_url_continue=None):
        return self._after_save(request, obj) or super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        return self._after_save(request, obj) or super().response_change(request, obj)

    def _after_save(self, request, obj):
        from django.urls import reverse

        here = HttpResponseRedirect(reverse("admin:telegram_bot_telegrampost_change", args=[obj.pk]))
        if "_nztg_test" in request.POST:
            chat = (request.POST.get("test_chat") or "").strip()
            if not chat:
                messages.error(request, "Sinov uchun Telegram ID kiriting.")
                return here
            try:
                posts.send_test(obj, chat)
                messages.success(request, f"Sinov post {chat} chatiga yuborildi — Telegramni tekshiring.")
            except posts.PostError as exc:
                messages.error(request, f"Telegram rad etdi: {exc}")
            return here
        if "_nztg_unschedule" in request.POST:
            posts.unschedule(obj)
            messages.success(request, "Reja bekor qilindi — post qoralamaga qaytdi.")
            return here
        if "_nztg_send" in request.POST:
            if not posts.audience(obj):
                messages.error(request, "Kimga yuborishni tanlang: kanal, obunachilar, mijozlar yoki xodimlar botlari.")
                return here
            if obj.status in (TelegramPostStatus.QUEUED, TelegramPostStatus.SENDING):
                messages.warning(request, "Bu post allaqachon yuborilmoqda.")
                return here
            if obj.scheduled_at and obj.scheduled_at > timezone.now():
                posts.schedule(obj, obj.scheduled_at)
                messages.success(request, f"Post rejalashtirildi: {ui.local(obj.scheduled_at)} da o'zi yuboriladi ({', '.join(posts.audience(obj))}).")
                return here
            posts.queue(obj)
            messages.success(request, f"Post yuborish navbatiga qo'yildi ({', '.join(posts.audience(obj))}). Natija shu sahifada yangilanadi.")
            return here
        return None

    @admin.display(description="")
    def result_panel(self, obj):
        err = format_html('<pre style="white-space:pre-wrap;margin-top:8px;color:#f87171">{}</pre>', obj.last_error) if obj.last_error else ""
        link = ""
        if obj.channel_message_id and obj.channel.startswith("@"):
            link = format_html(' · <a href="https://t.me/{}/{}" target="_blank" rel="noopener">Kanaldagi postni ochish ↗</a>', obj.channel.lstrip("@"), obj.channel_message_id)
        return format_html('<div class="nzi-panel-body"><p><b>{}</b> ta yetkazildi, <b>{}</b> ta xato{} {}</p>{}</div>',
                           obj.sent_count, obj.failed_count, f" · {ui.local(obj.sent_at)}" if obj.sent_at else "", link, err)


class ChannelAutoPostSettingsForm(forms.ModelForm):
    daily_template = TelegramRichTextField(label="Post shabloni", required=False, caption=True,
                                           help_text="Bo'sh qoldirilsa — standart shablon. {o'zgaruvchi} o'rniga mahsulot ma'lumoti qo'yiladi; "
                                                     "qiymati bo'sh o'zgaruvchili qator o'zi tushib qoladi.")

    class Meta:
        model = ChannelAutoPostSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.telegram_bot.infrastructure.daily_posts import DEFAULT_TEMPLATE

        if not (self.instance.daily_template or "").strip():
            self.initial["daily_template"] = DEFAULT_TEMPLATE


class ChannelPostSlotForm(forms.ModelForm):
    class Meta:
        model = ChannelPostSlot
        fields = ("time", "kind", "heading", "is_active")
        widgets = {"time": forms.TimeInput(attrs={"type": "time", "class": "nzs-time"}, format="%H:%M"),
                   "heading": forms.TextInput(attrs={"class": "nzs-heading", "placeholder": "☀️ Kun mahsuloti"})}


class ChannelPostSlotInline(admin.TabularInline):
    model = ChannelPostSlot
    form = ChannelPostSlotForm
    extra = 0
    fields = ("time", "kind", "heading", "is_active")
    verbose_name = "Vaqt"
    verbose_name_plural = "Kunlik jadval (Toshkent vaqti) — har vaqtda kanalga bitta mahsulot posti"


@admin.register(ChannelAutoPostSettings)
class ChannelAutoPostSettingsAdmin(PremiumFormMixin, admin.ModelAdmin):
    """Singleton: the shop channel's daily schedule (daily_posts.py) + event autoposts (channel_autopost.py)."""

    form = ChannelAutoPostSettingsForm
    inlines = (ChannelPostSlotInline,)
    readonly_fields = ("today_panel", "variables_panel", "queue_panel")
    fieldsets = (
        ("Kunlik jadval", {"fields": ("daily_enabled", "channel", "repeat_days")}),
        ("Bugungi reja", {"classes": ("nzi-panel",), "fields": ("today_panel",)}),
        ("Post shabloni", {"fields": ("daily_template",)}),
        ("O'zgaruvchilar", {"classes": ("nzi-panel",), "fields": ("variables_panel",)}),
        ("Hodisa avtopostlari (yangi / chegirma / yana sotuvda)", {"fields": ("enabled", "new_products", "discounts", "min_discount", "restock")}),
        ("Avtopostlar tartibi", {"fields": ("max_per_run", "quiet_from", "quiet_to")}),
        ("Navbatdagi avtopostlar", {"classes": ("nzi-panel",), "fields": ("queue_panel",)}),
    )
    hero_icon, hero_tone, hero_noun = "fa-calendar-days", "#0ea5e9", "sozlama"

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def changelist_view(self, request, extra_context=None):
        from django.urls import reverse

        ChannelAutoPostSettings.get()
        return HttpResponseRedirect(reverse("admin:telegram_bot_channelautopostsettings_change", args=[1]))

    def save_model(self, request, obj, form, change):
        if obj.enabled and not obj.enabled_at:
            obj.enabled_at = timezone.now()  # products published before today are not announced as "new"
        from apps.telegram_bot.infrastructure.daily_posts import DEFAULT_TEMPLATE

        if (obj.daily_template or "").strip() == DEFAULT_TEMPLATE.strip():
            obj.daily_template = ""  # unchanged default: keep following future improvements of the default
        super().save_model(request, obj, form, change)

    def form_hero(self, request, obj):
        from apps.telegram_bot.infrastructure.channel_autopost import _channel

        slots = list(obj.slots.filter(is_active=True))
        daily = TelegramPost.objects.filter(source="daily")
        auto = TelegramPost.objects.exclude(source__in=("manual", "daily"))
        on = obj.daily_enabled and slots
        return {
            "title": "Kanal jadvali", "subtitle": f"{_channel(obj) or 'Kanal tanlanmagan'} · har kuni " + (", ".join(f"{x.time:%H:%M}" for x in slots) or "vaqt yo'q"),
            "icon": "fa-calendar-days", "tone": "#16a34a" if on else "#64748b",
            "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#16a34a" if on else "#64748b", "Jadval yoqilgan" if on else "Jadval o'chirilgan"),
                      format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#0ea5e9" if obj.enabled else "#64748b", "Avtopostlar yoqilgan" if obj.enabled else "Avtopostlar o'chirilgan")],
            "stats": [hero_stat("Jadval postlari", daily.filter(status="sent").count(), "#16a34a", "kanalga yuborilgan", "fa-calendar-check"),
                      hero_stat("Rejalashtirilgan", TelegramPost.objects.filter(status="scheduled").count(), "#7c3aed", "qo'lda tayyorlangan", "fa-clock"),
                      hero_stat("Avtopostlar", auto.count(), "#0ea5e9", "jami", "fa-paper-plane")],
        }

    @admin.display(description="")
    def today_panel(self, obj):
        from datetime import datetime

        from django.urls import reverse
        from django.utils.html import format_html_join

        from apps.telegram_bot.infrastructure import daily_posts as dp

        today = timezone.localdate()
        now = timezone.now()
        rows, first_preview = [], None
        for slot in obj.slots.filter(is_active=True):
            at = datetime.combine(today, slot.time, tzinfo=dp.TZ)
            post = TelegramPost.objects.filter(dedupe_key=f"daily:{today:%Y%m%d}:{slot.pk}").first()
            if post:
                state = format_html('<a href="{}">{} — {}</a>', reverse("admin:telegram_bot_telegrampost_change", args=[post.pk]), post.get_status_display(),
                                    post.product.translations.first().name if post.product_id and post.product.translations.exists() else post.title)
            elif at + dp.SLOT_WINDOW <= now:
                state = format_html('<span class="nzi-muted">{}</span>', "vaqti o'tdi — bugun bu vaqtda jadval posti chiqmadi")
            else:
                try:
                    pv = dp.preview(slot)
                except Exception as exc:  # noqa: BLE001
                    pv, state = None, format_html('<span class="nzi-muted">hisoblab bo\'lmadi: {}</span>', exc)
                else:
                    state = format_html("taxminan: <b>{}</b>", pv["card"]["name"]) if pv else format_html('<span class="nzi-muted">{}</span>', "post qilinadigan mahsulot yo'q")
                if pv and first_preview is None:
                    first_preview = pv
            rows.append((f"{slot.time:%H:%M}", slot.heading or slot.get_kind_display(), state))
        if not rows:
            return format_html('<p class="nzi-none">{}</p>', "Jadvalda faol vaqt yo'q — pastdagi jadvalga vaqt qo'shing.")
        sample = format_html('<p class="nzi-help">Navbatdagi post namunasi:</p><div class="nztg-bubble" style="max-width:420px;white-space:pre-wrap">{}</div>',
                             mark_safe(first_preview["body"])) if first_preview else ""
        return format_html('<div class="nzi-panel-body"><ul class="nzi-items">{}</ul>{}<p class="nzi-help">{}</p></div>',
                           format_html_join("", "<li><span><b>{}</b> · {} — {}</span></li>", rows), sample,
                           "Mahsulot post paytida tanlanadi (zaxirada bor, rasmi bor, oxirgi kunlarda kanalga chiqmagan). "
                           "Shu vaqt atrofida kanalga o'zingiz post qo'ysangiz, jadval o'sha vaqtni o'tkazib yuboradi.")

    @admin.display(description="")
    def variables_panel(self, obj):
        from django.utils.html import format_html_join

        from apps.telegram_bot.infrastructure.daily_posts import VARIABLES

        return format_html('<div class="nzi-panel-body"><ul class="nzi-items">{}</ul></div>',
                           format_html_join("", "<li><span><code>{{{}}}</code> — {}</span></li>", VARIABLES))

    @admin.display(description="")
    def queue_panel(self, obj):
        from django.utils.html import format_html_join

        from apps.telegram_bot.infrastructure.channel_autopost import caption, candidates

        try:
            events = candidates(obj)[:5]
        except Exception as exc:  # noqa: BLE001
            return format_html('<p class="nzi-none">Hisoblab bo\'lmadi: {}</p>', exc)
        if not events:
            return format_html('<p class="nzi-none">{}</p>', "Hozircha post qilinadigan yangi hodisa yo'q.")
        label = {"new": "🆕 Yangi", "sale": "🔥 Chegirma", "restock": "📦 Yana sotuvda"}
        return format_html('<div class="nzi-panel-body"><ul class="nzi-items">{}</ul><p class="nzi-help">Namuna matn:</p><div class="nztg-bubble" style="max-width:420px">{}</div></div>',
                           format_html_join("", "<li><span>{} — <b>{}</b></span></li>", ((label[k], c["name"]) for k, c, _d in events)),
                           mark_safe(caption(events[0][0], events[0][1])))


# ---------------------------------------------------------------- Telegram xodimlari (TelegramStaffMember)


class TelegramStaffMemberForm(forms.ModelForm):
    pick = forms.ChoiceField(label="Orders botni boshlaganlardan tanlash", required=False,
                             help_text="Odam avval @Orders botda /start bosgan bo'lsa, shu yerdan tanlang — ID va ism o'zi to'ldiriladi.")

    class Meta:
        model = TelegramStaffMember
        fields = ("telegram_user_id", "full_name", "is_active")
        labels = {"telegram_user_id": "Telegram ID", "full_name": "Ism", "is_active": "Faol"}
        help_texts = {"telegram_user_id": "Raqamli Telegram ID (masalan 1323573501). Odam @userinfobot ga yozib bilib olishi mumkin.",
                      "is_active": "O'chirilsa, ruxsat darhol yo'qoladi (yozuv tarix uchun qoladi)."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

        taken = set(TelegramStaffMember.objects.values_list("telegram_user_id", flat=True))
        subs = TelegramBotSubscriber.objects.filter(bot="orders", is_active=True).order_by("-last_seen_at")[:200]
        choices = [("", "— tanlang —")]
        for s in subs:
            tid = s.telegram_user_id or s.chat_id
            if tid and tid > 0 and tid not in taken:
                choices.append((str(tid), f"{s.display_name or '—'}{' @' + s.username if s.username else ''} · {tid}"))
        self.fields["pick"].choices = choices
        if self.instance and self.instance.pk:
            self.fields.pop("pick")
            self.fields["telegram_user_id"].disabled = True
        else:
            self.fields["telegram_user_id"].required = False

    def clean(self):
        data = super().clean()
        picked = data.get("pick")
        if picked and not data.get("telegram_user_id"):
            from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

            data["telegram_user_id"] = int(picked)
            self.instance.telegram_user_id = int(picked)
            if not data.get("full_name"):
                sub = TelegramBotSubscriber.objects.filter(bot="orders").filter(Q(telegram_user_id=int(picked)) | Q(chat_id=int(picked))).first()
                data["full_name"] = (sub.display_name if sub else "") or ""
        tid = data.get("telegram_user_id")
        if not tid:
            self.add_error("telegram_user_id", "Telegram ID kiriting yoki ro'yxatdan tanlang.")
        elif tid <= 0:
            self.add_error("telegram_user_id", "Bu odamning ID'si emas (manfiy ID — kanal yoki guruh).")
        elif not (self.instance and self.instance.pk) and TelegramStaffMember.objects.filter(pk=tid).exists():
            self.add_error("telegram_user_id", "Bu odam allaqachon ro'yxatda.")
        return data


@admin.register(TelegramStaffMember)
class TelegramStaffMemberAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    """
    Who sees EVERY branch in the Orders bot and may press Confirm/Cancel under channel posts (staff_access.py,
    callback_router manager actions). Customer and sales data -- superusers only.
    """

    form = TelegramStaffMemberForm
    list_display = ("telegram_user_id", "created_at")
    search_fields = ("full_name", "=telegram_user_id")
    ordering = ("-is_active", "full_name")
    list_per_page = 50
    actions = ("deactivate", "activate")

    nz_icon, nz_tone, nz_title = "fa-user-shield", "#7c3aed", "Telegram xodimlari"
    nz_subtitle = "Orders botda hamma filiallarni ko'radi va kanaldagi buyurtmalarni «Tasdiqlash / Bekor qilish» qila oladi."
    nz_columns = (("Xodim", ""), ("Telegram ID", ""), ("Orders bot", ""), ("Qo'shilgan", ""), ("Holat", "r"))
    nz_grid = "minmax(220px,2fr) 150px minmax(160px,1.2fr) 130px 110px"
    nz_search = "Ism yoki Telegram ID…"
    nz_empty = ("Ro'yxat bo'sh", "«Qo'shish» bilan birinchi xodimni qo'shing — u Orders botda hamma filiallarni ko'radi.")
    hero_icon, hero_tone, hero_noun = "fa-user-shield", "#7c3aed", "xodim"

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (("Xodim", {"fields": ("pick", "telegram_user_id", "full_name", "is_active")}),
                    ("Nimaga ruxsat beradi", {"classes": ("nzi-panel",), "fields": ("rights_panel",)}))
        return (("Xodim", {"fields": ("telegram_user_id", "full_name", "is_active")}),
                ("Nimaga ruxsat beradi", {"classes": ("nzi-panel",), "fields": ("rights_panel",)}))

    def get_readonly_fields(self, request, obj=None):
        return ("rights_panel",)

    # superusers only: these people get every branch's sales and every customer's order
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    has_add_permission = has_change_permission = has_delete_permission = lambda self, request, obj=None: request.user.is_active and request.user.is_superuser  # noqa: E731

    # ---------------------------------------------------------------- list

    def nz_prepare(self, request, objs):
        from apps.identity.infrastructure.models import User
        from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

        ids = [o.telegram_user_id for o in objs]
        self._subs = {}
        for s in TelegramBotSubscriber.objects.filter(bot="orders").filter(Q(telegram_user_id__in=ids) | Q(chat_id__in=ids)):
            self._subs[s.telegram_user_id or s.chat_id] = s
        self._users = {u.telegram_user_id: u for u in User.objects.filter(telegram_user_id__in=ids).only("id", "telegram_user_id", "full_name", "phone_number")}

    def nz_stats(self, request):
        from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

        k = TelegramStaffMember.objects.aggregate(on=Count("pk", filter=Q(is_active=True)), off=Count("pk", filter=Q(is_active=False)))
        active_ids = list(TelegramStaffMember.objects.filter(is_active=True).values_list("pk", flat=True))
        started = TelegramBotSubscriber.objects.filter(bot="orders", is_active=True).filter(Q(telegram_user_id__in=active_ids) | Q(chat_id__in=active_ids)).count()
        return [
            ui.stat_card("Faol xodimlar", k["on"], "#7c3aed", "fa-user-shield", "hamma filialni ko'radi"),
            ui.stat_card("Botni boshlagan", started, "#16a34a", "fa-robot", f"{k['on']} tadan — /start bosilmasa bot yoza olmaydi"),
            ui.stat_card("O'chirilgan", k["off"], "#64748b", "fa-user-slash", "ruxsati yo'q"),
        ]

    def nz_tabs(self, request):
        counts = dict(TelegramStaffMember.objects.values_list("is_active").annotate(n=Count("pk")))
        return ui.tabs_for(request, "is_active__exact", [("", "Hammasi", sum(counts.values())), ("1", "Faol", counts.get(True, 0)), ("0", "O'chirilgan", counts.get(False, 0))],
                           {"1": "#16a34a", "0": "#64748b"})

    def lookup_allowed(self, lookup, value, request=None):
        return lookup == "is_active__exact" or super().lookup_allowed(lookup, value, request)

    def nz_hero_actions(self, request):
        from django.urls import reverse

        return [{"label": "Botlar markazi", "url": reverse("admin:nz_telegram_status"), "icon": "fa-robot"},
                {"label": "Xodim qo'shish", "url": reverse("admin:telegram_bot_telegramstaffmember_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, m):
        sub = getattr(self, "_subs", {}).get(m.telegram_user_id)
        user = getattr(self, "_users", {}).get(m.telegram_user_id)
        name = m.full_name or (sub.display_name if sub else "") or (user.full_name if user else "") or "Nomsiz"
        extra = " · ".join(x for x in ((f"@{sub.username}" if sub and sub.username else ""), (user.phone_number if user else "")) if x)
        if sub and sub.is_active:
            bot = format_html('<span class="nzi-pill" style="--t:#16a34a">Ulangan</span><small>oxirgi: {}</small>', ui.ago(sub.last_seen_at))
        elif sub:
            bot = format_html('<span class="nzi-pill" style="--t:#dc2626">{}</span>', "Botni bloklagan")
        else:
            bot = format_html('<span class="nzi-pill" style="--t:#d97706">{}</span><small>{}</small>', "/start bosmagan", "bot unga yoza olmaydi")
        return [
            format_html("<b>{}</b><small>{}</small>", name, extra or "—"),
            format_html('<code data-copy="{}">{}</code>', m.telegram_user_id, m.telegram_user_id),
            bot,
            format_html("<span>{}</span>", ui.local(m.created_at, "%d.%m.%Y")),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#16a34a" if m.is_active else "#64748b", "Faol" if m.is_active else "O'chirilgan"),
        ]

    @admin.action(description="Tanlanganlarni o'chirish (ruxsatni olish)")
    def deactivate(self, request, queryset):
        n = queryset.update(is_active=False)
        messages.success(request, f"{n} ta xodimning ruxsati olindi.")

    @admin.action(description="Tanlanganlarni faollashtirish")
    def activate(self, request, queryset):
        n = queryset.update(is_active=True)
        messages.success(request, f"{n} ta xodim faollashtirildi.")

    # ---------------------------------------------------------------- form

    def form_hero(self, request, obj):
        if obj is None:
            return {"title": "Telegram xodimi qo'shish", "subtitle": "Orders botda hamma filiallarni ko'radigan va buyurtmalarni tasdiqlay oladigan odam.",
                    "icon": "fa-user-shield", "tone": "#7c3aed"}
        return {"title": obj.full_name or str(obj.telegram_user_id), "subtitle": f"Telegram ID {obj.telegram_user_id} · qo'shilgan {ui.local(obj.created_at)}",
                "icon": "fa-user-shield", "tone": "#7c3aed" if obj.is_active else "#64748b",
                "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#16a34a" if obj.is_active else "#64748b", "Faol" if obj.is_active else "O'chirilgan")]}

    @admin.display(description="")
    def rights_panel(self, obj):
        return mark_safe(
            '<div class="nzi-panel-body"><ul class="nzi-items">'
            "<li><span>📋 Orders botda hamma filiallar: bugungi savdo, onlayn buyurtmalar, jarayondagilar</span></li>"
            "<li><span>✔️ Buyurtmalar kanalidagi postlarda «Tasdiqlash / Bekor qilish» tugmalari</span></li>"
            "<li><span>🔒 Filial egasi bu ro'yxatsiz ham o'z filialini ko'radi — bu yerga faqat rahbar va menejerlarni qo'shing</span></li>"
            "</ul><p class=\"nzi-help\">Bot odamga yoza olishi uchun u @Orders botda bir marta /start bosishi kerak.</p></div>"
        )
