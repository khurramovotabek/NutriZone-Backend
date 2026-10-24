"""
Narxlarni qayta baholash (batch repricing): pick variants by brand / category / text / price / stock, compute new prices
with one rule (± percent, ± amount, markup on cost, a fixed price), round them, review line by line, then apply now or at
a set time. Every price goes through the pricing SetPrice service (price history included); an applied document can be
reverted by a mirror document.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel, RepricingLineModel, RepricingModel

ZERO = Decimal(0)
MODES = {
    "percent": "Foizga o'zgartirish",
    "amount": "Summaga o'zgartirish",
    "markup": "Tannarxga ustama (%)",
    "fixed": "Aniq narx",
}
ROUNDINGS = {
    "none": "Yaxlitlamaslik",
    "100": "100 so'mgacha",
    "1000": "1 000 so'mgacha",
    "5000": "5 000 so'mgacha",
    "10000": "10 000 so'mgacha",
    "900": "…900 bilan tugasin (149 900)",
}
COMPARE = {
    "keep": "Eski narxni o'zgartirmaslik",
    "clear": "Eski narxni olib tashlash",
    "current": "Joriy narxni «eski narx» qilib ko'rsatish (chegirma)",
}
MAX_LINES = 2000


class RepricingError(Exception):
    pass


def _price_list():
    return PriceListModel.objects.filter(status="active", region__isnull=True).order_by("created_at").first()


def round_price(amount: Decimal, mode: str) -> Decimal:
    if amount <= 0:
        return amount
    if mode == "900":
        # 149 900, 150 900 … -- up to the next thousand, minus 100
        return (amount / 1000).to_integral_value(rounding=ROUND_CEILING) * 1000 - 100
    if mode in ("100", "1000", "5000", "10000"):
        step = Decimal(mode)
        return (amount / step).to_integral_value(rounding=ROUND_HALF_UP) * step
    return amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _subtree(category_ids) -> set:
    from apps.products.infrastructure.models import Category

    children: dict = {}
    for cid, parent in Category.objects.values_list("id", "parent_id"):
        children.setdefault(parent, []).append(cid)
    out, stack = set(), list(category_ids)
    while stack:
        c = stack.pop()
        if c in out:
            continue
        out.add(c)
        stack.extend(children.get(c, []))
    return out


@dataclass
class Filters:
    brands: list
    categories: list
    q: str = ""
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    stock: str = ""  # "" | "in" | "out"
    codes: list | None = None  # pasted SKUs / barcodes

    @classmethod
    def from_query(cls, g) -> Filters:
        def dec(key):
            raw = (g.get(key) or "").replace(" ", "").strip()
            try:
                return Decimal(raw) if raw else None
            except Exception:  # noqa: BLE001
                return None

        codes = [c.strip() for c in (g.get("codes") or "").replace(",", "\n").splitlines() if c.strip()]
        return cls(brands=[b for b in g.getlist("brand") if b], categories=[c for c in g.getlist("category") if c], q=(g.get("q") or "").strip()[:80],
                   price_min=dec("price_min"), price_max=dec("price_max"), stock=g.get("stock") or "", codes=codes or None)

    def as_dict(self) -> dict:
        return {"brands": self.brands, "categories": self.categories, "q": self.q, "price_min": str(self.price_min or ""), "price_max": str(self.price_max or ""),
                "stock": self.stock, "codes": self.codes or []}

    @property
    def empty(self) -> bool:
        return not (self.brands or self.categories or self.q or self.price_min is not None or self.price_max is not None or self.stock or self.codes)


def candidates(f: Filters, locale: str = "uz") -> list[dict]:
    """Active variants matching the filters, with their current price, old price, cost and sellable stock."""
    from apps.products.infrastructure.models import ProductTranslation, ProductVariant
    from apps.products.infrastructure.variant_labels import variant_label
    from apps.stores.infrastructure.availability import sellable
    from apps.stores.infrastructure.count_service import cost_info

    qs = ProductVariant.objects.filter(status="active", product__deleted_at__isnull=True).select_related("product", "package", "flavour").prefetch_related("flavour__translations")
    if f.brands:
        qs = qs.filter(product__brand_id__in=f.brands)
    if f.categories:
        qs = qs.filter(product__category_id__in=_subtree(f.categories))
    if f.codes:
        qs = qs.filter(Q(sku__in=f.codes) | Q(barcode__in=f.codes) | Q(extra_barcodes__barcode__in=f.codes)).distinct()
    if f.q:
        ids = ProductTranslation.objects.filter(name__icontains=f.q).values_list("product_id", flat=True)
        qs = qs.filter(Q(product_id__in=ids) | Q(sku__icontains=f.q) | Q(barcode=f.q))
    variants = list(qs[: MAX_LINES * 2])
    pl = _price_list()
    entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(price_list=pl, product_variant_id__in=[v.id for v in variants])} if pl else {}
    stock = sellable([v.id for v in variants])
    costs = cost_info([v.id for v in variants])
    names: dict = {}
    for t in ProductTranslation.objects.filter(product_id__in={v.product_id for v in variants}).values("product_id", "locale_code", "name"):
        names.setdefault(t["product_id"], {})[t["locale_code"]] = t["name"]
    out = []
    for v in variants:
        e = entries.get(v.id)
        price = e.base_price_amount if e else None
        if f.price_min is not None and (price is None or price < f.price_min):
            continue
        if f.price_max is not None and (price is None or price > f.price_max):
            continue
        units = stock.get(v.id, 0) or 0
        if f.stock == "in" and units <= 0 or f.stock == "out" and units > 0:
            continue
        cost, source = costs.get(v.id, (None, None))
        by = names.get(v.product_id, {})
        out.append({
            "variant_id": v.id, "product_id": v.product_id, "sku": v.sku, "barcode": v.barcode or "",
            "name": by.get(locale) or by.get("uz") or by.get("en") or v.sku, "label": variant_label(v, locale, package=False),
            "price": price, "compare_at": e.compare_at_price_amount if e else None,
            "cost": cost if source in ("receipt", "catalog") and cost else None, "stock": units,
        })
        if len(out) >= MAX_LINES:
            break
    out.sort(key=lambda r: (r["name"].lower(), r["label"]))
    return out


def compute(rows: list[dict], mode: str, value: Decimal | None, rounding: str, compare: str) -> list[dict]:
    """Adds new_price / new_compare / change % / margins / warnings to each candidate row."""
    for r in rows:
        price, cost = r["price"], r["cost"]
        new = None
        if mode == "fixed" and value is not None:
            new = value
        elif mode == "percent" and value is not None and price is not None:
            new = price * (1 + value / 100)
        elif mode == "amount" and value is not None and price is not None:
            new = price + value
        elif mode == "markup" and value is not None and cost:
            new = cost * (1 + value / 100)
        if new is not None:
            new = round_price(new, rounding)
        r["new_price"] = new
        if new is None:
            r["new_compare"] = r["compare_at"]
        elif compare == "clear":
            r["new_compare"] = None
        elif compare == "current":
            r["new_compare"] = price if price and price > new else None
        else:
            r["new_compare"] = r["compare_at"] if r["compare_at"] and r["compare_at"] > new else None
        r["delta"] = round(float((new - price) / price * 100), 1) if new is not None and price else None
        r["margin_old"] = round(float((price - cost) / price * 100), 1) if price and cost else None
        r["margin_new"] = round(float((new - cost) / new * 100), 1) if new and cost else None
        warn = []
        if new is None:
            warn.append("no_cost" if mode == "markup" else "no_price")
        elif new <= 0:
            warn.append("zero")
        elif cost and new < cost:
            warn.append("below_cost")
        r["warn"] = warn
        r["skip"] = bool(warn) and "below_cost" not in warn
    return rows


def _number() -> str:
    last = RepricingModel.objects.aggregate(m=Max("number"))["m"]
    return f"RP-{(int(last.split('-')[1]) + 1) if last else 1:06d}"


def create(lines: list[dict], title: str, rule: dict, actor: str, note: str = "", scheduled_for: datetime | None = None, reverts=None) -> RepricingModel:
    """lines: [{"variant_id", "old_price", "new_price", "old_compare", "new_compare", "cost"}] -- unchanged lines are dropped."""
    lines = [l for l in lines if l["new_price"] is not None and l["new_price"] > 0 and (l["new_price"] != l["old_price"] or l["new_compare"] != l["old_compare"])]
    if not lines:
        raise RepricingError("O'zgaradigan narx yo'q: qoidani yoki tanlovni tekshiring.")
    for l in lines:
        if l["new_compare"] is not None and l["new_compare"] <= l["new_price"]:
            l["new_compare"] = None
    for _attempt in range(5):
        try:
            with transaction.atomic():
                doc = RepricingModel.objects.create(number=_number(), title=title[:160] or "Narxlarni o'zgartirish", note=note[:255], rule=rule, created_by=actor[:150],
                                                    status="scheduled" if scheduled_for else "draft", scheduled_for=scheduled_for, reverts=reverts, lines_count=len(lines))
                RepricingLineModel.objects.bulk_create([RepricingLineModel(
                    repricing=doc, product_variant_id=l["variant_id"], old_price=l["old_price"], new_price=l["new_price"],
                    old_compare_at=l["old_compare"], new_compare_at=l["new_compare"], cost=l.get("cost")) for l in lines])
                return doc
        except IntegrityError:
            continue
    raise RepricingError("Hujjat raqamini ajratib bo'lmadi, qayta urinib ko'ring.")


def apply(doc: RepricingModel, actor: str) -> dict:
    """Sets every line's price through SetPrice (with history). Old values are re-read at this moment, so a revert restores what was really there."""
    from apps.pricing.infrastructure import composition as pricing_composition
    from apps.products.infrastructure.admin import _get_or_create_default_price_list

    caller = doc
    with transaction.atomic():
        doc = RepricingModel.objects.select_for_update().get(pk=doc.pk)
        if doc.status not in ("draft", "scheduled"):
            raise RepricingError("Hujjat allaqachon qo'llangan yoki bekor qilingan.")
        pl = _get_or_create_default_price_list()
        entries = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(price_list_id=pl.id)}
        service = pricing_composition.build_set_price()
        ok = failed = 0
        for line in doc.lines.all():
            e = entries.get(line.product_variant_id)
            line.old_price = e.base_price_amount if e else None
            line.old_compare_at = e.compare_at_price_amount if e else None
            try:
                with transaction.atomic():
                    service.execute(price_list_id=pl.id, product_variant_id=line.product_variant_id, base_amount=line.new_price, currency=pl.currency,
                                    cost_amount=e.cost_price_amount if e else None, sale_amount=e.sale_price_amount if e else None,
                                    compare_at_amount=line.new_compare_at, reason="rule_applied")
                line.applied, line.error = True, ""
                ok += 1
            except Exception as exc:  # noqa: BLE001 -- one bad line must not block the rest; it's shown on the document
                line.applied, line.error = False, str(exc)[:255]
                failed += 1
            line.save(update_fields=["old_price", "old_compare_at", "applied", "error"])
        doc.status, doc.applied_at, doc.applied_by = "applied", timezone.now(), actor[:150]
        doc.save(update_fields=["status", "applied_at", "applied_by"])
    caller.status, caller.applied_at, caller.applied_by = doc.status, doc.applied_at, doc.applied_by
    _refresh_storefront()
    return {"ok": ok, "failed": failed}


def _refresh_storefront() -> None:
    """Product list/detail caches and the search index pick up the new prices at once (not after their TTL)."""
    from apps.products.infrastructure.cache import invalidate_all_product_caches
    from apps.products.infrastructure.smart_search import invalidate_index

    transaction.on_commit(invalidate_all_product_caches)
    transaction.on_commit(invalidate_index)


def cancel(doc: RepricingModel) -> None:
    doc.refresh_from_db()
    if doc.status not in ("draft", "scheduled"):
        raise RepricingError("Faqat qoralama yoki rejalashtirilgan hujjatni bekor qilish mumkin.")
    doc.status = "cancelled"
    doc.save(update_fields=["status"])


def revert(doc: RepricingModel, actor: str) -> RepricingModel:
    """A mirror document (new = the old prices of the applied lines), applied at once."""
    doc.refresh_from_db()
    if doc.status != "applied":
        raise RepricingError("Faqat qo'llangan hujjatni qaytarish mumkin.")
    if doc.reverted_by.filter(status="applied").exists():
        raise RepricingError("Bu hujjat allaqachon qaytarilgan.")
    lines = [{"variant_id": l.product_variant_id, "old_price": l.new_price, "new_price": l.old_price, "old_compare": l.new_compare_at, "new_compare": l.old_compare_at, "cost": l.cost}
             for l in doc.lines.filter(applied=True) if l.old_price]
    back = create(lines, f"Qaytarish: {doc.title}"[:160], {"mode": "revert", "of": doc.number}, actor, note=f"{doc.number} dan oldingi narxlar", reverts=doc)
    apply(back, actor)
    return back


def apply_due(now: datetime | None = None) -> int:
    now = now or timezone.now()
    n = 0
    for doc in RepricingModel.objects.filter(status="scheduled", scheduled_for__lte=now):
        try:
            apply(doc, "Rejalashtirilgan")
            n += 1
        except RepricingError:
            continue
    return n


def lines_view(doc: RepricingModel, locale: str = "uz") -> list[dict]:
    from apps.stores.infrastructure.stock_service import variant_infos

    lines = list(doc.lines.all())
    infos = variant_infos([l.product_variant_id for l in lines], locale)
    out = []
    for l in lines:
        i = infos.get(l.product_variant_id)
        delta = round(float((l.new_price - l.old_price) / l.old_price * 100), 1) if l.old_price else None
        out.append({"l": l, "name": i.name if i else "—", "size": i.size if i else "", "sku": i.sku if i else "", "image": i.image_url if i else None, "delta": delta,
                    "below_cost": bool(l.cost and l.new_price < l.cost), "margin": round(float((l.new_price - l.cost) / l.new_price * 100), 1) if l.cost and l.new_price else None})
    out.sort(key=lambda r: r["name"].lower())
    return out

