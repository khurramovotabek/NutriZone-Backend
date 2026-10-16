"""
Dashboard → Bildirishnomalar → Xabar yuborish: one announcement to many customers at once.

The composer picks an audience (live count), writes the text in Uzbek (Russian/English optional -- empty falls
back to Uzbek), an optional link, and the channels (in-app inbox, Telegram). Sending creates a
`NotificationBroadcast` and fans it out on a Celery worker (notify.run_broadcast); the page then follows its progress.
"""
from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.notifications.infrastructure import notify
from apps.notifications.infrastructure.models import BroadcastAudience, NotificationBroadcast
from apps.telegram_bot.infrastructure.rich_text_field import TelegramRichTextField
from apps.telegram_bot.infrastructure.telegram_html import to_plain

AUDIENCES = [
    ("all", "Barcha mijozlar", "fa-users", "#2563eb", "Bloklanmagan barcha mijozlar"),
    ("active", "Faol mijozlar", "fa-user-check", "#16a34a", "Telefoni tasdiqlangan mijozlar"),
    ("buyers", "Xarid qilganlar", "fa-bag-shopping", "#f59e0b", "Onlayn yoki do'kondan xarid qilganlar"),
    ("telegram", "Telegram ulanganlar", "fa-paper-plane", "#0ea5e9", "Botga ulangan mijozlar"),
    ("new", "Yangi mijozlar", "fa-user-plus", "#8b5cf6", "So'nggi 30 kunda ro'yxatdan o'tganlar"),
    ("tier", "Loyalty darajasi", "fa-crown", "#db2777", "Tanlangan darajadagi mijozlar"),
    ("segment", "Mijozlar segmenti", "fa-chart-pie", "#f97316", "VIP, doimiy, ketish xavfi, yo'qotilgan…"),
    ("phone", "Bitta mijoz", "fa-mobile-screen", "#0d9488", "Telefon raqami bo'yicha (sinov uchun qulay)"),
]

LINKS = [
    ("", "Havolasiz"),
    ("/products", "Mahsulotlar katalogi"),
    ("/loyalty", "Bonuslar (coin) sahifasi"),
    ("/account/loyalty", "Mening bonuslarim"),
    ("/orders", "Buyurtmalarim"),
    ("/stores", "Do'konlar"),
    ("/brands", "Brendlar"),
    ("/", "Bosh sahifa"),
]


class BroadcastForm(forms.Form):
    audience = forms.ChoiceField(choices=BroadcastAudience.choices, initial="all")
    target_tier = forms.CharField(required=False)
    target_segment = forms.CharField(required=False)
    target_phone = forms.CharField(required=False, max_length=20)
    title_uz = forms.CharField(max_length=150, label="Sarlavha")
    # Rich text (bold, links, spoilers...) -- Telegram gets the formatting, the in-app inbox the plain text.
    body_uz = TelegramRichTextField(label="Matn", placeholder="Masalan: 🔥 Bugun barcha proteinlarga -15% chegirma!")
    title_ru = forms.CharField(max_length=150, required=False)
    body_ru = TelegramRichTextField(required=False, placeholder="Текст на русском (необязательно)")
    title_en = forms.CharField(max_length=150, required=False)
    body_en = TelegramRichTextField(required=False, placeholder="English text (optional)")
    link = forms.CharField(max_length=255, required=False)
    priority = forms.ChoiceField(choices=[("normal", "Oddiy"), ("high", "Muhim")], initial="normal")
    send_in_app = forms.BooleanField(required=False, initial=True)
    send_telegram = forms.BooleanField(required=False)

    def clean_link(self):
        link = (self.cleaned_data.get("link") or "").strip()
        if link and not link.startswith("/"):
            raise forms.ValidationError("Havola saytdagi sahifa bo'lishi kerak, masalan /products")
        return link

    def clean(self):
        data = super().clean()
        if not data.get("send_in_app") and not data.get("send_telegram"):
            raise forms.ValidationError("Kamida bitta kanalni tanlang: ilova ichida yoki Telegram.")
        audience = data.get("audience")
        if audience == "tier" and not data.get("target_tier"):
            self.add_error("target_tier", "Loyalty darajasini tanlang.")
        if audience == "segment" and not data.get("target_segment"):
            self.add_error("target_segment", "Segmentni tanlang.")
        if audience == "phone" and len("".join(c for c in (data.get("target_phone") or "") if c.isdigit())) < 9:
            self.add_error("target_phone", "Telefon raqamini to'liq kiriting.")
        return data

    def target(self) -> str:
        d = self.cleaned_data
        if d["audience"] == "segment":
            return d.get("target_segment", "")
        return d.get("target_tier", "") if d["audience"] == "tier" else d.get("target_phone", "") if d["audience"] == "phone" else ""

    def texts(self) -> dict:
        """Per language: `body` plain text (inbox), `html` the Telegram-formatted version. Empty ru/en fall back to Uzbek."""
        d = self.cleaned_data

        def lang(code: str, fallback: dict | None = None) -> dict:
            html = (d.get(f"body_{code}") or "").strip()
            title = (d.get(f"title_{code}") or "").strip()
            if fallback and not html:
                return {"title": title or fallback["title"], "body": fallback["body"], "html": fallback["html"]}
            return {"title": title or (fallback or {}).get("title", ""), "body": to_plain(html), "html": html}

        uz = lang("uz")
        return {"uz": uz, "ru": lang("ru", uz), "en": lang("en", uz)}


def _segments():
    from apps.platform.infrastructure import segments

    data = segments.snapshot()["segments"]
    return [{"code": c, "label": s["label"], "tone": s["tone"], "count": s["count"]} for c, s in data.items()]


def _tiers():
    from apps.loyalty.infrastructure.models import LoyaltyTier

    return list(LoyaltyTier.objects.filter(is_active=True).order_by("min_spend").values("slug", "name", "color"))


def _initial(request) -> dict:
    """Blank composer, `?audience=&phone=` shortcuts, or `?from=<broadcast id>` -- a copy of an earlier message to edit and resend."""
    initial = {"audience": request.GET.get("audience", "all"), "target_phone": request.GET.get("phone", ""), "target_segment": request.GET.get("segment", ""), "send_in_app": True}
    source = NotificationBroadcast.objects.filter(pk=request.GET.get("from")).first() if _uuid(request.GET.get("from")) else None
    if source is not None:
        texts = source.i18n or {"uz": {"title": source.title, "body": source.body}}
        for code in ("uz", "ru", "en"):
            initial[f"title_{code}"] = (texts.get(code) or {}).get("title", "")
            initial[f"body_{code}"] = (texts.get(code) or {}).get("html") or (texts.get(code) or {}).get("body", "")
        initial.update({"link": source.link, "audience": source.audience, "priority": source.priority if source.priority in ("normal", "high") else "normal",
                        "send_in_app": source.send_in_app, "send_telegram": source.send_telegram,
                        "target_tier": source.target if source.audience == "tier" else "", "target_segment": source.target if source.audience == "segment" else "", "target_phone": source.target if source.audience == "phone" else ""})
    return initial


def _uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def broadcast_view(request):
    if not request.user.has_perm("notifications.add_notificationbroadcast"):
        messages.error(request, "Xabar yuborish uchun ruxsat yo'q.")
        return HttpResponseRedirect(reverse("admin:index"))
    if request.method == "POST":
        form = BroadcastForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            recipients = notify.audience_queryset(d["audience"], form.target()).count()
            if recipients == 0:
                form.add_error(None, "Bu auditoriyada birorta ham mijoz yo'q.")
            else:
                texts = form.texts()
                b = NotificationBroadcast.objects.create(
                    kind="announcement", title=texts["uz"]["title"], body=texts["uz"]["body"], i18n=texts, link=d["link"],
                    audience=d["audience"], target=form.target(), priority=d["priority"], send_in_app=d["send_in_app"],
                    send_telegram=d["send_telegram"], recipients=recipients,
                    created_by=request.user.get_full_name() or request.user.get_username(),
                )
                notify.start_broadcast(b)
                messages.success(request, f"Xabar {recipients} ta mijozga yuborilmoqda.")
                return HttpResponseRedirect(reverse("admin:notifications_notificationbroadcast_change", args=[b.pk]))
    else:
        form = BroadcastForm(initial=_initial(request))
    return render(request, "admin/notifications/broadcast.html", {
        **admin.site.each_context(request), "title": "Xabar yuborish", "form": form, "audiences": AUDIENCES, "links": LINKS,
        "tiers": _tiers(), "segments": _segments(), "counts_url": reverse("admin:nz_notify_audience"),
        "history_url": reverse("admin:notifications_notificationbroadcast_changelist"),
    })


def audience_count_view(request):
    audience = request.GET.get("audience", "all")
    target = request.GET.get("target", "")
    qs = notify.audience_queryset(audience, target)
    total = qs.count()
    tg = qs.filter(telegram_user_id__isnull=False).count()
    sample = None
    if audience == "phone" and total == 1:
        u = qs.first()
        sample = u.full_name or u.phone_number
    return JsonResponse({"total": total, "telegram": tg, "sample": sample})


def urls():
    from django.urls import path

    return [
        path("notifications/send/", admin.site.admin_view(broadcast_view), name="nz_notify_send"),
        path("notifications/send/audience.json", admin.site.admin_view(audience_count_view), name="nz_notify_audience"),
    ]
