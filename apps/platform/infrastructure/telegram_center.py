"""
Dashboard → Telegram botlar markazi (/django-admin/telegram/status/): the three bots in one place.

  bots        @nutrizonebot (shop), Orders bot, Analytics bot -- configured or not (never the token itself), their
              @username, and real activity from the rows the bots keep: linked customers, checkouts in the bot,
              orders placed through Telegram, posts in the Orders channel / to branch owners, subscribers
  subscribers who started the staff bots and what each may see (all branches, or which store they own)
  preview     what a bot message looks like right now -- the same Rich Message documents the bots send
              (shop_rich / orders_rich / analytics_rich), turned into page HTML with the pictures inlined
  check       a live getMe for each configured token (on request only)
"""
from __future__ import annotations

import base64
import re
from datetime import timedelta
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

BOTS = (
    {"key": "shop", "title": "Mijozlar boti", "icon": "fa-bag-shopping", "tone": "#0ea5e9", "token": "TELEGRAM_BOT_TOKEN", "username": "TELEGRAM_BOT_USERNAME",
     "about": "Katalog, savat, buyurtma, coins, mahsulot topib berish, do'konlar, yangiliklar, operator bilan chat"},
    {"key": "orders", "title": "Orders bot", "icon": "fa-receipt", "tone": "#f59e0b", "token": "TELEGRAM_ORDERS_BOT_TOKEN", "username": "TELEGRAM_ORDERS_BOT_USERNAME",
     "about": "Onlayn buyurtma va kassa savdolari postlari, tasdiqlash tugmalari, filial egalariga"},
    {"key": "analytics", "title": "Analytics bot", "icon": "fa-chart-line", "tone": "#8b5cf6", "token": "TELEGRAM_ANALYTICS_BOT_TOKEN", "username": "TELEGRAM_ANALYTICS_BOT_USERNAME",
     "about": "Kunlik/haftalik hisobot, grafiklar, reja, nazorat ogohlantirishlari"},
)
PREVIEWS = (
    {"kind": "showcase", "bot": "shop", "label": "Vitrina", "icon": "fa-store", "private": False},
    {"kind": "sale", "bot": "shop", "label": "Aksiyalar", "icon": "fa-tags", "private": False},
    {"kind": "product", "bot": "shop", "label": "Mahsulot sahifasi", "icon": "fa-box-open", "private": False},
    {"kind": "customer_order", "bot": "shop", "label": "Mijoz buyurtmasi", "icon": "fa-user-check", "private": True},
    {"kind": "order_post", "bot": "orders", "label": "Buyurtma posti", "icon": "fa-truck-fast", "private": True},
    {"kind": "sale_post", "bot": "orders", "label": "Kassa savdosi", "icon": "fa-cash-register", "private": True},
    {"kind": "analytics", "bot": "analytics", "label": "Bugungi hisobot", "icon": "fa-chart-pie", "private": True},
)


def gateway_live() -> bool:
    return getattr(settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") == "live"


def _configured(name: str) -> bool:
    return bool(getattr(settings, name, None))


def bots() -> list[dict]:
    """Each bot with its configuration state and real activity figures."""
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel
    from apps.telegram_bot.infrastructure.models import (
        TelegramAfterSalesChannelMessage,
        TelegramBotSubscriber,
        TelegramCheckoutConfirmation,
        TelegramOrderChannelMessage,
        TelegramPosSaleChannelMessage,
        TelegramStorePost,
    )

    now = timezone.now()
    week, month = now - timedelta(days=7), now - timedelta(days=30)
    subs = {r["bot"]: r for r in TelegramBotSubscriber.objects.values("bot").annotate(total=Count("id"), active=Count("id", filter=Q(is_active=True)))}
    linked = User.objects.exclude(telegram_user_id=None)
    tg_orders = OrderModel.objects.filter(channel="telegram").exclude(status="draft")
    stats = {
        "shop": [("Telegram ulangan mijozlar", linked.count(), f"+{linked.filter(telegram_linked_at__gte=week).count()} shu hafta"),
                 ("Botda rasmiylashtirildi", TelegramCheckoutConfirmation.objects.exclude(order_number=None).count(),
                  f"{TelegramCheckoutConfirmation.objects.exclude(order_number=None).filter(created_at__gte=month).count()} ta 30 kunda"),
                 ("Telegram buyurtmalari", tg_orders.count(), f"{tg_orders.filter(created_at__gte=month).count()} ta 30 kunda")],
        "orders": [("Buyurtma postlari", TelegramOrderChannelMessage.objects.count(), "kanalga yuborilgan onlayn buyurtmalar"),
                   ("Kassa savdosi postlari", TelegramPosSaleChannelMessage.objects.count(), f"{TelegramPosSaleChannelMessage.objects.filter(created_at__gte=week).count()} ta shu hafta"),
                   ("Filial egalariga", TelegramStorePost.objects.filter(bot="orders").count(), "egalarning shaxsiy chatiga"),
                   ("Qaytarish / servis", TelegramAfterSalesChannelMessage.objects.count(), "kanaldagi murojaatlar")],
        "analytics": [("Obunachilar", subs.get("analytics", {}).get("active", 0), f"jami {subs.get('analytics', {}).get('total', 0)}"),
                      ("Ruxsat ro'yxati", len(_allowlist()), "hamma filialni ko'radigan chatlar"),
                      ("Filial egalariga", TelegramStorePost.objects.filter(bot="analytics").count(), "yuborilgan hisobotlar")],
    }
    owners = branch_owners()
    stats["analytics"].append(("Ulangan filial egalari", f"{sum(1 for o in owners if o['tone'] == 'ok')} / {len(owners)}", "o'z filiali hisobotini oladi"))
    stats["orders"].append(("Obunachilar", subs.get("orders", {}).get("active", 0), f"jami {subs.get('orders', {}).get('total', 0)}"))
    out = []
    for b in BOTS:
        username = getattr(settings, b["username"], None) or ""
        out.append({**b, "configured": _configured(b["token"]), "username": username.lstrip("@"), "stats": stats[b["key"]],
                    "extra": _orders_chat() if b["key"] == "orders" else ""})
    return out


def _allowlist() -> list[str]:
    raw = getattr(settings, "TELEGRAM_ANALYTICS_CHAT_IDS", "") or ""
    return [c.strip() for c in str(raw).replace(";", ",").split(",") if c.strip()]


def _orders_chat() -> str:
    return "Buyurtmalar kanali ulangan" if getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", "") else "Buyurtmalar kanali ulanmagan"


def subscribers() -> list[dict]:
    """Staff-bot subscribers with what each may see (store ownership read live, like the bots do)."""
    from apps.identity.infrastructure.models import User
    from apps.stores.infrastructure.models import Store
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber, TelegramStaffMember

    rows = list(TelegramBotSubscriber.objects.order_by("bot", "-last_seen_at")[:200])
    tg_ids = {r.telegram_user_id or r.chat_id for r in rows}
    users = {u.telegram_user_id: u for u in User.objects.filter(telegram_user_id__in=tg_ids).only("id", "telegram_user_id", "full_name")}
    owned: dict = {}
    for s in Store.objects.filter(owner_id__in=[u.id for u in users.values()]).only("name", "owner_id"):
        owned.setdefault(s.owner_id, []).append(s.name)
    staff = set(TelegramStaffMember.objects.filter(is_active=True).values_list("telegram_user_id", flat=True))
    allow = set(_allowlist())
    out = []
    for r in rows:
        tid = r.telegram_user_id or r.chat_id
        user = users.get(tid)
        stores = owned.get(user.id, []) if user else []
        everything = (r.bot == "analytics" and str(r.chat_id) in allow) or (r.bot == "orders" and tid in staff)
        out.append({"bot": "Orders bot" if r.bot == "orders" else "Analytics bot", "name": r.display_name or (user.full_name if user else "—"),
                    "username": r.username, "access": "Hamma filiallar" if everything else (", ".join(stores) if stores else "Ruxsat yo'q"),
                    "tone": "ok" if everything or stores else "bad", "active": r.is_active, "started": r.started_at, "seen": r.last_seen_at})
    return out


def branch_owners() -> list[dict]:
    """Every selling branch and whether its owner gets their own analytics: owner set → Telegram linked → bot started."""
    from apps.identity.infrastructure.models import User
    from apps.stores.infrastructure.models import Store
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    stores = list(Store.objects.filter(kind="store").exclude(status="inactive").order_by("name").only("id", "name", "owner_id"))
    users = {u.id: u for u in User.objects.filter(id__in=[s.owner_id for s in stores if s.owner_id]).only("id", "full_name", "phone_number", "telegram_user_id")}
    started = dict(TelegramBotSubscriber.objects.filter(bot="analytics", telegram_user_id__in=[u.telegram_user_id for u in users.values() if u.telegram_user_id])
                   .values_list("telegram_user_id", "is_active"))
    from apps.notifications.infrastructure.models import NotificationModel

    invited = {}
    for uid, at in NotificationModel.objects.filter(kind="store_owner_analytics", recipient_id__in=list(users)).order_by("created_at").values_list("recipient_id", "created_at"):
        invited[uid] = at
    out = []
    for s in stores:
        u = users.get(s.owner_id)
        if u is None:
            state, tone, hint = "Ega tayinlanmagan", "bad", "Dashboard → Filiallar → Ega maydonini to'ldiring"
        elif not u.telegram_user_id:
            state, tone, hint = "Telegram ulanmagan", "bad", "Ega mijoz botida ro'yxatdan o'tishi kerak"
        elif u.telegram_user_id not in started:
            when = invited.get(u.id)
            state, tone = "Botni ochmagan", "warn"
            hint = f"Taklif {when.astimezone(ZoneInfo('Asia/Tashkent')).strftime('%d.%m %H:%M')} da yuborilgan — Analytics botda /start bossin" if when else "Taklif yuboring — ega Analytics botda /start bossin"
        elif not started[u.telegram_user_id]:
            state, tone, hint = "Botni bloklagan", "bad", "Ega botni qayta ochishi kerak"
        else:
            state, tone, hint = "Ulangan", "ok", "Har kuni filial hisobotini oladi"
        out.append({"id": str(s.id), "store": s.name, "owner": (u.full_name or u.phone_number) if u else "—", "state": state, "tone": tone, "hint": hint,
                    "can_invite": bool(u and u.telegram_user_id) and tone != "ok"})
    return out


def invite_owner(store_id: str) -> tuple[bool, str]:
    """Dashboard button: send (again) the branch owner the inbox + Telegram invitation into NutriZoneAnalyticsBot."""
    from apps.notifications.infrastructure.notify import create_now, send_telegram
    from apps.stores.infrastructure.models import Store
    from apps.stores.infrastructure.owner_invite import analytics_bot_link

    store = Store.objects.filter(pk=store_id, kind="store").select_related("owner").first() if store_id else None
    if store is None or store.owner is None:
        return False, "Filial yoki uning egasi topilmadi."
    link = analytics_bot_link()
    if not link:
        return False, "Analytics bot sozlanmagan (TELEGRAM_ANALYTICS_BOT_TOKEN / _USERNAME)."
    row = create_now(store.owner_id, "store_owner_analytics", {"store": store.name}, link=link)
    delivered = bool(row and store.owner.telegram_user_id and send_telegram(row))
    who = store.owner.full_name or store.owner.phone_number
    return True, f"{store.name}: taklif {who} ga yuborildi" + (" (Telegram + sayt)." if delivered else " (saytdagi bildirishnomalarda; Telegram'ga yetmadi).")


def check(timeout: float = 8) -> dict:
    """getMe for every configured token: {key: {"ok", "username", "name"} | {"ok": False, "error"}}."""
    base = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
    out = {}
    for b in BOTS:
        token = getattr(settings, b["token"], None)
        if not token:
            out[b["key"]] = {"ok": False, "error": "Token kiritilmagan"}
            continue
        try:
            body = requests.get(f"{base}/bot{token}/getMe", timeout=timeout).json()
        except (requests.RequestException, ValueError) as exc:
            out[b["key"]] = {"ok": False, "error": f"Telegram bilan aloqa yo'q ({exc.__class__.__name__})"}
            continue
        if body.get("ok"):
            me = body.get("result") or {}
            out[b["key"]] = {"ok": True, "username": me.get("username", ""), "name": me.get("first_name", "")}
        else:
            out[b["key"]] = {"ok": False, "error": str(body.get("description") or "Token rad etildi")[:120]}
    return out


# ---------------------------------------------------------------- previews


def _doc_for(kind: str):
    """(RichDoc, inline keyboard) built from the newest real data, or (None, None) when there is nothing to show."""
    from apps.ordering.infrastructure.models import OrderModel
    from apps.pos.infrastructure.models import SaleModel
    from apps.products.infrastructure.models import Product
    from apps.telegram_bot.infrastructure import orders_rich, shop_rich

    if kind == "showcase":
        return shop_rich.showcase_doc("uz"), [[{"text": "🔥 Ko'p sotilganlar"}, {"text": "🆕 Yangilari"}], [{"text": "🏠 Bosh menyu"}]]
    if kind == "sale":
        return shop_rich.sale_doc("uz"), [[{"text": "🃏 Kartalarda ko'rish"}], [{"text": "⬅️ Orqaga"}, {"text": "🏠 Bosh menyu"}]]
    if kind == "product":
        product = Product.objects.filter(status="published").order_by("-created_at").first()
        return (shop_rich.product_doc(product.id, "uz"), [[{"text": "🛒 Savatcha"}, {"text": "📦 Mahsulotlar"}]]) if product else (None, None)
    if kind == "customer_order":
        o = OrderModel.objects.exclude(status="draft").exclude(customer_id=None).order_by("-created_at").first()
        return (shop_rich.order_doc(o.order_number, o.customer_id, "uz"), [[{"text": "⬅️ Orqaga"}, {"text": "🏠 Bosh menyu"}]]) if o else (None, None)
    if kind == "order_post":
        o = OrderModel.objects.exclude(status="draft").order_by("-created_at").first()
        if not o:
            return None, None
        doc, _meta = orders_rich.order_doc(o.id)
        return doc, [[{"text": "✅ Tasdiqlash"}, {"text": "❌ Bekor qilish"}]]
    if kind == "sale_post":
        s = SaleModel.objects.filter(status__in=("completed", "refunded")).order_by("-completed_at").first()
        if not s:
            return None, None
        doc, keyboard = orders_rich.sale_doc(s.id)
        return doc, keyboard
    if kind == "analytics":
        from apps.platform.infrastructure import business_analytics as ba
        from apps.telegram_bot.infrastructure import analytics_rich

        return analytics_rich.build_doc(ba.build(ba.period("today"))), [[{"text": "📅 Bugun"}, {"text": "🗓 Hafta"}, {"text": "📆 Oy"}]]
    return None, None


_BUTTON = re.compile(r'<tg-button type="(\w+)"([^>]*)>(.*?)</tg-button>', re.S)


def _button(m) -> str:
    url = re.search(r'url="([^"]*)"', m.group(2))
    if m.group(1) in ("url", "web_app") and url and url.group(1).startswith("https://"):
        return f'<a class="tgp-btn" href="{url.group(1)}" target="_blank" rel="noopener">{m.group(3)}</a>'
    return f'<span class="tgp-btn">{m.group(3)}</span>'


_MAP = re.compile(r'<tg-map lat="([-0-9.]+)" long="([-0-9.]+)" zoom="\d+"/>')


def to_page_html(doc) -> str:
    """A Rich Message document as page HTML: tg://photo links become inline images, Telegram-only tags become
    styled elements (collage grid, map link, button rows). The document's text is escaped by rich.py's helpers."""
    html = doc.html
    for image_id, png in doc.images.items():
        html = html.replace(f'src="tg://photo?id={image_id}"', f'src="data:image/png;base64,{base64.b64encode(png).decode()}" alt=""')
    html = _MAP.sub(lambda m: f'<a class="tgp-map" href="https://maps.google.com/?q={m.group(1)},{m.group(2)}" target="_blank" rel="noopener">'
                              f'<i class="fas fa-map-location-dot" aria-hidden="true"></i> {m.group(1)}, {m.group(2)}</a>', html)
    html = re.sub(r"<tg-collage>", '<div class="tgp-collage">', html).replace("</tg-collage>", "</div>")
    html = re.sub(r'<tg-button-row align="\w+">', '<div class="tgp-row">', html).replace("</tg-button-row>", "</div>")
    html = _BUTTON.sub(_button, html)
    html = re.sub(r'<tg-time [^>]*>', "<span>", html).replace("</tg-time>", "</span>")
    html = re.sub(r"<table bordered striped( compact)?>", '<table class="tgp-table">', html)
    return html


def preview(kind: str) -> dict | None:
    doc, keyboard = _doc_for(kind)
    if doc is None:
        return None
    return {"html": to_page_html(doc), "keyboard": [[(b.get("text") or "") for b in row] for row in keyboard or []], "size": len(doc.html), "images": len(doc.images)}
