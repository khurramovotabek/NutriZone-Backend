"""
Presentation helpers shared by the Identity dashboard pages (Foydalanuvchilar, Sessiyalar, Qurilmalar, Rollar,
Ruxsatlar, Foydalanuvchi rollari): avatars, "3 soat oldin" times, a small User-Agent reader, session states and
human (Uzbek) labels for permission codes. Read-only formatting -- no queries beyond what callers pass in.
"""
from __future__ import annotations

import re

from django.utils import timezone
from django.utils.html import format_html

from apps.platform.infrastructure.premium_admin import (  # noqa: F401 -- re-exported for the Identity admins
    TZ,
    PremiumListMixin,
    ago,
    avatar,
    avatar_url,
    chip,
    initials,
    local,
    muted,
    stat_card,
    tabs_for,
    tone,
    user_cell,
)

USER_STATUS = {"active": ("Faol", "#16a34a", "fa-circle-check"), "blocked": ("Bloklangan", "#dc2626", "fa-ban"),
               "pending_verification": ("Tasdiqlanmagan", "#d97706", "fa-hourglass-half")}
LANGUAGE = {"uz": "O'zbekcha", "ru": "Русский", "en": "English"}
GOAL = {"muscle_gain": "Mushak massasi", "fat_loss": "Ozish", "healthy_lifestyle": "Sog'lom turmush"}
DEVICE = {"web": ("Veb-sayt", "fa-globe"), "mobile": ("Mobil ilova", "fa-mobile-screen"), "pos": ("Kassa (POS)", "fa-cash-register")}


def status_pill(status: str) -> str:
    label, color, icon = USER_STATUS.get(status, (status, "#64748b", "fa-circle"))
    return format_html('<span class="nzi-pill" style="--t:{}"><i class="fas {}" aria-hidden="true"></i> {}</span>', color, icon, label)


# ---------------------------------------------------------------- user agent

_BROWSERS = (("Edg/", "Edge", "fa-edge"), ("OPR/", "Opera", "fa-opera"), ("YaBrowser/", "Yandex", "fa-yandex"), ("SamsungBrowser/", "Samsung Internet", "fa-globe"),
             ("Telegram", "Telegram", "fa-telegram"), ("Chrome/", "Chrome", "fa-chrome"), ("CriOS/", "Chrome", "fa-chrome"), ("FxiOS/", "Firefox", "fa-firefox-browser"),
             ("Firefox/", "Firefox", "fa-firefox-browser"), ("Safari/", "Safari", "fa-safari"))
_OS = (("iPhone", "iOS", "fa-apple"), ("iPad", "iPadOS", "fa-apple"), ("Android", "Android", "fa-android"), ("Windows", "Windows", "fa-windows"),
       ("Mac OS X", "macOS", "fa-apple"), ("Macintosh", "macOS", "fa-apple"), ("CrOS", "ChromeOS", "fa-chrome"), ("Linux", "Linux", "fa-linux"))
_TOOLS = ("node", "curl", "python-requests", "okhttp", "axios", "go-http-client", "postman")


_BRAND_ICONS = {"fa-chrome", "fa-edge", "fa-opera", "fa-yandex", "fa-telegram", "fa-firefox-browser", "fa-safari", "fa-android", "fa-apple", "fa-windows", "fa-linux"}


def icon_family(icon: str) -> str:
    """Font Awesome family for an icon name: brand logos are "fab", everything else "fas"."""
    return "fab" if icon in _BRAND_ICONS else "fas"


def parse_ua(ua: str | None) -> dict:
    """{"browser", "os", "icon", "label", "tool"} from a User-Agent string; `tool` = a server / script, not a person's browser."""
    ua = (ua or "").strip()
    if not ua:
        return {"browser": "", "os": "", "icon": "fa-circle-question", "label": "Noma'lum", "tool": False}
    low = ua.lower()
    if any(low.startswith(t) for t in _TOOLS):
        name = re.split(r"[/ ]", ua)[0]
        return {"browser": name, "os": "", "icon": "fa-server", "label": f"{name} (server)", "tool": True}
    browser = next(((name, icon) for key, name, icon in _BROWSERS if key in ua), ("Brauzer", "fa-globe"))
    os_name = next((name for key, name, _icon in _OS if key in ua), "")
    mobile = any(k in ua for k in ("Mobile", "iPhone", "Android"))
    return {"browser": browser[0], "os": os_name, "icon": browser[1], "label": " · ".join(x for x in (browser[0], os_name) if x), "tool": False, "mobile": mobile}


# ---------------------------------------------------------------- sessions

SESSION_STATE = {"active": ("Faol", "#16a34a"), "idle": ("Faol emas", "#0ea5e9"), "expired": ("Muddati tugagan", "#94a3b8"), "revoked": ("Yopilgan", "#dc2626")}
IDLE_DAYS = 7


def session_state(s) -> str:
    now = timezone.now()
    if s.revoked_at:
        return "revoked"
    if s.expires_at <= now:
        return "expired"
    if s.last_activity and (now - s.last_activity).days >= IDLE_DAYS:
        return "idle"
    return "active"


# ---------------------------------------------------------------- permissions

MODULES = {
    "cart": ("Savat", "fa-cart-shopping", "#2563eb"), "pricing": ("Narxlar", "fa-tags", "#0891b2"), "ordering": ("Buyurtmalar", "fa-receipt", "#9333ea"),
    "wallet": ("Hamyon", "fa-wallet", "#16a34a"), "loyalty": ("Loyalty", "fa-coins", "#d97706"), "reviews": ("Sharhlar", "fa-star", "#eab308"),
    "notifications": ("Bildirishnomalar", "fa-bell", "#db2777"), "chat": ("Chat", "fa-comments", "#4f46e5"), "identity": ("Akkaunt", "fa-user-shield", "#0d9488"),
    "stores": ("Do'konlar", "fa-store", "#ea580c"), "products": ("Mahsulotlar", "fa-box", "#64748b"), "payments": ("To'lovlar", "fa-credit-card", "#0ea5e9"),
}
RESOURCES = {
    "item": "savat mahsuloti", "line_item": "savat qatori", "price_reference": "narx ma'lumoti", "snapshot": "narx surati", "validation": "savat tekshiruvi",
    "checkout": "rasmiylashtirish", "order": "buyurtma", "wallet": "hamyon", "ledger": "hamyon tarixi", "membership": "a'zolik", "tier": "daraja",
    "review": "sharh", "media": "sharh rasmlari", "notification": "bildirishnoma", "preference": "bildirishnoma sozlamalari", "conversation": "suhbat",
    "message": "xabar", "session": "sessiya", "user": "foydalanuvchi", "role": "rol",
}
ACTIONS = {
    "view": "ko'rish", "view_own": "o'zinikini ko'rish", "create": "qo'shish", "update": "o'zgartirish", "edit": "tahrirlash", "delete": "o'chirish",
    "manage": "boshqarish", "manage_own": "o'zinikini boshqarish", "execute": "bajarish", "send": "yuborish", "issue": "yaratish",
    "view_history": "tarixini ko'rish", "revoke_any": "istalganini yopish", "assign": "biriktirish",
}


def module_of(code: str) -> tuple[str, str, str, str]:
    """(module key, label, icon, colour) of a permission code like "cart.item.create"."""
    key = (code or "").split(".")[0]
    label, icon, color = MODULES.get(key, (key.replace("_", " ").title() or "Boshqa", "fa-key", "#64748b"))
    return key, label, icon, color


def permission_label(code: str, description: str = "") -> str:
    """A human sentence for a permission: the stored description when it says more than the code, else "<resource> — <action>"."""
    if description and description.strip() and description.strip() != code:
        return description.strip()
    parts = (code or "").split(".")
    if len(parts) < 3:
        return code
    resource, action = parts[1], ".".join(parts[2:])
    res = RESOURCES.get(resource, resource.replace("_", " "))
    act = ACTIONS.get(action, action.replace("_", " "))
    return f"{res[:1].upper()}{res[1:]} — {act}"


