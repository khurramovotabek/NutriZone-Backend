"""
@nutrizonebot -- the shop screens as Telegram Rich Messages (rich.py), in the shopper's language (uz / ru / en):

  showcase       "📦 Mahsulotlar": a collage of the best sellers, a top-list table (price, old price, rating, stock)
                 and one button per product that opens its page
  product page   photo (+ gallery collage), price / discount, rating, sizes table with prices, nutrition facts,
                 goals, description and directions folded into <details>, add-to-cart / buy-now buttons
  cart           basket table (product · qty · sum), totals with the coins the shopper can spend
  my orders      orders table with status and amount; one order: status progress checklist, products with
                 names, money, delivery address and map

Product photos are read straight from media storage (no public URL needed) and shrunk to phone size. Every builder
returns a RichDoc with a classic-HTML `fallback`, so a client that refuses rich messages still gets the screen.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.telegram_bot.infrastructure import charts
from apps.telegram_bot.infrastructure import rich as R

logger = logging.getLogger("nutrizone.telegram_bot.shop_rich")
TZ = ZoneInfo("Asia/Tashkent")
SHOWCASE_SIZE = 8
PHOTO_PX = 720

T = {
    "uz": {
        "som": "so'm", "cards_view": "🃏 Kartalarda ko'rish", "sale": "Aksiyadagi mahsulotlar", "sale_badge": "AKSIYA", "sale_upto": "−{p}% gacha", "sale_count": "{n} ta mahsulot chegirmada",
        "sale_save": "eng katta tejov", "col_discount": "Chegirma", "sale_hint": "Narxlar ombordagi qoldiq tugaguncha amal qiladi. Mahsulotni ochish uchun tugmani bosing 👇",  "showcase": "NutriZone vitrinasi", "showcase_sub": "Eng ko'p sotilayotgan mahsulotlar — narx, reyting va qoldiq bir joyda",
        "top": "🔥 Top mahsulotlar", "new": "🆕 Yangi kelganlar", "col_product": "Mahsulot", "col_price": "Narx", "col_rating": "⭐", "col_stock": "📦",
        "in_stock": "✅", "few": "⚠️ {n}", "out": "❌", "open_hint": "Mahsulotni ochish uchun tugmani bosing 👇",
        "price": "Narx", "old_price": "Avvalgi narx", "discount": "Chegirma", "rating": "Reyting", "reviews": "{n} ta sharh", "no_reviews": "Hali sharh yo'q",
        "stock": "Omborda", "brand": "Brend", "sizes": "📏 Hajmlar va narxlar", "col_size": "Hajm", "col_pack": "Qadoq", "nutrition": "🥄 Ozuqaviy qiymat",
        "serving": "Porsiya", "servings": "Porsiyalar soni", "calories": "Kaloriya", "goals": "🎯 Maqsad", "about": "📖 Mahsulot haqida", "directions": "🥤 Qanday qabul qilish",
        "warnings": "⚠️ Ogohlantirish", "flavours": "🍓 Ta'mlar", "add": "🛒 Savatga", "buy": "⚡ Hozir sotib olish", "site": "🌐 Saytda ochish",
        "cart": "Savatingiz", "cart_sub": "{units} dona mahsulot", "col_qty": "Soni", "col_sum": "Summa", "items": "Mahsulotlar", "total": "JAMI",
        "coins_hint": "🪙 Hisobingizda {coins} coin bor — rasmiylashtirishda to'lovga ishlatishingiz mumkin.", "price_pending": "narx aniqlanmoqda",
        "orders": "Buyurtmalarim", "orders_sub": "Oxirgi {n} ta buyurtma", "col_order": "Buyurtma", "col_date": "Sana", "col_status": "Holat",
        "order": "Buyurtma", "progress": "📍 Buyurtma holati", "address": "🏠 Yetkazish manzili", "map": "📍 Yetkazish nuqtasi", "pickup": "🏪 Do'kondan olib ketish",
        "coins_used": "🪙 Coins bilan to'landi", "to_pay": "To'lanadi", "discount_row": "Chegirma", "track": "📦 Buyurtmani kuzatish", "footer": "NutriZone · sog'lom tanlov",
    },
    "ru": {
        "som": "сум", "cards_view": "🃏 Смотреть карточками", "sale": "Товары со скидкой", "sale_badge": "АКЦИЯ", "sale_upto": "до −{p}%", "sale_count": "{n} товаров со скидкой",
        "sale_save": "максимальная экономия", "col_discount": "Скидка", "sale_hint": "Цены действуют, пока товар есть в наличии. Нажмите кнопку, чтобы открыть товар 👇",  "showcase": "Витрина NutriZone", "showcase_sub": "Хиты продаж — цена, рейтинг и наличие в одном месте",
        "top": "🔥 Топ товаров", "new": "🆕 Новинки", "col_product": "Товар", "col_price": "Цена", "col_rating": "⭐", "col_stock": "📦",
        "in_stock": "✅", "few": "⚠️ {n}", "out": "❌", "open_hint": "Нажмите кнопку, чтобы открыть товар 👇",
        "price": "Цена", "old_price": "Старая цена", "discount": "Скидка", "rating": "Рейтинг", "reviews": "{n} отзыв(ов)", "no_reviews": "Пока нет отзывов",
        "stock": "На складе", "brand": "Бренд", "sizes": "📏 Объёмы и цены", "col_size": "Объём", "col_pack": "Упаковка", "nutrition": "🥄 Пищевая ценность",
        "serving": "Порция", "servings": "Порций", "calories": "Калории", "goals": "🎯 Цель", "about": "📖 О товаре", "directions": "🥤 Способ применения",
        "warnings": "⚠️ Предупреждение", "flavours": "🍓 Вкусы", "add": "🛒 В корзину", "buy": "⚡ Купить сейчас", "site": "🌐 Открыть на сайте",
        "cart": "Ваша корзина", "cart_sub": "{units} шт. товаров", "col_qty": "Кол-во", "col_sum": "Сумма", "items": "Товары", "total": "ИТОГО",
        "coins_hint": "🪙 На счёте {coins} coin — можно оплатить ими часть заказа.", "price_pending": "цена уточняется",
        "orders": "Мои заказы", "orders_sub": "Последние {n} заказов", "col_order": "Заказ", "col_date": "Дата", "col_status": "Статус",
        "order": "Заказ", "progress": "📍 Статус заказа", "address": "🏠 Адрес доставки", "map": "📍 Точка доставки", "pickup": "🏪 Самовывоз из магазина",
        "coins_used": "🪙 Оплачено coins", "to_pay": "К оплате", "discount_row": "Скидка", "track": "📦 Отследить заказ", "footer": "NutriZone · здоровый выбор",
    },
    "en": {
        "som": "UZS", "cards_view": "🃏 Browse as cards", "sale": "On sale", "sale_badge": "SALE", "sale_upto": "up to −{p}%", "sale_count": "{n} products on sale",
        "sale_save": "biggest saving", "col_discount": "Off", "sale_hint": "Prices last while stock lasts. Tap a button to open the product 👇",  "showcase": "NutriZone showcase", "showcase_sub": "Best sellers — price, rating and stock in one place",
        "top": "🔥 Top products", "new": "🆕 New arrivals", "col_product": "Product", "col_price": "Price", "col_rating": "⭐", "col_stock": "📦",
        "in_stock": "✅", "few": "⚠️ {n}", "out": "❌", "open_hint": "Tap a button to open the product 👇",
        "price": "Price", "old_price": "Was", "discount": "Discount", "rating": "Rating", "reviews": "{n} review(s)", "no_reviews": "No reviews yet",
        "stock": "In stock", "brand": "Brand", "sizes": "📏 Sizes and prices", "col_size": "Size", "col_pack": "Pack", "nutrition": "🥄 Nutrition facts",
        "serving": "Serving", "servings": "Servings", "calories": "Calories", "goals": "🎯 Goal", "about": "📖 About", "directions": "🥤 How to use",
        "warnings": "⚠️ Warning", "flavours": "🍓 Flavours", "add": "🛒 Add to cart", "buy": "⚡ Buy now", "site": "🌐 Open on the website",
        "cart": "Your cart", "cart_sub": "{units} item(s)", "col_qty": "Qty", "col_sum": "Sum", "items": "Items", "total": "TOTAL",
        "coins_hint": "🪙 You have {coins} coins — spend them at checkout.", "price_pending": "price pending",
        "orders": "My orders", "orders_sub": "Last {n} orders", "col_order": "Order", "col_date": "Date", "col_status": "Status",
        "order": "Order", "progress": "📍 Order status", "address": "🏠 Delivery address", "map": "📍 Delivery point", "pickup": "🏪 Store pickup",
        "coins_used": "🪙 Paid with coins", "to_pay": "To pay", "discount_row": "Discount", "track": "📦 Track the order", "footer": "NutriZone · the healthy choice",
    },
}
STATUS = {
    "uz": {"pending_payment": "⏳ To'lov kutilmoqda", "confirmed": "✅ Tasdiqlandi", "processing": "📦 Yig'ilmoqda", "shipped": "🚚 Yo'lda", "delivered": "🎉 Yetkazildi",
           "completed": "🏁 Yakunlandi", "cancelled": "❌ Bekor qilindi", "returned": "↩️ Qaytarildi", "failed": "⚠️ Muvaffaqiyatsiz", "draft": "📝 Qoralama"},
    "ru": {"pending_payment": "⏳ Ожидает оплаты", "confirmed": "✅ Подтверждён", "processing": "📦 Собирается", "shipped": "🚚 В пути", "delivered": "🎉 Доставлен",
           "completed": "🏁 Завершён", "cancelled": "❌ Отменён", "returned": "↩️ Возвращён", "failed": "⚠️ Ошибка", "draft": "📝 Черновик"},
    "en": {"pending_payment": "⏳ Awaiting payment", "confirmed": "✅ Confirmed", "processing": "📦 Packing", "shipped": "🚚 On the way", "delivered": "🎉 Delivered",
           "completed": "🏁 Completed", "cancelled": "❌ Cancelled", "returned": "↩️ Returned", "failed": "⚠️ Failed", "draft": "📝 Draft"},
}
PROGRESS = ("confirmed", "processing", "shipped", "delivered")


def tr(lang: str, key: str, **kw) -> str:
    text = T.get(lang, T["uz"]).get(key) or T["uz"][key]
    return text.format(**kw) if kw else text


def status_label(status: str, lang: str) -> str:
    return STATUS.get(lang, STATUS["uz"]).get(status, status)


def money(v, lang: str = "uz") -> str:
    return f"{int(round(Decimal(str(v or 0)))):,}".replace(",", " ") + " " + tr(lang, "som")


def num(v) -> str:
    return f"{int(round(Decimal(str(v or 0)))):,}".replace(",", " ")


# ---------------------------------------------------------------- product photos


def photo(url: str | None, px: int = PHOTO_PX) -> bytes | None:
    """A product image from media storage as a phone-sized PNG on white (photos are often transparent PNGs)."""
    if not url:
        return None
    from django.core.files.storage import default_storage
    from PIL import Image

    path = urlparse(url).path
    media = "/" + (getattr(settings, "MEDIA_URL", "/media/") or "/media/").strip("/") + "/"
    if media not in path:
        return None
    name = path.split(media, 1)[1]
    try:
        with default_storage.open(name, "rb") as fh:
            img = Image.open(io.BytesIO(fh.read()))
            img.load()
    except Exception:  # noqa: BLE001 -- a missing / broken image just leaves the picture out
        logger.info("shop_rich: image %s not readable", name)
        return None
    scale = min(px * 0.92 / img.width, px * 0.92 / img.height)  # fit with a small margin (small thumbnails are scaled up)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (px, px), (255, 255, 255))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas.paste(img, ((px - img.width) // 2, (px - img.height) // 2), img)
    else:
        canvas.paste(img.convert("RGB"), ((px - img.width) // 2, (px - img.height) // 2))
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def strip(urls: list[str], tile: int = 300) -> bytes | None:
    """The basket's photos side by side in one compact band (white tiles on the reports' navy) -- a staff post shows
    every box at a glance without a full-width picture per product."""
    from PIL import Image, ImageDraw

    tiles = [png for png in (photo(u, tile) for u in urls[:6]) if png]
    if not tiles:
        return None
    gap, pad = 16, 20
    width = max(1200, pad * 2 + len(tiles) * tile + (len(tiles) - 1) * gap)
    band = Image.new("RGB", (width, tile + pad * 2), charts.BG)
    draw = ImageDraw.Draw(band)
    x = (width - (len(tiles) * tile + (len(tiles) - 1) * gap)) // 2
    for png in tiles:
        draw.rounded_rectangle((x, pad, x + tile, pad + tile), 22, fill=(255, 255, 255))
        img = Image.open(io.BytesIO(png))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width, img.height), 22, fill=255)
        band.paste(img, (x, pad), mask)
        x += tile + gap
    out = io.BytesIO()
    band.save(out, "PNG", optimize=True)
    return out.getvalue()


def pictures(doc: R.RichDoc, urls: list[str], prefix: str, caption: str = "") -> str:
    """One figure, or a collage of up to 6 pictures; '' when none could be read."""
    ids = []
    for k, url in enumerate(urls[:6]):
        image_id = f"{prefix}{k}"
        if doc.image(image_id, photo(url, 480 if len(urls) > 1 else PHOTO_PX)):
            ids.append(image_id)
    if not ids:
        return ""
    return R.figure(ids[0], caption) if len(ids) == 1 else R.collage(ids, caption)


def _stock_cell(qty, lang: str) -> str:
    if qty is None:
        return "—"
    if qty <= 0:
        return R.e(tr(lang, "out"))
    return R.e(tr(lang, "few", n=qty)) if qty <= 3 else R.e(tr(lang, "in_stock"))


def _stock_words(qty, lang: str) -> str:
    if qty is None:
        return "—"
    words = {"uz": ("❌ tugagan", "⚠️ {n} ta qoldi", "✅ bor ({n} ta)"), "ru": ("❌ нет в наличии", "⚠️ осталось {n}", "✅ есть ({n} шт.)"),
             "en": ("❌ sold out", "⚠️ {n} left", "✅ in stock ({n})")}.get(lang) or ("❌", "⚠️ {n}", "✅ {n}")
    return R.e((words[0] if qty <= 0 else words[1] if qty <= 3 else words[2]).format(n=qty))


def _price_cell(card: dict, lang: str) -> str:
    if not card.get("price"):
        return R.i(tr(lang, "price_pending"))
    cell = R.b(num(card["price"]))
    if card.get("compare_at_price") and Decimal(str(card["compare_at_price"])) > Decimal(str(card["price"])):
        cell += f" <s>{num(card['compare_at_price'])}</s>"
    return cell


def _rating_cell(card: dict) -> str:
    return f"{card['rating_average']:.1f}" if card.get("rating_count") else "—"


def _site(path: str) -> str | None:
    base = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else None


# ---------------------------------------------------------------- showcase


def showcase_cards(lang: str, kind: str = "best") -> list[dict]:
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    svc = TelegramCatalogService()
    cards = svc.list_best_sellers_cards(limit=SHOWCASE_SIZE, locale=lang) if kind == "best" else []
    if len(cards) < SHOWCASE_SIZE:  # a young shop: top up with the newest products
        from apps.products.infrastructure.selectors import DjangoProductSearchBackend

        seen = {c["id"] for c in cards}
        newest = DjangoProductSearchBackend().search("", {}, 1, SHOWCASE_SIZE, "-created_at", lang)["results"]
        cards += [c for c in newest if c["id"] not in seen][: SHOWCASE_SIZE - len(cards)]
    return cards


def showcase_doc(lang: str = "uz") -> R.RichDoc:
    cards = showcase_cards(lang)
    doc = R.RichDoc()
    hero = pictures(doc, [c["primary_image_path"] for c in cards if c.get("primary_image_path")], "p", tr(lang, "showcase_sub"))
    doc.add(hero, R.h(2, f"🛍 {R.e(tr(lang, 'showcase'))}"))
    if not hero:
        doc.add(R.p(R.e(tr(lang, "showcase_sub"))))
    rows = [[str(k), f"{R.b(c.get('name') or '—')}", _price_cell(c, lang), _rating_cell(c), _stock_cell(c.get("stock_quantity"), lang)]
            for k, c in enumerate(cards, 1)]
    if rows:
        doc.add(R.h(3, R.e(tr(lang, "top"))),
                R.table(["#", R.e(tr(lang, "col_product")), R.e(tr(lang, "col_price")), R.e(tr(lang, "col_rating")), R.e(tr(lang, "col_stock"))], rows,
                        align=["center", "left", "right", "center", "center"]),
                R.p(R.i(tr(lang, "open_hint"))))
        for pair in (cards[k:k + 2] for k in range(0, len(cards), 2)):
            doc.add(R.buttons(*[R.button(f"{k}. {_short(c.get('name'))}", callback=f"po:open:{c['id']}") for k, c in
                                ((cards.index(c) + 1, c) for c in pair)]))
    doc.add(R.footer(R.e(tr(lang, "footer"))))
    doc.fallback = f"🛍 <b>{R.e(tr(lang, 'showcase'))}</b>\n\n" + "\n".join(
        f"{k}. <b>{R.e(c.get('name'))}</b> — {R.e(money(c['price'], lang)) if c.get('price') else R.e(tr(lang, 'price_pending'))}" for k, c in enumerate(cards, 1))
    return doc


def _short(name, n: int = 22) -> str:
    name = str(name or "—")
    return name if len(name) <= n else name[: n - 1] + "…"


def sale_cards(lang: str, limit: int = 10) -> list[dict]:
    """Products on sale right now (old price above today's price), biggest saving first."""
    from apps.products.infrastructure.selectors import DjangoProductSearchBackend

    found = DjangoProductSearchBackend().search("", {"on_sale": True}, 1, limit, "-discount", lang)["results"]
    return [c for c in found if c.get("price") and c.get("compare_at_price")]


def sale_doc(lang: str = "uz", cards: list[dict] | None = None) -> R.RichDoc | None:
    cards = sale_cards(lang) if cards is None else cards
    if not cards:
        return None
    doc = R.RichDoc()
    best = max((c.get("discount_percent") or 0) for c in cards)
    saving = max(Decimal(str(c["compare_at_price"])) - Decimal(str(c["price"])) for c in cards)
    doc.image("salehead", charts.receipt_banner(tr(lang, "sale_badge"), tr(lang, "sale_upto", p=best), tr(lang, "sale_count", n=len(cards)),
                                                money(saving, lang), tr(lang, "sale_save"), charts.ROSE))
    doc.add(R.figure("salehead"), R.h(2, f"💰 {R.e(tr(lang, 'sale'))}"),
            pictures(doc, [c["primary_image_path"] for c in cards if c.get("primary_image_path")], "s"))
    rows = [[str(k), R.b(c.get("name") or "—"), f"{R.b(num(c['price']))} <s>{num(c['compare_at_price'])}</s>",
             R.mark(f"−{c['discount_percent']}%") if c.get("discount_percent") else "—"] for k, c in enumerate(cards, 1)]
    doc.add(R.table(["#", R.e(tr(lang, "col_product")), R.e(tr(lang, "col_price")), R.e(tr(lang, "col_discount"))], rows, align=["center", "left", "right", "center"]),
            R.p(R.i(tr(lang, "sale_hint"))))
    for start in range(0, len(cards), 2):
        doc.add(R.buttons(*[R.button(f"−{c.get('discount_percent') or 0}% · {_short(c.get('name'), 18)}", callback=f"po:open:{c['id']}")
                            for c in cards[start:start + 2]]))
    doc.add(R.footer(R.e(tr(lang, "footer"))))
    doc.fallback = f"💰 <b>{R.e(tr(lang, 'sale'))}</b>\n\n" + "\n".join(
        f"{k}. <b>{R.e(c.get('name'))}</b> — {R.e(money(c['price'], lang))} (<s>{R.e(num(c['compare_at_price']))}</s>)" for k, c in enumerate(cards, 1))
    return doc


# ---------------------------------------------------------------- product page


def product_doc(product_id, lang: str = "uz") -> R.RichDoc | None:
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    svc = TelegramCatalogService()
    full = svc.get_product(uuid.UUID(str(product_id)), locale=lang)
    if not full:
        return None
    full = svc.enrich(full)
    doc = R.RichDoc()
    urls = [u for u in [full.get("primary_image_path"), *(full.get("gallery") or [])] if u]
    doc.add(pictures(doc, list(dict.fromkeys(urls)), "g"))
    doc.add(R.h(2, R.e(full.get("name") or "—")))
    price = R.b(money(full["price"], lang)) if full.get("price") else R.i(tr(lang, "price_pending"))
    head = [price]
    if full.get("discount_percent") and full.get("compare_at_price"):
        head.append(f"<s>{R.e(money(full['compare_at_price'], lang))}</s> · {R.mark(f'−{full['discount_percent']}%')}")
    doc.add(R.p(" · ".join(head)))

    doc.add(R.table([], [[R.e(k), v] for k, v in _info_rows(full, lang)], align=["left", "left"]), _sizes(full, lang), _facts(full, lang))
    if full.get("description"):
        doc.add(R.details(R.e(tr(lang, "about")), _paragraphs(full["description"][:1500])))
    if full.get("directions"):
        doc.add(R.details(R.e(tr(lang, "directions")), _paragraphs(str(full["directions"])[:800])))
    if full.get("warnings"):
        doc.add(R.aside(R.e(str(full["warnings"])[:500]), cite=R.e(tr(lang, "warnings"))))

    actions = []
    if full.get("default_variant_id") and full.get("price"):
        actions += [R.button(tr(lang, "add"), callback=f"po:add:{full['default_variant_id']}", style="primary"),
                    R.button(tr(lang, "buy"), callback=f"po:buy:{full['default_variant_id']}", style="success")]
    if actions:
        doc.add(R.buttons(*actions))
    site = _site(f"/products/{full['slug']}") if full.get("slug") else None
    if site:
        doc.add(R.buttons(R.button(tr(lang, "site"), url=site)))
    doc.add(R.footer(R.e(tr(lang, "footer"))))
    doc.fallback = (f"<b>{R.e(full.get('name'))}</b>\n{R.e(full.get('brand_name') or '')}\n💰 "
                    + (R.e(money(full["price"], lang)) if full.get("price") else R.e(tr(lang, "price_pending"))))
    return doc


def _paragraphs(text: str) -> str:
    return "".join(R.p(R.e(line.strip())) for line in str(text).splitlines() if line.strip())


def _info_rows(full: dict, lang: str) -> list[tuple[str, str]]:
    from apps.products.infrastructure import goals as goal_book

    rating = (R.e(f"⭐ {full['rating_average']:.1f} / 5 · " + tr(lang, "reviews", n=full["rating_count"])) if full.get("rating_count")
              else R.e(tr(lang, "no_reviews")))
    rows = [(tr(lang, "brand"), R.b(full.get("brand_name") or "—")), (tr(lang, "rating"), rating), (tr(lang, "stock"), _stock_words(full.get("available_quantity"), lang))]
    goals = [goal_book.label(g, lang) for g in goal_book.clean(full.get("goals") or [])]
    if goals:
        rows.append((tr(lang, "goals"), R.e(", ".join(goals))))
    if full.get("flavours"):
        rows.append((tr(lang, "flavours"), R.e(", ".join(str(f.get("name") if isinstance(f, dict) else f) for f in full["flavours"]))))
    return rows


def _sizes(full: dict, lang: str) -> str:
    variants = [v for v in full.get("variants") or [] if v.get("status") == "active"]
    if not (len(variants) > 1 or (variants and variants[0].get("package"))):
        return ""
    rows = []
    for v in variants:
        size = f"{v['weight_value']:g} {v.get('weight_unit') or 'g'}" if v.get("weight_value") else (v.get("sku") or "—")
        rows.append([R.e(size), R.e((v.get("package") or {}).get("name") or "—"), R.b(num(v["price"])) if v.get("price") else "—"])
    return R.h(3, R.e(tr(lang, "sizes"))) + R.table([R.e(tr(lang, "col_size")), R.e(tr(lang, "col_pack")), R.e(tr(lang, "col_price"))], rows, align=["left", "left", "right"])


def _facts(full: dict, lang: str) -> str:
    nutrition = full.get("nutrition") or {}
    facts = [(tr(lang, "serving"), f"{nutrition['serving_size_grams']:g} g" if nutrition.get("serving_size_grams") else ""),
             (tr(lang, "servings"), str(nutrition.get("servings_per_container") or "")), (tr(lang, "calories"), str(nutrition.get("calories") or ""))]
    facts += [(str(f.get("name") or f.get("key") or ""), f"{f.get('amount') or f.get('value') or ''} {f.get('unit') or ''}".strip())
              for f in (full.get("supplement_facts") or []) if isinstance(f, dict)]
    facts += [(str(sp.get("key")), str(sp.get("value"))) for sp in full.get("specifications") or []]
    facts = [(k, v) for k, v in facts if k and v]
    return R.h(3, R.e(tr(lang, "nutrition"))) + R.table([], [[R.e(k), R.b(v)] for k, v in facts], align=["left", "right"]) if facts else ""


# ---------------------------------------------------------------- cart


def cart_doc(user, cart: dict, lang: str = "uz") -> R.RichDoc:
    from apps.stores.infrastructure.stock_service import variant_infos

    infos = variant_infos([uuid.UUID(i["product_variant_id"]) for i in cart["items"]], locale=lang)
    units = sum(i["quantity"] for i in cart["items"])
    rows = []
    for k, item in enumerate(cart["items"], 1):
        info = infos.get(uuid.UUID(item["product_variant_id"]))
        name = R.b(info.name if info else "—") + (f" · {R.e(info.size)}" if info and info.size else "")
        line = R.b(num(Decimal(str(item["unit_amount"])) * item["quantity"])) if item.get("priced") else R.i(tr(lang, "price_pending"))
        rows.append([str(k), name, str(item["quantity"]), line])
    doc = R.RichDoc()
    doc.image("head", charts.receipt_banner("NUTRIZONE", tr(lang, "cart").upper(), tr(lang, "cart_sub", units=units), money(cart["total"], lang), "", charts.GREEN))
    doc.add(R.figure("head"), R.h(2, f"🛒 {R.e(tr(lang, 'cart'))}"),
            R.table(["#", R.e(tr(lang, "col_product")), R.e(tr(lang, "col_qty")), R.e(tr(lang, "col_sum"))], rows, align=["center", "left", "center", "right"]),
            R.table([], [[R.b(tr(lang, "total")), R.b(money(cart["total"], lang))]], align=["left", "right"]))
    coins = _coins(user)
    if coins:
        doc.add(R.aside(R.e(tr(lang, "coins_hint", coins=num(coins)))))
    doc.add(R.footer(R.e(tr(lang, "footer"))))
    doc.fallback = f"🛒 <b>{R.e(tr(lang, 'cart'))}</b> · {units}\n\n" + "\n".join(
        f"{r[0]}. {r[1]} — {r[2]} × = {r[3]}" for r in rows) + f"\n\n<b>{R.e(tr(lang, 'total'))}: {R.e(money(cart['total'], lang))}</b>"
    return doc


def _coins(user) -> Decimal:
    try:
        from apps.loyalty.infrastructure import services as loyalty

        return Decimal(str(loyalty.summary(user.id).balance or 0))
    except Exception:  # noqa: BLE001 -- the hint is optional
        return Decimal(0)


# ---------------------------------------------------------------- orders


def _order_total(order) -> Decimal:
    return order.compute_total().grand_total.amount


def orders_doc(orders: list[dict], lang: str = "uz") -> R.RichDoc:
    from apps.ordering.infrastructure import composition as ordering_composition

    repo = ordering_composition.build_order_repository()
    rows = []
    for o in orders:
        order = repo.get_by_id(uuid.UUID(o["id"]))
        when = timezone.localtime(datetime.fromisoformat(o["placed_at"]), TZ).strftime("%d.%m.%Y") if o.get("placed_at") else "—"
        rows.append([R.b(o["order_number"]), R.e(when), R.e(status_label(o["status"], lang)), R.b(num(_order_total(order))) if order else "—"])
    doc = R.RichDoc()
    doc.add(R.h(2, f"📦 {R.e(tr(lang, 'orders'))}"), R.p(R.i(tr(lang, "orders_sub", n=len(orders)))),
            R.table([R.e(tr(lang, "col_order")), R.e(tr(lang, "col_date")), R.e(tr(lang, "col_status")), R.e(tr(lang, "col_sum"))], rows,
                    align=["left", "center", "left", "right"]),
            R.footer(R.e(tr(lang, "footer"))))
    doc.fallback = f"📦 <b>{R.e(tr(lang, 'orders'))}</b>\n\n" + "\n".join(f"#{R.e(o['order_number'])} — {R.e(status_label(o['status'], lang))}" for o in orders)
    return doc


def order_doc(order_number: str, customer_id, lang: str = "uz") -> R.RichDoc | None:
    """One of the shopper's own orders (None when it isn't theirs -- the caller answers "not found")."""
    from apps.loyalty.infrastructure.services import coins_spent_on_order
    from apps.ordering.infrastructure.models import OrderModel
    from apps.stores.infrastructure.stock_service import variant_infos

    row = OrderModel.objects.filter(order_number=order_number, customer_id=customer_id).values("id", "fulfilment_method", "status").first()
    if row is None:
        return None
    from apps.ordering.infrastructure import composition as ordering_composition

    order = ordering_composition.build_order_repository().get_by_id(row["id"])
    status, pickup = row["status"], row["fulfilment_method"] == "pickup"
    lines = order.active_lines()
    infos = variant_infos([ln.product_variant_id for ln in lines], locale=lang)
    basket = []
    for k, ln in enumerate(lines, 1):
        info = infos.get(ln.product_variant_id)
        basket.append([str(k), R.b(info.name if info else "—") + (f" · {R.e(info.size)}" if info and info.size else ""), str(ln.quantity),
                       R.b(num(ln.unit_price.amount * ln.quantity))])
    totals = order.compute_total()
    cash = totals.grand_total.amount
    coins = Decimal(coins_spent_on_order(order.id) or 0)
    money_rows = [[R.e(tr(lang, "items")), num(cash + totals.discount_total.amount)]]
    if totals.discount_total.amount - coins > 0:
        money_rows.append([R.e(tr(lang, "discount_row")), f"−{num(totals.discount_total.amount - coins)}"])
    if coins:
        money_rows.append([R.e(tr(lang, "coins_used")), f"−{num(coins)}"])
    money_rows.append([R.b(tr(lang, "to_pay")), R.b(money(cash, lang))])

    doc = R.RichDoc()
    accent = charts.ROSE if status in ("cancelled", "failed", "returned") else charts.GREEN if status in ("delivered", "completed") else charts.CYAN
    placed = timezone.localtime(order.placed_at or timezone.now(), TZ)
    doc.image("head", charts.receipt_banner(tr(lang, "order").upper(), order.order_number.value, status_label(status, lang), money(cash, lang),
                                            placed.strftime("%d.%m.%Y %H:%M"), accent))
    doc.add(R.figure("head"), R.h(2, f"🧾 {R.e(order.order_number.value)}"), R.p(f"{R.b(status_label(status, lang))} · {R.time_tag(placed)}"))
    if status in PROGRESS or status == "completed":
        reached = len(PROGRESS) if status == "completed" else PROGRESS.index(status) + 1
        steps = [s for s in PROGRESS if not (pickup and s == "shipped")]
        doc.add(R.h(3, R.e(tr(lang, "progress"))), R.checklist([(R.e(status_label(s, lang)), PROGRESS.index(s) < reached) for s in steps]))
    doc.add(R.h(3, f"🛍 {R.e(tr(lang, 'items'))}"),
            R.table(["#", R.e(tr(lang, "col_product")), R.e(tr(lang, "col_qty")), R.e(tr(lang, "col_sum"))], basket, align=["center", "left", "center", "right"]),
            R.table([], money_rows, align=["left", "right"]))
    address = order.shipping_address
    if pickup:
        doc.add(R.p(R.e(tr(lang, "pickup"))))
    elif address:
        doc.add(R.h(3, R.e(tr(lang, "address"))), R.p(R.e(", ".join(x for x in (address.city, address.line1, address.line2) if x))))
        if address.latitude is not None and address.longitude is not None:
            doc.add(R.map_block(float(address.latitude), float(address.longitude), 16, R.e(tr(lang, "map"))))
    frontend = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    if frontend.startswith("https://"):
        doc.add(R.buttons(R.button(tr(lang, "track"), web_app=f"{frontend}/tg?next=/orders/{order.order_number.value}", style="primary")))
    doc.add(R.footer(R.e(tr(lang, "footer"))))
    doc.fallback = (f"🧾 <b>{R.e(order.order_number.value)}</b>\n{R.e(status_label(status, lang))}\n\n"
                    + "\n".join(f"{r[0]}. {r[1]} — {r[2]} = {r[3]}" for r in basket) + f"\n\n<b>{R.e(tr(lang, 'to_pay'))}: {R.e(money(cash, lang))}</b>")
    return doc
