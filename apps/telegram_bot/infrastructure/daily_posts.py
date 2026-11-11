"""
The shop channel's daily schedule and scheduled posts -- runs every minute (task telegram_bot.channel_schedule).

  1. Posts a manager scheduled in Dashboard → Telegram → Postlar (status "scheduled") are queued when their time comes.
  2. Daily slots (ChannelPostSlot, default 10:00 / 15:00 / 20:00 Tashkent): at each slot one product post goes to the shop
     channel -- the product is picked by the slot's kind (top seller / discount / new / random pick), never one already
     posted to the channel within `repeat_days`. The text is the dashboard template (RichText, Telegram HTML) with
     {variables}; a line whose variable is empty is dropped, so the post never shows "Brend: " with nothing after it.

Guards: a slot fires at most once a day (dedupe_key daily:<date>:<slot>), only within SLOT_WINDOW after its time (after a
long outage the morning post is not sent at night), and is skipped when a manager already put a post into the channel
around that time. Every post is an ordinary TelegramPost (source "daily") sent by posts.send, so it shows up in
Dashboard → Telegram → Postlar with its delivery result.
"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

logger = logging.getLogger("nutrizone.telegram_bot.daily_posts")
TZ = ZoneInfo("Asia/Tashkent")
SLOT_WINDOW = timedelta(minutes=45)
MANUAL_GAP = timedelta(minutes=45)

DEFAULT_TEMPLATE = (
    "<b>{sarlavha}</b>\n"
    "\n"
    "<b>{nomi}</b>\n"
    "🏷 {brend}\n"
    "\n"
    "<i>{tavsif}</i>\n"
    "\n"
    "{narx_qator}\n"
    "📦 {variantlar}\n"
    "⭐ {reyting}\n"
    "✅ Omborda bor · 🚚 Tez yetkazib berish · 🏪 Do'kondan olib ketish\n"
    "🪙 Har xariddan NutriZone coin\n"
    "\n"
    "{teglar}"
)

VARIABLES = [
    ("sarlavha", "jadvaldagi sarlavha (☀️ Kun mahsuloti …)"),
    ("nomi", "mahsulot nomi"),
    ("brend", "brend"),
    ("kategoriya", "kategoriya"),
    ("tavsif", "qisqa tavsif (1–2 gap)"),
    ("narx", "narx: 289 000 so'm"),
    ("eski_narx", "chegirmadan oldingi narx"),
    ("chegirma", "chegirma: −14%"),
    ("narx_qator", "tayyor narx qatori: 💰 eski → yangi (−%)"),
    ("variantlar", "2 ta hajm · 3 ta ta'm"),
    ("reyting", "4.8 (12 ta baho)"),
    ("havola", "saytdagi sahifa havolasi"),
    ("teglar", "#Protein #NutriZone"),
]
_VAR = re.compile(r"\{([a-z_]+)\}")


def money(value) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return ""


def _sentences(text: str, limit: int = 220) -> str:
    from apps.telegram_bot.infrastructure.telegram_html import to_plain

    plain = re.sub(r"\s+", " ", to_plain(text or "")).strip()
    if len(plain) <= limit:
        return plain
    cut = plain[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…"


def _hashtag(text: str) -> str:
    word = re.sub(r"[^\w]", "", (text or "").title().replace("'", "").replace("ʻ", "").replace("’", ""))
    return f"#{word}" if word and not word.isdigit() else ""


def variables(card: dict, heading: str = "", extra: dict | None = None) -> dict[str, str]:
    """Template values -- every one already Telegram-HTML safe (card text escaped, our markup trusted)."""
    extra = extra or {}
    price, old = money(card.get("price")), money(card.get("compare_at_price"))
    pct = int(float(card.get("discount_percent") or 0))
    discounted = bool(old and pct)
    sizes, flavours = int(card.get("size_count") or 0), int(card.get("flavour_count") or 0)
    variant_bits = [f"{sizes} ta hajm" if sizes > 1 else "", f"{flavours} ta ta'm" if flavours > 1 else ""]
    rating = f"{float(card['rating_average']):.1f} ({card['rating_count']} ta baho)" if card.get("rating_count") and card.get("rating_average") else ""
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    category = extra.get("category", "")
    tags = " ".join(t for t in (_hashtag(category), _hashtag(extra.get("brand", "")), "#NutriZone") if t)
    if price:
        price_line = f"💰 <s>{old}</s> → <b>{price} so'm</b>  (−{pct}%)" if discounted else f"💰 Narxi: <b>{price} so'm</b>"
    else:
        price_line = ""
    return {
        "sarlavha": escape(heading),
        "nomi": escape(card.get("name") or ""),
        "brend": escape(extra.get("brand", "")),
        "kategoriya": escape(category),
        "tavsif": escape(_sentences(extra.get("description", ""))),
        "narx": f"{price} so'm" if price else "",
        "eski_narx": f"{old} so'm" if discounted else "",
        "chegirma": f"−{pct}%" if discounted else "",
        "narx_qator": price_line,
        "variantlar": " · ".join(b for b in variant_bits if b),
        "reyting": rating,
        "havola": escape(f"{base}/products/{card.get('slug')}") if base and card.get("slug") else "",
        "teglar": tags,
    }


def render(template: str, values: dict[str, str]) -> str:
    """Fill {variables}; drop a line whose variables are all empty; ≤ 1024 visible characters (photo caption)."""
    from apps.telegram_bot.infrastructure.telegram_html import CAPTION_LIMIT, sanitize, visible_length

    lines = []
    for line in (template or DEFAULT_TEMPLATE).split("\n"):
        names = _VAR.findall(line)
        if names and not any(values.get(n) for n in names):
            continue
        lines.append(_VAR.sub(lambda m: values.get(m.group(1), m.group(0)), line))
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    text = re.sub(r"<(b|i|u|s)>\s*</\1>", "", text)
    text = sanitize(text) if "<" in text else text
    if visible_length(text) > CAPTION_LIMIT and values.get("tavsif"):
        return render(template, {**values, "tavsif": ""})
    return text


# ------------------------------------------------------------------------------------------------ picking a product


def _extras(cards: list[dict]) -> dict[str, dict]:
    """brand / category names (uz) and descriptions for the given cards."""
    from apps.products.infrastructure.models import BrandTranslation, CategoryTranslation, ProductTranslation

    def names(model, field, ids):
        out: dict = {}
        for oid, loc, name in model.objects.filter(**{f"{field}__in": ids}).values_list(field, "locale_code", "name"):
            if loc == "uz" or str(oid) not in out:
                out[str(oid)] = name
        return out

    brands = names(BrandTranslation, "brand_id", {c.get("brand_id") for c in cards if c.get("brand_id")})
    cats = names(CategoryTranslation, "category_id", {c.get("category_id") for c in cards if c.get("category_id")})
    desc: dict = {}
    for pid, loc, text in ProductTranslation.objects.filter(product_id__in=[c["id"] for c in cards]).values_list("product_id", "locale_code", "description"):
        if text and (loc == "uz" or str(pid) not in desc):
            desc[str(pid)] = text
    return {c["id"]: {"brand": brands.get(str(c.get("brand_id")), ""), "category": cats.get(str(c.get("category_id")), ""), "description": desc.get(c["id"], "")}
            for c in cards}


def _sold_last_30_days() -> dict[str, int]:
    from django.db.models import Sum

    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.products.infrastructure.models import ProductVariant

    since = timezone.now() - timedelta(days=30)
    by_variant = dict(OrderLineItemModel.objects.filter(order__created_at__gte=since).exclude(order__status__in=("draft", "cancelled", "failed", "returned"))
                      .values_list("product_variant_id").annotate(n=Sum("quantity")))
    out: dict[str, int] = {}
    for vid, pid in ProductVariant.objects.filter(id__in=list(by_variant)).values_list("id", "product_id"):
        out[str(pid)] = out.get(str(pid), 0) + int(by_variant[vid] or 0)
    return out


def _recently_posted(channel: str, days: int) -> set[str]:
    from apps.telegram_bot.infrastructure.models import TelegramPost

    since = timezone.now() - timedelta(days=max(days, 0))
    return {str(p) for p in TelegramPost.objects.filter(to_channel=True, channel=channel, product_id__isnull=False, created_at__gte=since)
            .exclude(status__in=("draft", "failed")).values_list("product_id", flat=True)}


def pool() -> list[dict]:
    """Postable products: published, in stock, priced, with a photo."""
    from apps.products.infrastructure.models import Product
    from apps.products.infrastructure.selectors import _cards_with_price_and_rating

    products = list(Product.objects.filter(status="published").prefetch_related("translations", "media", "variants"))
    return [c for c in _cards_with_price_and_rating(products, "uz")
            if c.get("stock_status") == "in_stock" and c.get("price") and c.get("primary_image_path")]


def pick(kind: str, cards: list[dict], exclude: set[str], rng: random.Random | None = None) -> dict | None:
    rng = rng or random.Random()
    fresh = [c for c in cards if c["id"] not in exclude] or cards  # everything posted lately → allow repeats rather than silence
    if not fresh:
        return None
    pct = lambda c: int(float(c.get("discount_percent") or 0))  # noqa: E731
    if kind == "sale":
        sale = sorted((c for c in fresh if pct(c) >= 5), key=lambda c: (-pct(c), -int(c.get("stock_quantity") or 0)))
        if sale:
            return rng.choice(sale[:3])
        kind = "top"
    if kind == "new":
        return sorted(fresh, key=lambda c: c.get("created_at") or "", reverse=True)[0]
    if kind == "top":
        sold = _sold_last_30_days()
        ranked = sorted(fresh, key=lambda c: (-sold.get(c["id"], 0), -int(c.get("rating_count") or 0), -int(c.get("stock_quantity") or 0)))
        return rng.choice(ranked[:5])
    best = sorted(fresh, key=lambda c: -int(c.get("stock_quantity") or 0))[:40]  # random pick among well-stocked products
    return rng.choice(best)


# ------------------------------------------------------------------------------------------------ the runner


def channel() -> str:
    from apps.telegram_bot.infrastructure.channel_autopost import _channel
    from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings

    return _channel(ChannelAutoPostSettings.get())


def _slot_at(slot, day) -> datetime:
    return datetime.combine(day, slot.time, tzinfo=TZ)


def build_post(slot, card: dict, extra: dict, template: str, chan: str, *, key: str | None):
    from apps.products.infrastructure.models import Product
    from apps.telegram_bot.infrastructure.models import TelegramPost, TelegramPostStatus

    body = render(template, variables(card, slot.heading, extra))
    return TelegramPost.objects.create(
        title=f"Jadval {slot.time:%H:%M}: {card['name'][:90]}", body=body, product=Product.objects.filter(pk=card["id"]).first(),
        to_channel=True, channel=chan, source="daily", dedupe_key=key, created_by="Kanal jadvali", status=TelegramPostStatus.DRAFT,
    )


def preview(slot) -> dict | None:
    """What this slot would post right now (dashboard panel) -- nothing is saved."""
    from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings

    s = ChannelAutoPostSettings.get()
    if slot.kind == slot.KIND_TIP:
        entry = pick_tip(timezone.now(), random.Random(f"{timezone.localdate()}:{slot.pk}"))
        if entry is None:
            return None
        product = tip_product(entry)
        return {"card": {"id": str(product.pk) if product else "", "name": f"💡 {entry.title}"},
                "body": f"<b>{_md_html(slot.heading or '💡 Kun maslahati')}</b>\n\n<b>{_md_html(entry.title)}</b>\n\n{_md_html(entry.answer_uz.strip())}"}
    cards = pool()
    card = pick(slot.kind, cards, _recently_posted(channel(), s.repeat_days), random.Random(f"{timezone.localdate()}:{slot.pk}"))
    if not card:
        return None
    extra = _extras([card])[card["id"]]
    return {"card": card, "body": render(s.daily_template, variables(card, slot.heading, extra))}


def _due_scheduled(now: datetime) -> int:
    from apps.telegram_bot.infrastructure import posts
    from apps.telegram_bot.infrastructure.models import TelegramPost, TelegramPostStatus

    n = 0
    for post in TelegramPost.objects.filter(status=TelegramPostStatus.SCHEDULED, scheduled_at__lte=now):
        posts.queue(post)
        n += 1
    return n


# ------------------------------------------------------------------------------------------------ "💡 Kun maslahati"

TIP_TOPICS = ("product", "usage")
TIP_REPEAT_DAYS = 90
TIP_TITLE = "Maslahat: "


def _md_html(text: str) -> str:
    """The knowledge base's light markdown (**bold**, _italic_) as Telegram HTML; everything else escaped."""
    import html

    out = html.escape(text or "", quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<i>\1</i>", out, flags=re.S)


def pick_tip(now: datetime, rng: random.Random | None = None):
    """A knowledge entry for today's tip: active, about products / how to take them, not posted in TIP_REPEAT_DAYS --
    among the 5 most important left, so the channel walks through the whole base over the months."""
    from apps.assistant.infrastructure.models import KnowledgeEntry
    from apps.telegram_bot.infrastructure.models import TelegramPost

    recent = {t[len(TIP_TITLE):] for t in TelegramPost.objects.filter(source="daily", title__startswith=TIP_TITLE,
                                                                       created_at__gte=now - timedelta(days=TIP_REPEAT_DAYS)).values_list("title", flat=True)}
    today = now.astimezone(TZ).date()
    entries = [e for e in KnowledgeEntry.objects.filter(is_active=True, topic__in=TIP_TOPICS).order_by("-priority", "title")
               if (e.valid_until is None or e.valid_until >= today) and e.title[:150] not in recent and len(e.answer_uz or "") >= 120]
    if not entries:
        return None
    return (rng or random.Random()).choice(entries[:5])


def tip_product(entry):
    """An in-stock product of the kind the tip is about (its photo and «buy» button), or None."""
    from apps.assistant.infrastructure.advisor import expert, nlu
    from apps.products.infrastructure.models import Product

    about = nlu.normalize(" ".join((entry.title, entry.keywords or "")))
    concept, sub = expert.kind_of(about, next(iter(nlu.concepts_in(f"{about} {about.translate(nlu.LATIN_FROM_CYR)}")), None))
    if not concept:
        return None
    found = expert.kind_search(concept, "uz", sub=sub, limit=1)
    return Product.objects.filter(pk=found[0]["id"]).first() if found else None


def build_tip_post(slot, entry, chan: str, *, key: str | None):
    from apps.telegram_bot.infrastructure.models import TelegramPost, TelegramPostStatus

    heading = slot.heading or "💡 Kun maslahati"
    body = (f"<b>{_md_html(heading)}</b>\n\n<b>{_md_html(entry.title)}</b>\n\n{_md_html(entry.answer_uz.strip())}\n\n"
            "🤖 Savolingiz bo'lsa — saytdagi AI maslahatchiga yozing, mahsulotni sizga moslab tanlab beradi.")
    return TelegramPost.objects.create(
        title=f"{TIP_TITLE}{entry.title[:150]}", body=body, product=tip_product(entry), to_channel=True, channel=chan, source="daily",
        dedupe_key=key, created_by="Kanal jadvali", status=TelegramPostStatus.DRAFT,
    )


def _post_tip(slot, chan: str, key: str, now: datetime) -> int:
    from apps.telegram_bot.infrastructure import posts

    entry = pick_tip(now)
    if entry is None:
        logger.warning("Channel schedule %s: no knowledge entry left to post.", slot)
        return 0
    try:
        post = build_tip_post(slot, entry, chan, key=key)
    except IntegrityError:
        return 0
    posts.queue(post)
    return 1


def run(now: datetime | None = None) -> dict:
    from apps.telegram_bot.infrastructure import posts
    from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings, ChannelPostSlot, TelegramPost

    now = now or timezone.now()
    result = {"scheduled_sent": _due_scheduled(now), "daily": 0}
    s = ChannelAutoPostSettings.get()
    chan = channel()
    if not s.daily_enabled or not chan:
        result["daily_skipped"] = "disabled" if not s.daily_enabled else "no channel"
        return result
    today = now.astimezone(TZ).date()
    cards = None
    for slot in ChannelPostSlot.objects.filter(is_active=True):
        at = _slot_at(slot, today)
        if not (at <= now < at + SLOT_WINDOW):
            continue
        key = f"daily:{today:%Y%m%d}:{slot.pk}"
        if TelegramPost.objects.filter(dedupe_key=key).exists():
            continue
        manual = TelegramPost.objects.filter(source="manual", to_channel=True, channel=chan).exclude(status__in=("draft", "failed"))
        if manual.filter(sent_at__range=(at - MANUAL_GAP, at + MANUAL_GAP)).exists() or manual.filter(scheduled_at__range=(at - MANUAL_GAP, at + MANUAL_GAP)).exists():
            continue  # a manager already posts around this time
        if slot.kind == slot.KIND_TIP:
            result["daily"] += _post_tip(slot, chan, key, now)
            continue
        if cards is None:
            cards = pool()
        card = pick(slot.kind, cards, _recently_posted(chan, s.repeat_days))
        if card is None:
            logger.warning("Channel schedule %s: no postable product.", slot)
            continue
        try:
            post = build_post(slot, card, _extras([card])[card["id"]], s.daily_template, chan, key=key)
        except IntegrityError:
            continue
        posts.queue(post)
        result["daily"] += 1
    return result
