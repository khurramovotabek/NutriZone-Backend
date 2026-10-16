"""
Automatic posts to the shop's Telegram channel (@nutrizonepit): new products, discounts, back in stock.

Runs every 15 minutes (task telegram_bot.channel_autopost). Each event becomes a regular TelegramPost
(source new / sale / restock, unique dedupe_key) and is sent by posts.send -- so auto posts show up in
Dashboard → Telegram → Postlar with their delivery result, exactly like hand-made ones.
Guards: off until enabled; products published before it was enabled are never "new"; quiet hours;
at most `max_per_run` posts per run; one post per event (dedupe_key).
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import IntegrityError
from django.utils import timezone
from django.utils.html import escape

logger = logging.getLogger("nutrizone.telegram_bot.channel_autopost")
TZ = ZoneInfo("Asia/Tashkent")


def money(value) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return ""


def _brand_names(cards: list[dict]) -> dict:
    from apps.products.infrastructure.models import BrandTranslation

    ids = {c.get("brand_id") for c in cards if c.get("brand_id")}
    rows = BrandTranslation.objects.filter(brand_id__in=ids).values_list("brand_id", "locale_code", "name")
    out: dict = {}
    for bid, loc, name in rows:
        if loc == "uz" or str(bid) not in out:
            out[str(bid)] = name
    return out


def caption(kind: str, card: dict, brand: str = "") -> str:
    """Telegram-HTML caption (≤ 1024 visible chars) for one product event, in Uzbek -- the channel's language."""
    name = f"<b>{escape(card.get('name') or '')}</b>"
    brand_line = f"🏷 {escape(brand)}\n" if brand else ""
    price = money(card.get("price"))
    old = money(card.get("compare_at_price"))
    pct = card.get("discount_percent") or 0
    price_line = (f"💰 <s>{old}</s> → <b>{price} so'm</b>  (−{pct}%)" if old and pct else f"💰 Narxi: <b>{price} so'm</b>") if price else ""
    stock = "✅ Omborda bor" if card.get("stock_status") == "in_stock" else ""
    rating = f"⭐ {card['rating_average']:.1f} ({card['rating_count']} ta baho)" if card.get("rating_count") else ""
    head = {
        "new": "🆕 <b>Yangi mahsulot!</b>",
        "sale": f"🔥 <b>Chegirma −{pct}%</b> — cheklangan muddat!",
        "restock": "📦 <b>Yana sotuvda!</b> Kutganlar uchun yaxshi xabar.",
    }[kind]
    lines = [head, "", name, brand_line.rstrip("\n"), "", price_line, stock, rating, "", "🚚 Tez yetkazib berish · 🏪 Do'kondan olib ketish", "🪙 Har xariddan NutriZone coin"]
    return "\n".join(x for i, x in enumerate(lines) if x or (i and lines[i - 1])).strip()


def _quiet(settings_row, now: datetime) -> bool:
    hour = now.astimezone(TZ).hour
    a, b = settings_row.quiet_from, settings_row.quiet_to
    return (a <= hour or hour < b) if a > b else (a <= hour < b)


def _channel(settings_row) -> str:
    if settings_row.channel.strip():
        return settings_row.channel.strip()
    from apps.telegram_bot.infrastructure.admin import _default_channel

    return _default_channel()


def candidates(settings_row) -> list[tuple[str, dict, str]]:
    """(kind, card, dedupe_key) for every event not posted yet. Also refreshes the stock flags."""
    from apps.products.infrastructure.models import Product
    from apps.products.infrastructure.selectors import _cards_with_price_and_rating
    from apps.telegram_bot.infrastructure.models import ProductStockFlag, TelegramPost

    products = list(Product.objects.filter(status="published").prefetch_related("translations", "media", "variants"))
    cards = {c["id"]: c for c in _cards_with_price_and_rating(products, "uz")}
    posted = set(TelegramPost.objects.filter(dedupe_key__isnull=False).values_list("dedupe_key", flat=True))
    flags = {str(f.product_id): f for f in ProductStockFlag.objects.filter(product_id__in=[p.id for p in products])}
    out = []
    for p in products:
        card = cards.get(str(p.id))
        if not card or not card.get("price"):
            continue
        in_stock = card.get("stock_status") == "in_stock"
        flag = flags.get(str(p.id))
        if flag is None:
            ProductStockFlag.objects.create(product_id=p.id, in_stock=in_stock)  # first sight: remember, don't post
        elif flag.in_stock != in_stock:
            if in_stock and settings_row.restock:
                out.append(("restock", card, f"restock:{p.id}:{timezone.now():%Y%m%d}"))
            ProductStockFlag.objects.filter(pk=p.id).update(in_stock=in_stock, changed_at=timezone.now())
        if not in_stock:
            continue
        if settings_row.new_products and settings_row.enabled_at and p.created_at >= settings_row.enabled_at:
            out.append(("new", card, f"new:{p.id}"))
        pct = card.get("discount_percent") or 0
        if settings_row.discounts and pct >= settings_row.min_discount:
            out.append(("sale", card, f"sale:{p.id}:{pct}:{int(float(card['price']))}"))
    # one event per product (restock > new > sale); a sale already shown in a recent new/restock post (same price) is not reposted
    from datetime import timedelta

    recent = {}
    for pid, body in TelegramPost.objects.filter(source__in=("new", "restock"), created_at__gte=timezone.now() - timedelta(days=7)).values_list("product_id", "body"):
        recent.setdefault(str(pid), []).append(body)
    order = {"restock": 0, "new": 1, "sale": 2}
    seen, unique = set(), []
    for kind, card, key in sorted(out, key=lambda e: order[e[0]]):
        if key in posted or card["id"] in seen:
            continue
        if kind == "sale" and any(f"{money(card['price'])} so'm" in b for b in recent.get(card["id"], [])):
            continue
        seen.add(card["id"])
        unique.append((kind, card, key))
    return unique


def run(now: datetime | None = None) -> dict:
    from apps.products.infrastructure.models import Product
    from apps.telegram_bot.infrastructure import posts
    from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings, TelegramPost, TelegramPostStatus

    now = now or timezone.now()
    s = ChannelAutoPostSettings.get()
    if not s.enabled:
        return {"skipped": "disabled"}
    channel = _channel(s)
    if not channel:
        return {"skipped": "no channel"}
    events = candidates(s)  # refresh stock flags even during quiet hours
    if _quiet(s, now):
        return {"skipped": "quiet hours", "pending": len(events)}
    brands = _brand_names([c for _k, c, _d in events])
    queued = 0
    for kind, card, key in events[: s.max_per_run]:
        product = Product.objects.filter(pk=card["id"]).first()
        try:
            post = TelegramPost.objects.create(
                title=f"Avto: {dict(new='Yangi', sale='Chegirma', restock='Yana sotuvda')[kind]} — {card['name'][:80]}",
                body=caption(kind, card, brands.get(str(card.get("brand_id")), "")), product=product,
                to_channel=True, channel=channel, source=kind, dedupe_key=key, created_by="Avtopost", status=TelegramPostStatus.DRAFT,
            )
        except IntegrityError:
            continue
        posts.queue(post)
        queued += 1
    return {"queued": queued, "pending": max(len(events) - queued, 0)}
