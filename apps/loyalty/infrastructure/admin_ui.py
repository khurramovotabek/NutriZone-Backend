"""
Presentation helpers for the Loyalty & Wallet dashboard pages: Uzbek labels / icons / colours for ledger kinds,
referral states and channels, tier badges and coin amounts. Formatting only.
"""
from __future__ import annotations

from django.utils.html import format_html

TIER_GLYPH = {"bronze": "🥉", "silver": "🥈", "gold": "🥇", "platinum": "✦", "diamond": "💎", "elite": "🛡️", "legend": "🔥", "vip": "👑"}
KIND = {  # ledger kind -> (label, icon, colour)
    "earn": ("Keshbek (buyurtma)", "fa-cart-shopping", "#16a34a"),
    "referral": ("Referal bonusi", "fa-user-plus", "#9333ea"),
    "refund": ("Qaytarildi (bekor qilingan to'lov)", "fa-rotate-left", "#0891b2"),
    "adjustment": ("Qo'lda tuzatish", "fa-hand", "#6366f1"),
    "spend": ("Xaridda ishlatildi", "fa-bag-shopping", "#ea580c"),
    "reversal": ("Keshbek qaytarib olindi", "fa-ban", "#dc2626"),
    "expiry": ("Muddati tugadi", "fa-hourglass-end", "#64748b"),
}
REFERRAL_STATUS = {"pending": ("Birinchi buyurtma kutilmoqda", "#d97706"), "rewarded": ("Mukofotlangan", "#16a34a"), "void": ("Bekor qilingan", "#94a3b8")}
CHANNEL = {"web": ("Veb-sayt", "fa-globe"), "telegram": ("Telegram bot", "fa-paper-plane"), "manual": ("Qo'lda", "fa-hand")}
TIER_CHANGE = {"auto": ("Avtomatik", "#16a34a"), "manual": ("Admin belgiladi", "#9333ea"), "cleared": ("Qo'lda daraja olib tashlandi", "#64748b")}


def som(value) -> str:
    return f"{int(value or 0):,}".replace(",", " ")


def coins(value, signed: bool = False) -> str:
    v = int(value or 0)
    if signed:
        color = "#16a34a" if v > 0 else "#dc2626"
        return format_html('<b class="nzl-coin" style="color:{}">{}{}</b>', color, "+" if v > 0 else "−", som(abs(v)))
    return format_html('<b class="nzl-coin">{}</b>', som(v))


def tier_chip(tier, manual: bool = False, reason: str = "") -> str:
    if tier is None:
        return format_html('<span class="nzi-muted">{}</span>', "—")
    pin = format_html(' <span class="nzl-pin" title="{}"><i class="fas fa-thumbtack" aria-hidden="true"></i></span>', reason or "Admin belgilagan") if manual else ""
    return format_html('<span class="nzl-tier" style="--t:{}"><span>{}</span> {} <small>{}%</small>{}</span>',
                       tier.color, TIER_GLYPH.get(tier.icon, "★"), tier.name, f"{tier.percent.normalize():f}", pin)


def kind_chip(kind: str) -> str:
    label, icon, color = KIND.get(kind, (kind, "fa-circle", "#64748b"))
    return format_html('<span class="nzi-chip" style="--t:{}"><i class="fas {}" aria-hidden="true"></i> {}</span>', color, icon, label)
