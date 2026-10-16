"""
Dashboard → Telegram → Postlar: compose a rich post (RichText editor, photo or product, URL buttons), preview it,
send a test copy to your own Telegram, then send it to the channel / news subscribers / all Telegram customers.
"""
from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.telegram_bot.infrastructure import posts
from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings, TelegramPost, TelegramPostStatus
from apps.telegram_bot.infrastructure.rich_text_field import TelegramRichTextField
from apps.telegram_bot.infrastructure.telegram_html import CAPTION_LIMIT, to_plain, visible_length

STATUS_TONE = {"draft": "#64748b", "queued": "#f59e0b", "sending": "#0ea5e9", "sent": "#16a34a", "failed": "#dc2626"}


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
    test_chat = forms.CharField(label="Sinov uchun Telegram ID", required=False, max_length=32,
                                help_text="O'z Telegram ID raqamingiz (@userinfobot ko'rsatadi). «Sinov yuborish» faqat shu chatga yuboradi.")

    class Meta:
        model = TelegramPost
        help_texts = {"image": f"JPG / PNG. Matn {CAPTION_LIMIT} belgigacha bo'lsa rasm ostida chiqadi, uzunroq bo'lsa — rasmdan keyin alohida xabar."}
        fields = ("title", "body", "image", "product", "to_channel", "channel", "to_subscribers", "to_customers", "silent", "pin")

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
        ("Kimga yuboriladi", {"fields": ("to_channel", "channel", "pin", "to_subscribers", "to_customers", "silent")}),
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
        targets = [x for x, on in (("Kanal " + p.channel, p.to_channel), ("Obunachilar", p.to_subscribers), ("Mijozlar", p.to_customers)) if on]
        return [
            format_html('<span style="display:flex;align-items:center">{}<span><b>{}</b><small>{}</small></span></span>', thumb, p.title, (text[:90] + "…") if len(text) > 90 else text),
            format_html("{}", ", ".join(targets) or "—"),
            format_html("<b>{}</b> <small>yetdi</small>{}", p.sent_count, format_html("<small>xato {}</small>", p.failed_count) if p.failed_count else ""),
            format_html("<span>{}</span><small>{}</small>", ui.ago(p.sent_at or p.created_at), p.created_by),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE.get(p.status, "#64748b"), p.get_status_display()),
        ]

    # ---------------------------------------------------------------- form

    def form_hero(self, request, obj):
        if obj is None:
            return {"title": "Yangi Telegram post", "subtitle": "Matnni formatlang, rasm yoki mahsulot qo'shing, avval o'zingizga sinov yuboring."}
        n = visible_length(obj.body)
        return {
            "title": obj.title, "subtitle": f"{ui.local(obj.created_at)} · {obj.created_by}", "icon": "fa-paper-plane", "tone": STATUS_TONE.get(obj.status, "#0ea5e9"),
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
        context.update({"show_save_and_add_another": False, "nztg_post": True, "nztg_can_send": obj is None or obj.status in (TelegramPostStatus.DRAFT, TelegramPostStatus.FAILED, TelegramPostStatus.SENT)})
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
        if "_nztg_send" in request.POST:
            if not (obj.to_channel or obj.to_subscribers or obj.to_customers):
                messages.error(request, "Kimga yuborishni tanlang: kanal, obunachilar yoki mijozlar.")
                return here
            if obj.status in (TelegramPostStatus.QUEUED, TelegramPostStatus.SENDING):
                messages.warning(request, "Bu post allaqachon yuborilmoqda.")
                return here
            posts.queue(obj)
            messages.success(request, "Post yuborish navbatiga qo'yildi. Natija shu sahifada yangilanadi.")
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


@admin.register(ChannelAutoPostSettings)
class ChannelAutoPostSettingsAdmin(PremiumFormMixin, admin.ModelAdmin):
    """Singleton: the list opens the one settings row; a read-only panel shows what would be posted next."""

    readonly_fields = ("queue_panel",)
    fieldsets = (
        ("Holat", {"fields": ("enabled", "channel")}),
        ("Qaysi hodisalar post qilinadi", {"fields": ("new_products", "discounts", "min_discount", "restock")}),
        ("Tartib", {"fields": ("max_per_run", "quiet_from", "quiet_to")}),
        ("Navbatdagi postlar", {"classes": ("nzi-panel",), "fields": ("queue_panel",)}),
    )
    hero_icon, hero_tone, hero_noun = "fa-bullhorn", "#0ea5e9", "sozlama"

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
            from django.utils import timezone

            obj.enabled_at = timezone.now()  # products published before today are not announced as "new"
        super().save_model(request, obj, form, change)

    def form_hero(self, request, obj):
        from apps.telegram_bot.infrastructure.channel_autopost import _channel

        auto = TelegramPost.objects.exclude(source="manual")
        return {
            "title": "Kanal avtopostlari", "subtitle": f"{_channel(obj) or 'Kanal tanlanmagan'} · har 15 daqiqada tekshiriladi",
            "icon": "fa-bullhorn", "tone": "#16a34a" if obj.enabled else "#64748b",
            "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#16a34a" if obj.enabled else "#64748b", "Yoqilgan" if obj.enabled else "O'chirilgan")],
            "stats": [hero_stat("Avtopostlar", auto.count(), "#0ea5e9", "jami", "fa-paper-plane"),
                      hero_stat("Yetkazildi", auto.filter(status="sent").count(), "#16a34a", "kanalga", "fa-circle-check")],
        }

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
