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
