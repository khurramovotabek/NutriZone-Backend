"""
Product feeds for shopping surfaces -- the product cards (photo, price, "in stock", the store) in search results:

* Google Merchant Center: RSS 2.0 with the `g:` namespace -- free listings in Google Search / Shopping / Images.
* Yandex YML (Yandex Market / Yandex Products, Yandex Webmaster "Товары"): the same catalogue in Yandex's format.

One item per published product (its default variant: the price and stock the product page leads with, the same
facts as the page's own schema.org Product markup -- never an invented price). The old price, when the product is
marked down, is the regular price and the current one the sale price. Per language (uz / ru / en): its name,
description, category path and the page URL in that language. Built from the catalogue in pages, cached an hour.
"""
from __future__ import annotations

import html
import re
import unicodedata
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

LOCALES = ("uz", "ru", "en")
CACHE_SECONDS = 3600
PAGE = 200
# Google's product taxonomy: "Health & Beauty > Health Care > Fitness & Nutrition" (6871) covers protein, creatine,
# vitamins and supplements -- the whole shop.
GOOGLE_CATEGORY = "6871"
STORE_NAME = "NUTRIZONE"
CHANNEL = {
    "uz": "Sport ozuqalari va vitaminlar: original protein, kreatin, gainer, BCAA, vitaminlar. Toshkent va O'zbekiston bo'ylab yetkazib berish.",
    "ru": "Спортивное питание и витамины: оригинальный протеин, креатин, гейнеры, BCAA, витамины. Доставка по Ташкенту и Узбекистану.",
    "en": "Sports nutrition and vitamins: genuine protein, creatine, gainers, BCAA, vitamins. Delivery across Tashkent and Uzbekistan.",
}
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def site() -> str:
    return (getattr(settings, "FRONTEND_URL", None) or "https://nutrizone.uz").rstrip("/")


def _prefix(locale: str) -> str:
    return "" if locale == "uz" else f"/{locale}"


def plain(text: str | None, limit: int = 4900) -> str:
    """Description as plain text: no HTML / markdown marks, one line, within the feed's limit."""
    t = html.unescape(TAG.sub(" ", text or ""))
    t = re.sub(r"[*_#>`]+", " ", t)
    # emoji / pictographs: Google Merchant flags "promotional symbols" in descriptions
    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("So", "Cs", "Co") and ch not in "\ufe0f\u200d")
    t = SPACE.sub(" ", t).strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def _category_paths(locale: str) -> dict:
    """category id -> "Sport ozuqalari > Proteinlar > Izolyat" in `locale` (Uzbek when untranslated)."""
    from apps.products.infrastructure import models as orm

    rows = {c.id: c for c in orm.Category.objects.prefetch_related("translations")}

    def name(c):
        tr = {t.locale_code: t.name for t in c.translations.all()}
        return tr.get(locale) or tr.get("uz") or next(iter(tr.values()), "")

    out = {}
    for cid in rows:
        names, cur, seen = [], rows.get(cid), set()
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            names.append(name(cur))
            cur = rows.get(cur.parent_id)
        out[cid] = " > ".join(n for n in reversed(names) if n)
    return out


def items(locale: str = "uz") -> list[dict]:
    """Every published product with a price, as feed-neutral dicts."""
    from apps.products.infrastructure import models as orm
    from apps.products.infrastructure.selectors import (
        CatalogSelector,
        _translated_description,
        _translated_name,
        valid_gtin,
    )

    locale = locale if locale in LOCALES else "uz"
    cats = _category_paths(locale)
    brands = {b.id: _translated_name(b, locale) for b in orm.Brand.objects.prefetch_related("translations")}
    out, page = [], 1
    while True:
        cards, total = CatalogSelector().list(page=page, page_size=PAGE, locale=locale)
        if not cards:
            break
        rows = {str(p.id): p for p in orm.Product.objects.filter(id__in=[c["id"] for c in cards]).prefetch_related("translations", "variants", "media")}
        for c in cards:
            row = rows.get(c["id"])
            price = c.get("price")
            if row is None or not price or float(price) <= 0 or not c.get("primary_image_path"):
                continue  # no price or no photo: shopping surfaces reject the item anyway
            default = next((v for v in row.variants.all() if str(v.id) == str(c.get("default_variant_id"))), None)
            slug = (c.get("slugs") or {}).get(locale) or c["slug"]
            old = c.get("compare_at_price")
            stock = c.get("default_variant_stock")
            if stock is None:
                stock = c.get("stock_quantity")
            brand = brands.get(row.brand_id, "") if row.brand_id else ""
            desc = plain(_translated_description(row, locale)) or plain(row.seo_meta_description) or c["name"]
            out.append({
                "id": (default.sku if default and default.sku else c["id"]),
                "group": c["id"],
                "title": c["name"][:150],
                "description": desc,
                "link": f"{site()}{_prefix(locale)}/products/{slug}",
                "image": c["primary_image_path"],
                "images": [],
                "price": int(float(old)) if old and float(old) > float(price) else int(float(price)),
                "sale_price": int(float(price)) if old and float(old) > float(price) else None,
                "currency": c.get("currency") or "UZS",
                "in_stock": bool(stock and stock > 0),
                "brand": brand,
                "gtin": valid_gtin(default.barcode) if default else None,
                "mpn": default.sku if default else "",
                "category": cats.get(row.category_id, ""),
                "category_id": str(row.category_id) if row.category_id else "",
            })
        if page * PAGE >= total:
            break
        page += 1
    return out


def _x(v) -> str:
    return escape(str(v), {'"': "&quot;"})


def google_xml(locale: str = "uz") -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">', "<channel>",
             f"<title>{STORE_NAME} — {_x(locale)}</title>", f"<link>{_x(site() + _prefix(locale))}</link>",
             f"<description>{_x(CHANNEL.get(locale, CHANNEL['uz']))}</description>"]
    for it in items(locale):
        lines += ["<item>",
                  f"<g:id>{_x(it['id'])}</g:id>", f"<g:item_group_id>{_x(it['group'])}</g:item_group_id>",
                  f"<g:title>{_x(it['title'])}</g:title>", f"<g:description>{_x(it['description'])}</g:description>",
                  f"<g:link>{_x(it['link'])}</g:link>", f"<g:image_link>{_x(it['image'])}</g:image_link>",
                  f"<g:availability>{'in_stock' if it['in_stock'] else 'out_of_stock'}</g:availability>",
                  f"<g:price>{it['price']} {_x(it['currency'])}</g:price>",
                  *( [f"<g:sale_price>{it['sale_price']} {_x(it['currency'])}</g:sale_price>"] if it["sale_price"] else []),
                  "<g:condition>new</g:condition>", f"<g:google_product_category>{GOOGLE_CATEGORY}</g:google_product_category>",
                  *( [f"<g:product_type>{_x(it['category'])}</g:product_type>"] if it["category"] else []),
                  *( [f"<g:brand>{_x(it['brand'])}</g:brand>"] if it["brand"] else []),
                  *( [f"<g:gtin>{_x(it['gtin'])}</g:gtin>"] if it["gtin"] else []),
                  *( [f"<g:mpn>{_x(it['mpn'])}</g:mpn>"] if it["mpn"] and not it["gtin"] else []),
                  *( ["<g:identifier_exists>no</g:identifier_exists>"] if not it["gtin"] and not it["brand"] else []),
                  "</item>"]
    lines += ["</channel>", "</rss>"]
    return "\n".join(lines)


def yandex_yml(locale: str = "ru") -> str:
    from apps.products.infrastructure import models as orm

    rows = items(locale)
    used = {it["category_id"] for it in rows if it["category_id"]}
    cats = {str(c.id): c for c in orm.Category.objects.prefetch_related("translations")}
    # a category and all its parents (YML wants the tree the offers hang on)
    need = set()
    for cid in used:
        cur, seen = cats.get(cid), set()
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            need.add(str(cur.id))
            cur = cats.get(str(cur.parent_id)) if cur.parent_id else None

    num = {cid: i + 1 for i, cid in enumerate(sorted(need))}  # YML category ids are numbers

    def cname(c):
        tr = {t.locale_code: t.name for t in c.translations.all()}
        return tr.get(locale) or tr.get("uz") or next(iter(tr.values()), "")

    now = timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S%z")
    now = now[:-2] + ":" + now[-2:]
    out = ['<?xml version="1.0" encoding="UTF-8"?>', f'<yml_catalog date="{now}">', "<shop>",
           f"<name>{STORE_NAME}</name>", f"<company>{STORE_NAME}</company>", f"<url>{_x(site() + _prefix(locale))}</url>",
           '<currencies><currency id="UZS" rate="1"/></currencies>', "<categories>"]
    for cid in sorted(need):
        c = cats[cid]
        parent = f' parentId="{num[str(c.parent_id)]}"' if c.parent_id and str(c.parent_id) in need else ""
        out.append(f'<category id="{num[cid]}"{parent}>{_x(cname(c))}</category>')
    out += ["</categories>", "<pickup>true</pickup>", "<delivery>true</delivery>", "<offers>"]
    for it in rows:
        oid = re.sub(r"[^A-Za-z0-9]", "", str(it["id"]))[:80] or it["group"].replace("-", "")
        out += [f'<offer id="{oid}" available="{"true" if it["in_stock"] else "false"}">',
                f"<url>{_x(it['link'])}</url>",
                f"<price>{it['sale_price'] or it['price']}</price>",
                *( [f"<oldprice>{it['price']}</oldprice>"] if it["sale_price"] else []),
                "<currencyId>UZS</currencyId>",
                *( [f"<categoryId>{num[it['category_id']]}</categoryId>"] if it["category_id"] in need else []),
                f"<picture>{_x(it['image'])}</picture>",
                "<pickup>true</pickup>", "<delivery>true</delivery>",
                f"<name>{_x(it['title'])}</name>",
                *( [f"<vendor>{_x(it['brand'])}</vendor>"] if it["brand"] else []),
                *( [f"<vendorCode>{_x(it['mpn'])}</vendorCode>"] if it["mpn"] else []),
                *( [f"<barcode>{_x(it['gtin'])}</barcode>"] if it["gtin"] else []),
                f"<description><![CDATA[{it['description'].replace(']]>', ']] >')[:3000]}]]></description>",
                "</offer>"]
    out += ["</offers>", "</shop>", "</yml_catalog>"]
    return "\n".join(out)


def cached(kind: str, locale: str) -> str:
    locale = locale if locale in LOCALES else ("ru" if kind == "yandex" else "uz")
    key = f"feeds:{kind}:{locale}:v1"
    body = cache.get(key)
    if body is None:
        body = google_xml(locale) if kind == "google" else yandex_yml(locale)
        cache.set(key, body, CACHE_SECONDS)
    return body
