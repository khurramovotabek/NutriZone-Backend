"""
Dashboard → AI maslahatchi → AI suhbatlar: every customer conversation with the assistant, for quality review --
what people ask, which products were shown, thumbs up / down, errors, token use and an approximate API cost.
Read-only: conversations are written by the assistant only.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.html import format_html

from apps.assistant.infrastructure.models import AssistantConversation
from apps.platform.infrastructure import premium_admin as ui

# USD per million tokens (Claude Opus 5.5: input, output, cache read, cache write = 1.25 x input) -- an estimate for staff
PRICES = {"claude-opus-5-5": (4, 20, Decimal("0.2"), 5), "claude-sonnet-5-5": (2, 10, Decimal("0.2"), Decimal("2.5")), "claude-haiku-5-5": (Decimal("0.1"), Decimal("0.5"), Decimal("0.01"), Decimal("0.125"))}


def cost_usd(conv) -> Decimal:
    i, o, cr, cw = PRICES.get(settings.ASSISTANT_MODEL, PRICES["claude-opus-5-5"])
    total = conv.input_tokens * Decimal(i) + conv.output_tokens * Decimal(o) + conv.cache_read_tokens * Decimal(cr) + conv.cache_write_tokens * Decimal(cw)
    return (total / 1_000_000).quantize(Decimal("0.0001"))


@admin.register(AssistantConversation)
class AssistantConversationAdmin(ui.PremiumListMixin, admin.ModelAdmin):
    nz_icon = "fa-robot"
    nz_tone = "#8b5cf6"
    nz_title = "AI suhbatlar"
    nz_subtitle = "Mijozlar AI maslahatchiga nima so'rayapti, qaysi mahsulotlar taklif qilindi va javoblar qanchalik foydali bo'ldi."
    nz_columns = (("Oxirgi savol", ""), ("Mijoz", ""), ("Mahsulotlar", "r"), ("Baho", ""), ("Vaqt", ""), ("Savollar", "r"))
    nz_grid = "minmax(0,2.4fr) minmax(0,1.2fr) 90px 110px 120px 80px"
    nz_search = "Savol matni bo'yicha…"
    nz_empty = ("Hali suhbat yo'q", "Mijozlar saytdagi AI maslahatchiga yozganda bu yerda paydo bo'ladi.")
    list_filter = ("locale", "channel")
    search_fields = ("last_message",)
    list_per_page = 40

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tab = request.GET.get("tab", "")
        if tab == "down":
            qs = qs.filter(feedback_down__gt=0)
        elif tab == "errors":
            qs = qs.filter(errors__gt=0)
        elif tab == "products":
            qs = qs.filter(products_shown__gt=0)
        return qs

    def nz_tabs(self, request):
        base = AssistantConversation.objects.all()
        return ui.tabs_for(request, "tab", [("", "Hammasi", base.count()), ("products", "Mahsulot ko'rsatilgan", base.filter(products_shown__gt=0).count()),
                                            ("down", "Yomon baholangan", base.filter(feedback_down__gt=0).count()), ("errors", "Xatoli", base.filter(errors__gt=0).count())],
                           {"down": "#ef4444", "errors": "#f59e0b", "products": "#22c55e"})

    def nz_stats(self, request):
        week = AssistantConversation.objects.filter(created_at__gte=timezone.now() - timedelta(days=7))
        agg = week.aggregate(n=Count("id"), q=Sum("turns"), shown=Sum("products_shown"), up=Sum("feedback_up"), down=Sum("feedback_down"),
                             buyers=Count("id", filter=Q(customer_id__isnull=False)))
        rated = (agg["up"] or 0) + (agg["down"] or 0)
        cost = sum((cost_usd(c) for c in week.only("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")), Decimal(0))
        return [
            ui.stat_card("Suhbatlar (7 kun)", agg["n"] or 0, "#8b5cf6", "fa-comments", f"{agg['q'] or 0} ta savol"),
            ui.stat_card("Ko'rsatilgan mahsulotlar", agg["shown"] or 0, "#22c55e", "fa-box-open", f"{agg['buyers'] or 0} ta suhbat — ro'yxatdan o'tgan mijoz"),
            ui.stat_card("Foydali javoblar", f"{round((agg['up'] or 0) * 100 / rated)}%" if rated else "—", "#0ea5e9", "fa-thumbs-up", f"👍 {agg['up'] or 0} · 👎 {agg['down'] or 0}", "?tab=down"),
            ui.stat_card("API xarajati (7 kun)", f"${cost:.2f}", "#f59e0b", "fa-coins", settings.ASSISTANT_MODEL),
        ]

    def nz_row(self, c):
        rating = ui.muted() if not (c.feedback_up or c.feedback_down) else format_html("👍 {} · 👎 {}", c.feedback_up, c.feedback_down)
        who = ui.chip("mijoz", "#22c55e", "fa-user") if c.customer_id else ui.chip("mehmon", "#64748b", "fa-user-secret")
        return [
            format_html("<b>{}</b><small>{} · {}{}</small>", c.last_message or "—", c.locale.upper(), c.channel, " · ⚠️ xato" if c.errors else ""),
            who, c.products_shown or ui.muted("0"), rating, format_html("{}<small>{}</small>", ui.ago(c.updated_at), ui.local(c.created_at)), c.turns,
        ]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        conv = get_object_or_404(AssistantConversation, pk=object_id)
        customer = None
        if conv.customer_id:
            from apps.identity.infrastructure.models import User

            customer = User.objects.filter(id=conv.customer_id).first()
        return render(request, "admin/assistant/conversation.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": f"AI suhbat · {ui.local(conv.created_at)}",
            "c": conv, "customer": customer, "cost": cost_usd(conv), "model": settings.ASSISTANT_MODEL,
        })


# ---------------------------------------------------------------- AI bilimlar bazasi

from django import forms  # noqa: E402

from apps.assistant.infrastructure.models import KnowledgeEntry  # noqa: E402
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin  # noqa: E402

TOPIC_STYLE = {"faq": ("#2563eb", "fa-circle-question"), "policy": ("#0d9488", "fa-scale-balanced"), "usage": ("#7c3aed", "fa-flask"),
               "product": ("#ea580c", "fa-box"), "promo": ("#db2777", "fa-bullhorn"), "branch": ("#16a34a", "fa-store"), "other": ("#64748b", "fa-tag")}


class KnowledgeForm(forms.ModelForm):
    class Meta:
        model = KnowledgeEntry
        fields = ("topic", "title", "questions", "keywords", "answer_uz", "answer_ru", "answer_en", "priority", "valid_until", "is_active")
        widgets = {
            "questions": forms.Textarea(attrs={"rows": 4, "placeholder": "yetkazib berish qancha turadi\nдоставка сколько стоит\nhow much is delivery"}),
            "answer_uz": forms.Textarea(attrs={"rows": 6}), "answer_ru": forms.Textarea(attrs={"rows": 6}), "answer_en": forms.Textarea(attrs={"rows": 6}),
            "valid_until": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


@admin.register(KnowledgeEntry)
class KnowledgeEntryAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = KnowledgeForm
    list_display = ("title", "topic", "priority", "uses", "is_active")
    list_filter = ("topic", "is_active")
    search_fields = ("title", "questions", "keywords", "answer_uz", "answer_ru", "answer_en")
    ordering = ("-priority", "title")
    actions = None
    fieldsets = (
        ("Bilim", {"fields": ("topic", "title", "questions", "keywords")}),
        ("Javob", {"fields": ("answer_uz", "answer_ru", "answer_en")}),
        ("Sozlamalar", {"fields": ("priority", "valid_until", "is_active")}),
    )
    nz_icon, nz_tone, nz_title = "fa-brain", "#7c3aed", "AI bilimlar bazasi"
    nz_subtitle = ("AI maslahatchini o'qiting: yetkazib berish, to'lov, aksiyalar, mahsulotlarni qo'llash va filiallar haqidagi rasmiy javoblaringiz. "
                   "Maslahatchi shu javoblarni mijozning tilida (o'zbek, rus, ingliz) ishlatadi; mahsulot, narx, qoldiq va filiallarni esa o'zi katalogdan o'qiydi.")
    nz_columns = (("Bilim", ""), ("Mavzu", ""), ("Tillar", ""), ("Holat", ""), ("Ishlatildi", "r"))
    nz_grid = "minmax(260px,3fr) minmax(170px,1.2fr) 150px 130px 90px"
    nz_search = "Savol, kalit so'z yoki javob…"
    nz_empty = ("Hali bilim yo'q", "«Qo'shish» bilan birinchi savol-javobni kiriting.")
    nz_sorts = (("Muhimlik", ""), ("Ko'p ishlatilgan", "-5"), ("Nom", "1"))

    def nz_tabs(self, request):
        counts = dict(KnowledgeEntry.objects.values_list("topic").annotate(n=Count("id")))
        return ui.tabs_for(request, "topic__exact", [("", "Hammasi", sum(counts.values()))] + [(k, str(label), counts.get(k, 0)) for k, label in KnowledgeEntry.TOPICS if counts.get(k)],
                           {k: v[0] for k, v in TOPIC_STYLE.items()})

    def nz_stats(self, request):
        from apps.assistant.infrastructure import tts

        agg = KnowledgeEntry.objects.aggregate(n=Count("id", filter=Q(is_active=True)), uses=Sum("uses"), no_ru=Count("id", filter=Q(answer_ru="")), no_en=Count("id", filter=Q(answer_en="")))
        return [ui.stat_card("Faol bilimlar", agg["n"], "#7c3aed", "fa-brain"), ui.stat_card("Javoblarda ishlatildi", agg["uses"] or 0, "#16a34a", "fa-comments"),
                ui.stat_card("Tarjimasi yo'q", (agg["no_ru"] or 0) + (agg["no_en"] or 0), "#f59e0b", "fa-language", "ru/en bo'sh — o'zbekcha javob ishlatiladi"),
                ui.stat_card("Ovozli o'qish", "Yoqilgan" if tts.enabled() else "O'chiq", "#0ea5e9" if tts.enabled() else "#94a3b8", "fa-volume-high",
                             "Azure: Madina / Sardor" if tts.enabled() else "AZURE_SPEECH_KEY kerak")]

    def nz_hero_actions(self, request):
        from django.urls import reverse

        return [{"label": "AI suhbatlar", "url": reverse("admin:assistant_assistantconversation_changelist"), "icon": "fa-comments"},
                {"label": "Yangi bilim", "url": reverse("admin:assistant_knowledgeentry_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, e):
        color, icon = TOPIC_STYLE.get(e.topic, ("#64748b", "fa-tag"))
        q = [x for x in (e.questions or "").splitlines() if x.strip()][:2]
        title = format_html("<b>{}</b><br><small>{}</small>", e.title, " · ".join(q) or e.answer_uz[:90])
        langs = format_html("{} {} {}", ui.chip("UZ", "#16a34a"), ui.chip("RU", "#16a34a" if e.answer_ru else "#cbd5e1"), ui.chip("EN", "#16a34a" if e.answer_en else "#cbd5e1"))
        today = timezone.localdate()
        if not e.is_active:
            state = ui.chip("O'chiq", "#94a3b8", "fa-circle-pause")
        elif e.valid_until and e.valid_until < today:
            state = ui.chip("Muddati o'tgan", "#f59e0b", "fa-clock")
        else:
            state = ui.chip("Faol", "#16a34a", "fa-circle-check")
        return [title, ui.chip(e.get_topic_display(), color, icon), langs, state, format_html("<b>{}</b>", e.uses)]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Savol shakllarini mijozlar qanday yozsa, shunday kiriting (uch tilda ham bo'ladi). Javob qisqa va aniq bo'lsin — maslahatchi uni o'zi moslab beradi."}
        return {"title": obj.title, "subtitle": f"{obj.get_topic_display()} · {obj.uses} marta ishlatilgan"}

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.get_full_name() or request.user.get_username()
        super().save_model(request, obj, form, change)
