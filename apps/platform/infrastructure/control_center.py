"""
Nazorat markazi -- the control centre: a 2-minute scan (beat task platform.control_scan) that turns till and
operations data into ControlAlert rows, and pushes the new ones to NutriZoneAnalyticsBot.

Suspicious till operations (thresholds: ControlSettings, editable on /django-admin/control/):
  big_discount     a completed receipt whose basket discount is >= N % of the basket or >= N so'm
  quick_refund     money returned within N minutes of the sale
  refund_burst     one cashier made >= N returns today
  void_burst       one cashier cancelled >= N receipts that had items in them today
  cash_difference  a closed shift whose counted drawer differs from the expected cash by >= N so'm

Operational incidents (closed automatically once the cause is gone):
  shift_missing    a working branch kassa (has a PIN, sold in the last 14 days) is not open N minutes after opening time
  shift_overdue    a shift has been open longer than N hours (forgotten Z-report)
  late_order       an online order stuck in confirmed / packing (ordering admin LATE_HOURS)
  payment_errors   the payment callbacks answered with a server error >= N times in 30 minutes

Every finding has a unique key, so re-running the scan (or two workers) never duplicates it, and the facts are frozen
when found. Telegram: the analytics allowlist gets everything, a branch owner who started the bot only their branches;
one message per recipient per scan (a digest when several things happened at once). Nothing older than
NOTIFY_WINDOW is pushed, so switching the bot on later never floods it with old news.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

logger = logging.getLogger("nutrizone.platform.control")
TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal(0)
NOTIFY_WINDOW = timedelta(hours=6)
ACTIVE_KASSA_DAYS = 14
LOCK_KEY = "control_center:scan"
DIGEST_LIMIT = 8
DAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

KINDS = {
    "big_discount": ("🏷", "Katta chegirma"),
    "quick_refund": ("↩️", "Tezkor qaytarish"),
    "refund_burst": ("🔁", "Ko'p qaytarish"),
    "void_burst": ("🗑", "Bekor qilingan cheklar"),
    "cash_difference": ("💵", "Kassa farqi"),
    "shift_missing": ("🔒", "Smena ochilmagan"),
    "shift_overdue": ("⏰", "Smena yopilmagan"),
    "late_order": ("🚚", "Kechikayotgan buyurtma"),
    "payment_errors": ("💳", "To'lov tizimi xatosi"),
    "low_stock": ("📦", "Minimal qoldiqdan past"),
    "stock_forecast": ("📉", "Tez orada tugaydi"),
    "expiry": ("⏳", "Yaroqlilik muddati"),
}
GROUPS = {"risk": ("big_discount", "quick_refund", "refund_burst", "void_burst", "cash_difference"),
          "ops": ("shift_missing", "shift_overdue", "late_order", "payment_errors"),
          "stock": ("low_stock", "stock_forecast", "expiry")}
AUTO_RESOLVED = ("shift_missing", "shift_overdue", "late_order", "low_stock", "stock_forecast", "expiry")
# a stock problem that comes back after it was fixed is news again: its (resolved) row is re-opened and re-sent
REOPENABLE = ("low_stock", "stock_forecast")
EXPIRY_TIERS = (30, 60, 90)
SNOOZE = timedelta(hours=24)  # "Ko'rildi" on a stock problem that is still there silences it for a day


def som(v) -> str:
    return f"{int(round(Decimal(v or 0))):,}".replace(",", " ") + " so'm"


def _local(dt) -> datetime:
    return timezone.localtime(dt, TZ)


def _hm(dt) -> str:
    return _local(dt).strftime("%H:%M") if dt else "—"


def _url(name: str, *args, query: str = "") -> str:
    try:
        return reverse(name, args=args) + (f"?{query}" if query else "")
    except NoReverseMatch:
        return ""


def today_start(now=None) -> datetime:
    local = _local(now or timezone.now())
    return datetime.combine(local.date(), time.min, tzinfo=TZ)


def settings_obj():
    from apps.platform.infrastructure.models import ControlSettings

    return ControlSettings.load()


# ---------------------------------------------------------------- findings


class Finding(dict):
    """key, kind, severity, store_id, title, facts, link, actor_name, happened_at."""


def _finding(key, kind, severity, title, facts, happened_at, store_id=None, link="", actor="") -> Finding:
    return Finding(key=key, kind=kind, severity=severity, title=title, facts=[[str(a), str(b)] for a, b in facts],
                   happened_at=happened_at, store_id=store_id, link=link, actor_name=(actor or "")[:150])


def _names(ids) -> dict:
    from apps.pos.infrastructure import sales_reports as rep

    return rep.people_names(ids)


def _store_map() -> dict:
    from apps.stores.infrastructure.models import Store

    return {str(s.id): s for s in Store.objects.all()}


def _store_label(stores: dict, store_id) -> str:
    from apps.stores.infrastructure.pos_cashiers import kassa_name

    s = stores.get(str(store_id)) if store_id else None
    return kassa_name(s) if s else "Dashboard kassa"


def _known_store(stores: dict, store_id):
    return store_id if store_id and str(store_id) in stores else None


def rule_big_discount(cfg, since, stores) -> list[Finding]:
    from apps.pos.infrastructure.models import SaleModel

    line_total = F("line_items__unit_price_amount") * F("line_items__quantity")
    rows = list(SaleModel.objects.filter(status__in=("completed", "refunded"), completed_at__gte=since, discount_amount__gt=0)
                .annotate(basket=Sum(line_total)).values("id", "branch_id", "cashier_id", "receipt_number", "basket", "discount_amount",
                                                         "discount_reason", "completed_at", "coins_redeemed", "delivery_fee_amount"))
    names = _names({r["cashier_id"] for r in rows})
    out = []
    for r in rows:
        basket, disc = r["basket"] or ZERO, r["discount_amount"]
        pct = float(disc / basket * 100) if basket else 100.0
        if pct < cfg.discount_percent and disc < cfg.discount_amount:
            continue
        critical = pct >= cfg.discount_percent * 2 or disc >= cfg.discount_amount * 2
        who = names.get(r["cashier_id"]) or "—"
        out.append(_finding(
            f"big_discount:{r['id']}", "big_discount", "critical" if critical else "warning",
            f"{r['receipt_number'] or 'Chek'}: {pct:.0f}% chegirma ({som(disc)})",
            [("Filial", _store_label(stores, r["branch_id"])), ("Kassir", who), ("Savat", som(basket)),
             ("Chegirma", f"{som(disc)} · {pct:.1f}%"), ("Sabab", r["discount_reason"] or "ko'rsatilmagan"),
             ("To'landi", som(basket - disc + r["delivery_fee_amount"])), ("Vaqti", _hm(r["completed_at"]))],
            r["completed_at"], _known_store(stores, r["branch_id"]), _url("admin:pos_salemodel_change", r["id"]), who))
    return out


def rule_quick_refund(cfg, since, stores) -> list[Finding]:
    from apps.pos.infrastructure.models import SaleRefundModel

    gap = timedelta(minutes=cfg.quick_refund_minutes)
    refunds = list(SaleRefundModel.objects.filter(created_at__gte=since).select_related("sale"))
    names = _names({x.cashier_id for x in refunds} | {x.sale.cashier_id for x in refunds})
    out = []
    for x in refunds:
        sold = x.sale.completed_at
        if not sold or x.created_at - sold > gap:
            continue
        minutes = max(int((x.created_at - sold).total_seconds() // 60), 0)
        who = names.get(x.cashier_id) or "—"
        seller = names.get(x.sale.cashier_id) or "—"
        out.append(_finding(
            f"quick_refund:{x.id}", "quick_refund", "critical" if x.split.get("cash") and Decimal(str(x.split["cash"])) > 0 else "warning",
            f"{x.sale.receipt_number or 'Chek'}: {minutes} daqiqada qaytarildi ({som(x.amount + x.coins)})",
            [("Filial", _store_label(stores, x.sale.branch_id)), ("Qaytargan", who), ("Sotgan", seller),
             ("Sotuv", _hm(sold)), ("Qaytarish", f"{_hm(x.created_at)} · {x.number}"), ("Qaytarilgan pul", som(x.amount)),
             ("Sabab", x.reason or "ko'rsatilmagan")],
            x.created_at, _known_store(stores, x.sale.branch_id), _url("admin:pos_salemodel_change", x.sale_id), who))
    return out


def rule_refund_burst(cfg, since, stores) -> list[Finding]:
    from apps.pos.infrastructure.models import SaleRefundModel

    rows = list(SaleRefundModel.objects.filter(created_at__gte=since).values("cashier_id", "sale__branch_id")
                .annotate(n=Count("id"), value=Sum("value"), money=Sum("amount"), last=Max("created_at")).filter(n__gte=cfg.refunds_per_cashier))
    names = _names({r["cashier_id"] for r in rows})
    day = _local(since).date().isoformat()
    return [_finding(
        f"refund_burst:{r['cashier_id']}:{r['sale__branch_id']}:{day}", "refund_burst", "critical",
        f"{names.get(r['cashier_id']) or 'Kassir'}: bugun {r['n']} ta qaytarish",
        [("Filial", _store_label(stores, r["sale__branch_id"])), ("Kassir", names.get(r["cashier_id"]) or "—"),
         ("Qaytarishlar", f"{r['n']} ta (chegara {cfg.refunds_per_cashier})"), ("Mahsulot qiymati", som(r["value"])),
         ("Qaytarilgan pul", som(r["money"])), ("Oxirgisi", _hm(r["last"]))],
        r["last"], _known_store(stores, r["sale__branch_id"]), _url("admin:pos_salemodel_changelist", query="status__exact=refunded"),
        names.get(r["cashier_id"]) or "") for r in rows]


def rule_void_burst(cfg, since, stores) -> list[Finding]:
    from apps.pos.infrastructure.models import SaleModel

    line_total = F("line_items__unit_price_amount") * F("line_items__quantity")
    voided = (SaleModel.objects.filter(status="voided", voided_at__gte=since, line_items__isnull=False)
              .values("id", "cashier_id", "branch_id").annotate(value=Sum(line_total), last=Max("voided_at")))
    groups: dict = defaultdict(lambda: {"n": 0, "value": ZERO, "last": None})
    for v in voided:
        g = groups[(v["cashier_id"], v["branch_id"])]
        g["n"] += 1
        g["value"] += v["value"] or ZERO
        g["last"] = max(filter(None, (g["last"], v["last"])))
    names = _names({k[0] for k in groups})
    day = _local(since).date().isoformat()
    out = []
    for (cashier, branch), g in groups.items():
        if g["n"] < cfg.voids_per_cashier:
            continue
        who = names.get(cashier) or "Kassir"
        out.append(_finding(
            f"void_burst:{cashier}:{branch}:{day}", "void_burst", "warning",
            f"{who}: bugun {g['n']} ta chek bekor qilindi",
            [("Filial", _store_label(stores, branch)), ("Kassir", who), ("Bekor qilingan cheklar", f"{g['n']} ta (chegara {cfg.voids_per_cashier})"),
             ("Savatlardagi summa", som(g["value"])), ("Oxirgisi", _hm(g["last"]))],
            g["last"], _known_store(stores, branch), _url("admin:pos_salemodel_changelist", query="status__exact=voided"), who))
    return out


def rule_cash_difference(cfg, since, stores) -> list[Finding]:
    from apps.stores.infrastructure.models import CashSession
    from apps.stores.infrastructure.pos_service import shift_number

    out = []
    for s in CashSession.objects.filter(status="closed", closed_at__gte=since, cash_difference__isnull=False).select_related("store"):
        diff = s.cash_difference
        if abs(diff) < cfg.cash_difference:
            continue
        short = diff < 0
        who = s.closed_by_name or "—"
        out.append(_finding(
            f"cash_difference:{s.id}", "cash_difference", "critical" if short else "warning",
            f"{_store_label(stores, s.store_id)}: kassada {'kamomad' if short else 'ortiqcha'} {som(abs(diff))}",
            [("Filial", _store_label(stores, s.store_id)), ("Smena", f"№{shift_number(s)} · {_hm(s.opened_at)}–{_hm(s.closed_at)}"),
             ("Kutilgan naqd", som(s.expected_cash)), ("Sanalgan naqd", som(s.counted_cash)),
             ("Farq", ("−" if short else "+") + som(abs(diff))), ("Yopgan", who), ("Izoh", s.closing_note or "—")],
            s.closed_at, s.store_id, _url("admin:stores_cashsession_change", s.id), who))
    return out


def rule_shift_overdue(cfg, now, stores) -> list[Finding]:
    from apps.stores.infrastructure.models import CashSession
    from apps.stores.infrastructure.pos_service import shift_number

    limit = now - timedelta(hours=cfg.shift_max_hours)
    out = []
    for s in CashSession.objects.filter(status="open", opened_at__lt=limit).select_related("store"):
        hours = int((now - s.opened_at).total_seconds() // 3600)
        out.append(_finding(
            f"shift_overdue:{s.id}", "shift_overdue", "warning",
            f"{_store_label(stores, s.store_id)}: smena {hours} soatdan beri ochiq",
            [("Filial", _store_label(stores, s.store_id)), ("Smena", f"№{shift_number(s)}"),
             ("Ochilgan", _local(s.opened_at).strftime("%d.%m %H:%M")), ("Ochgan", s.opened_by_name or (s.opened_by.full_name if s.opened_by else "—"))],
            now, s.store_id, _url("admin:stores_cashsession_change", s.id), s.opened_by_name or ""))
    return out


def opening_time(store, day) -> tuple[time | None, time | None]:
    """(open, close) of a branch on a local date -- special_hours win over the weekly working_hours; (None, None) when closed/unknown."""
    entry = next((x for x in (store.special_hours or []) if isinstance(x, dict) and x.get("date") == day.isoformat()), None)
    if entry is None:
        entry = (store.working_hours or {}).get(DAY_CODES[day.weekday()]) or {}
    if not entry or entry.get("closed"):
        return None, None
    try:
        return time.fromisoformat(entry["open"]), time.fromisoformat(entry["close"])
    except (KeyError, TypeError, ValueError):
        return None, None


def active_kassas(now) -> list:
    """Selling branches whose till is really used: a kassa PIN is set and it sold something in the last 14 days."""
    from apps.pos.infrastructure.models import SaleModel
    from apps.stores.infrastructure.models import Store

    recent = set(SaleModel.objects.filter(channel="store", status__in=("completed", "refunded"), completed_at__gte=now - timedelta(days=ACTIVE_KASSA_DAYS))
                 .values_list("branch_id", flat=True).distinct())
    return [s for s in Store.objects.filter(kind="store", status="active").exclude(pos_pin_hash="") if s.id in recent]


def rule_shift_missing(cfg, now, stores) -> list[Finding]:
    from apps.stores.infrastructure.models import CashSession

    local = _local(now)
    start = today_start(now)
    out = []
    for store in active_kassas(now):
        opens, closes = opening_time(store, local.date())
        if opens is None:
            continue
        due = datetime.combine(local.date(), opens, tzinfo=TZ) + timedelta(minutes=cfg.shift_open_grace_minutes)
        if not (due <= local < datetime.combine(local.date(), closes, tzinfo=TZ)):
            continue
        if CashSession.objects.filter(store=store).filter(Q(status="open") | Q(opened_at__gte=start)).exists():
            continue
        late = int((local - datetime.combine(local.date(), opens, tzinfo=TZ)).total_seconds() // 60)
        from apps.platform.infrastructure.business_analytics import duration

        out.append(_finding(
            f"shift_missing:{store.id}:{local.date().isoformat()}", "shift_missing", "warning",
            f"{store.name}: kassa hali ochilmagan",
            [("Filial", store.name), ("Ish vaqti", f"{opens:%H:%M}–{closes:%H:%M}"), ("Kechikish", duration(late))],
            now, store.id, _url("admin:stores_cashsession_changelist", query=f"store__id__exact={store.id}")))
    return out


def rule_late_orders(cfg, now, stores) -> list[Finding]:
    from apps.ordering.infrastructure.admin import LATE_HOURS, late_orders
    from apps.ordering.infrastructure.models import OrderModel
    from apps.platform.infrastructure.business_analytics import STATUS_LABELS, duration

    line_total = ExpressionWrapper(F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"),
                                   output_field=DecimalField(max_digits=16, decimal_places=2))
    out = []
    for o in (late_orders(OrderModel.objects.all()).annotate(total_amount=Sum(line_total, filter=Q(lines__status="active")))
              .values("id", "order_number", "status", "updated_at", "placed_at", "fulfilment_store_id", "shipping_recipient_name", "total_amount")[:50]):
        idle = int((now - o["updated_at"]).total_seconds() // 60)
        out.append(_finding(
            f"late_order:{o['id']}", "late_order", "critical" if idle >= LATE_HOURS * 60 * 2 else "warning",
            f"{o['order_number']}: {duration(idle)} harakatsiz",
            [("Holati", STATUS_LABELS.get(o["status"], o["status"])), ("Mijoz", o["shipping_recipient_name"] or "—"),
             ("Summa", som(o["total_amount"])), ("Berilgan", _local(o["placed_at"]).strftime("%d.%m %H:%M") if o["placed_at"] else "—"),
             ("Filial", _store_label(stores, o["fulfilment_store_id"]) if o["fulfilment_store_id"] else "Markaziy ombor")],
            now, _known_store(stores, o["fulfilment_store_id"]), _url("admin:ordering_ordermodel_change", o["id"])))
    return out


def rule_payment_errors(cfg, now, stores) -> list[Finding]:
    from apps.payment.infrastructure.models import PaymentCallbackLog

    rows = PaymentCallbackLog.objects.filter(created_at__gte=now - timedelta(minutes=30), http_status__gte=500).values("provider").annotate(n=Count("id"), last=Max("created_at"))
    hour = _local(now).strftime("%Y%m%d%H")
    return [_finding(
        f"payment_errors:{r['provider']}:{hour}", "payment_errors", "critical",
        f"{r['provider'].capitalize()}: 30 daqiqada {r['n']} ta server xatosi",
        [("To'lov tizimi", r["provider"].capitalize()), ("Xatolar", f"{r['n']} ta (chegara {cfg.payment_errors})"), ("Oxirgisi", _hm(r["last"]))],
        r["last"], None, _url("admin:payment_paymentcallbacklog_changelist", query=f"provider={r['provider']}")) for r in rows if r["n"] >= cfg.payment_errors]


# ---------------------------------------------------------------- stock (planning_service: rules, sales speed, transfers on the way)


def _branch_plans(now) -> list:
    """(store, source, plan lines) for every active selling branch -- one planning pass shared by the stock rules."""
    from apps.stores.infrastructure import planning_service
    from apps.stores.infrastructure.models import Store

    out = []
    for store in Store.objects.filter(kind="store", status="active").order_by("name"):
        source = planning_service.default_source(exclude=store)
        out.append((store, source, planning_service.plan(store, source)["lines"]))
    return out


def _stock_facts(store, source, ln, days=None) -> list:
    from apps.stores.infrastructure import planning_service

    facts = [("Filial", store.name), ("Mahsulot", ln.info.name), ("Qoldiq (sotuvga)", f"{ln.available} dona")]
    if ln.rule:
        facts.append(("Minimal / to'ldirish", f"{ln.rule.min_quantity} / {ln.rule.target_quantity}"))
    if ln.incoming:
        facts.append(("Yo'lda (transfer)", f"{ln.incoming} dona"))
    if ln.sold:
        facts.append(("Sotuv tezligi", f"{ln.sold / planning_service.SALES_DAYS:.1f} dona/kun ({ln.sold} — 30 kun)"))
    if days is not None:
        facts.append(("Taxminan tugaydi", f"{days} kunda"))
    want = ln.suggest if ln.rule else max(0, planning_service.suggested_rule(ln.sold)[1] - ln.projected)
    if want:
        facts.append(("Tavsiya etilgan transfer", f"{want} dona" + (f" ({source.name} da {ln.source_available})" if source else "")))
    return facts


def rule_low_stock(cfg, now, stores, plans=None) -> list[Finding]:
    """A branch product with a reorder rule is at / under its minimum (counting what is already on the way)."""
    if not cfg.stock_alerts:
        return []
    out = []
    for store, source, lines in plans if plans is not None else _branch_plans(now):
        for ln in lines:
            if not ln.needs:
                continue
            empty = ln.available == 0
            out.append(_finding(
                f"low_stock:{store.id}:{ln.variant_id}", "low_stock", "critical" if empty else "warning",
                f"{store.name}: {ln.info.name} — " + ("tugadi" if empty else f"{ln.available} dona qoldi (minimal {ln.rule.min_quantity})"),
                _stock_facts(store, source, ln), now, store.id, _url("admin:nz_wms_stock_product", ln.variant_id)))
    return out


def rule_stock_forecast(cfg, now, stores, plans=None) -> list[Finding]:
    """At the current sales speed a branch runs out within `forecast_days` (and isn't already under its minimum)."""
    if not cfg.stock_alerts:
        return []
    out = []
    for store, source, lines in plans if plans is not None else _branch_plans(now):
        for ln in lines:
            days = ln.days_cover
            if ln.needs or not ln.available or days is None or days > cfg.forecast_days or ln.projected > ln.available + ln.per_day * cfg.forecast_days:
                continue  # a transfer on its way already covers the horizon
            out.append(_finding(
                f"stock_forecast:{store.id}:{ln.variant_id}", "stock_forecast", "warning",
                f"{store.name}: {ln.info.name} ≈{days} kunda tugaydi",
                _stock_facts(store, source, ln, days), now, store.id, _url("admin:nz_wms_stock_product", ln.variant_id)))
    return out


def rule_expiry(cfg, now, stores) -> list[Finding]:
    """A batch with stock whose expiry is within 90 / 60 / 30 days (one alert per tier) or already past."""
    from apps.stores.infrastructure import stock_service
    from apps.stores.infrastructure.models import StockBatch

    if not cfg.stock_alerts:
        return []
    today = _local(now).date()
    horizon = today + timedelta(days=max(EXPIRY_TIERS))
    batches = list(StockBatch.objects.filter(quantity__gt=0, expiry_date__isnull=False, expiry_date__lte=horizon).exclude(store__status="inactive").select_related("store"))
    infos = stock_service.variant_infos({b.product_variant_id for b in batches})
    out = []
    for b in batches:
        days = (b.expiry_date - today).days
        typo = b.expiry_date.year < today.year - 2  # e.g. 0002-05-01: a receipt typo, not goods that expired centuries ago
        tier = "typo" if typo else "expired" if days < 0 else str(next(t for t in EXPIRY_TIERS if days <= t))
        name = infos[b.product_variant_id].name if b.product_variant_id in infos else "Mahsulot"
        where = b.store.name
        out.append(_finding(
            f"expiry:{b.id}:{tier}", "expiry", "critical" if tier in ("expired", "30") else "warning",
            f"{where}: {name} — " + ("yaroqlilik sanasi noto'g'ri kiritilgan" if typo else "muddati o'tgan" if days < 0 else f"{days} kun qoldi") + f" ({b.quantity} dona)",
            [("Joy", where), ("Mahsulot", name), ("Partiya", b.batch_number or "partiyasiz"), ("Yaroqlilik", f"{b.expiry_date.day:02}.{b.expiry_date.month:02}.{b.expiry_date.year:04}"),
             ("Qoldi", "—" if typo else "muddati o'tgan" if days < 0 else f"{days} kun"), ("Miqdor", f"{b.quantity} dona"),
             ("Tavsiya", "sanani tuzating: inventarizatsiyada partiyani to'g'ri muddat bilan qayta sanang" if typo else "hisobdan chiqarish (Hisobdan chiqarish sahifasi)" if days < 0 else "birinchi navbatda sotish / aksiya" if days <= 30 else "FEFO bo'yicha oldinga qo'yish")],
            now, b.store_id if b.store.kind == "store" else None, _url("admin:nz_wms_expiry")))
    return out


def stock_rules(cfg, now, stores) -> list[Finding]:
    plans = _branch_plans(now) if cfg.stock_alerts else []
    return rule_low_stock(cfg, now, stores, plans) + rule_stock_forecast(cfg, now, stores, plans) + rule_expiry(cfg, now, stores)


RISK_RULES = (rule_big_discount, rule_quick_refund, rule_refund_burst, rule_void_burst, rule_cash_difference)
OPS_RULES = (rule_shift_overdue, rule_shift_missing, rule_late_orders, rule_payment_errors, stock_rules)


# ---------------------------------------------------------------- scan


def _resolve_gone(found_keys: set, now) -> int:
    """Incidents whose cause is gone (shift opened / closed, order moved on) close themselves."""
    from apps.platform.infrastructure.models import ControlAlert

    gone = ControlAlert.objects.filter(kind__in=AUTO_RESOLVED, resolved_at__isnull=True).exclude(key__in=found_keys)
    return gone.update(resolved_at=now, resolved_by_name="Avtomatik", resolution_note="Sabab bartaraf etildi")


def _store(finding: Finding):
    return finding.pop("store_id", None)


def scan(now=None) -> dict:
    """Runs every rule, stores the new findings, auto-closes the incidents that are over. Returns counts."""
    from apps.platform.infrastructure.models import ControlAlert

    now = now or timezone.now()
    cfg = settings_obj()
    if not cfg.enabled:
        return {"skipped": "disabled"}
    since = today_start(now)
    stores = _store_map()
    found: list[Finding] = []
    failed = []
    for rule in RISK_RULES:
        try:
            found += rule(cfg, since, stores)
        except Exception:  # noqa: BLE001 - one broken rule never stops the others
            logger.exception("control: %s failed", rule.__name__)
            failed.append(rule.__name__)
    for rule in OPS_RULES:
        try:
            found += rule(cfg, now, stores)
        except Exception:  # noqa: BLE001
            logger.exception("control: %s failed", rule.__name__)
            failed.append(rule.__name__)
    rows = {a.key: a for a in ControlAlert.objects.filter(key__in=[f["key"] for f in found])}
    created = 0
    for f in found:
        row = rows.get(f["key"])
        if row is not None:
            snoozed = row.resolved_by_name != "Avtomatik" and row.resolved_at and row.resolved_at > now - SNOOZE
            if row.resolved_at and row.kind in REOPENABLE and not snoozed:  # back after a fix (or a 24 h snooze): fresh facts, open, notify again
                ControlAlert.objects.filter(pk=row.pk).update(resolved_at=None, resolved_by_name="", resolution_note="", notified_at=None,
                                                              happened_at=f["happened_at"], title=f["title"], facts=f["facts"], severity=f["severity"])
                created += 1
            continue
        store_id = _store(f)
        try:
            with transaction.atomic():
                ControlAlert.objects.create(store_id=store_id, **f)
            created += 1
        except IntegrityError:
            continue  # another worker stored it first
    resolved = 0 if failed else _resolve_gone({f["key"] for f in found}, now)
    return {"found": len(found), "created": created, "resolved": resolved, "failed": failed}


def run() -> dict:
    """The beat task: scan + Telegram, never two at once."""
    if not cache.add(LOCK_KEY, "1", timeout=110):
        return {"skipped": "locked"}
    try:
        out = scan()
        if "skipped" not in out:
            try:
                out["telegram"] = notify_pending()
            except Exception:  # noqa: BLE001
                logger.exception("control: telegram failed")
                out["telegram"] = "error"
        return out
    finally:
        cache.delete(LOCK_KEY)


# ---------------------------------------------------------------- reading


def open_alerts(store_ids=None):
    from apps.platform.infrastructure.models import ControlAlert

    qs = ControlAlert.objects.filter(resolved_at__isnull=True).select_related("store")
    if store_ids is not None:
        qs = qs.filter(store_id__in=list(store_ids))
    return qs.order_by("severity", "-happened_at")  # "critical" < "warning"


def resolve(alert_id, by_name: str, note: str = "", store_ids=None) -> bool:
    from apps.platform.infrastructure.models import ControlAlert

    qs = ControlAlert.objects.filter(id=alert_id, resolved_at__isnull=True)
    if store_ids is not None:
        qs = qs.filter(store_id__in=list(store_ids))
    return bool(qs.update(resolved_at=timezone.now(), resolved_by_name=(by_name or "—")[:150], resolution_note=(note or "")[:255]))


def live(store_ids=None, now=None) -> dict:
    """Right now: today's money vs yesterday at the same time, every branch's till (open shift, cashier, last sale) and the open alerts."""
    from apps.platform.infrastructure import business_analytics as ba
    from apps.pos.infrastructure import sales_reports as rep
    from apps.pos.infrastructure.models import SaleModel
    from apps.stores.infrastructure.models import CashSession

    now = now or timezone.now()
    r = ba.build(ba.period("today", now=now), sections=("stores",), store_ids=store_ids)
    shifts: dict = {}
    for s in CashSession.objects.filter(status="open").select_related("store", "opened_by"):
        key = str(s.store_id) if s.store.kind == "store" else rep.CENTRAL
        shifts[key] = {"opened_at": s.opened_at, "by": s.opened_by_name or (s.opened_by.full_name if s.opened_by else "") or "—",
                       "hours": round((now - s.opened_at).total_seconds() / 3600, 1)}
    last_sale = {}
    for row in SaleModel.objects.filter(status__in=("completed", "refunded"), completed_at__gte=today_start(now)).values("branch_id", "channel").annotate(last=Max("completed_at")):
        key = rep.branch_key(row)
        last_sale[key] = max(filter(None, (last_sale.get(key), row["last"])))
    alerts = list(open_alerts(store_ids))
    per_store = defaultdict(lambda: {"critical": 0, "warning": 0})
    for a in alerts:
        per_store[str(a.store_id) if a.store_id else ""][a.severity] += 1
    stores = _store_map()
    kassa_ids = {str(s.id) for s in active_kassas(now)}
    branches = []
    for s in r.get("stores") or []:
        if s["kind"] == "online":
            continue
        st = stores.get(s["key"])
        opens, closes = opening_time(st, _local(now).date()) if st else (None, None)
        branches.append({**s, "shift": shifts.get(s["key"]), "last_sale": last_sale.get(s["key"]), "alerts": per_store.get(s["key"], {"critical": 0, "warning": 0}),
                         "hours": f"{opens:%H:%M}–{closes:%H:%M}" if opens else "", "kassa": s["key"] in kassa_ids or s["key"] in shifts})
    online = next((s for s in r.get("stores") or [] if s["kind"] == "online"), None)
    return {
        "generated_at": _local(now), "overview": r.get("overview"), "branches": branches, "online": online,
        "open_shifts": sum(1 for b in branches if b["shift"]), "kassa_count": sum(1 for b in branches if b["kassa"]),
        "alerts": alerts, "critical": sum(1 for a in alerts if a.severity == "critical"), "warning": sum(1 for a in alerts if a.severity == "warning"),
        "sections_ok": r["sections_ok"],
    }


# ---------------------------------------------------------------- Telegram


def dashboard_url() -> str | None:
    from django.conf import settings

    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return f"{base}/django-admin/control/" if base.startswith("https://") else None


def alert_blocks(alert, R) -> list[str]:
    icon, label = KINDS.get(alert.kind, ("•", alert.kind))
    level = "🔴" if alert.severity == "critical" else "🟠"
    return [R.h(3, f"{level} {icon} {R.e(alert.title)}"),
            R.table([], [[R.e(a), R.b(b) if i == 0 else R.e(b)] for i, (a, b) in enumerate(alert.facts)], align=["left", "left"]),
            R.footer(f"{R.e(label)} · {R.time_tag(alert.happened_at, 't', _hm(alert.happened_at))}")]


def alert_text(alert) -> str:
    from html import escape

    icon, _label = KINDS.get(alert.kind, ("•", alert.kind))
    level = "🔴" if alert.severity == "critical" else "🟠"
    lines = [f"{level} {icon} <b>{escape(alert.title)}</b>"] + [f"{escape(a)}: <b>{escape(b)}</b>" for a, b in alert.facts]
    return "\n".join(lines)


def alerts_doc(alerts: list, title: str = ""):
    from apps.telegram_bot.infrastructure import rich as R

    doc = R.RichDoc()
    crit = sum(1 for a in alerts if a.severity == "critical")
    if len(alerts) == 1:
        doc.add(R.h(2, "🛡 Nazorat markazi"), *alert_blocks(alerts[0], R))
        doc.fallback = "🛡 <b>Nazorat markazi</b>\n\n" + alert_text(alerts[0])
        return doc
    head = title or f"🛡 Nazorat: {len(alerts)} ta yangi signal"
    doc.add(R.h(2, R.e(head)), R.p(f"🔴 Jiddiy: <b>{crit}</b> · 🟠 Diqqat: <b>{len(alerts) - crit}</b>"))
    for a in alerts[:DIGEST_LIMIT]:
        doc.add(R.details(f"{'🔴' if a.severity == 'critical' else '🟠'} {R.e(a.title)}", "".join(alert_blocks(a, R)[1:]), open_=a.severity == "critical"))
    if len(alerts) > DIGEST_LIMIT:
        doc.add(R.p(f"… yana <b>{len(alerts) - DIGEST_LIMIT}</b> ta — Dashboard → Nazorat markazi"))
    doc.fallback = f"<b>{head}</b>\n\n" + "\n\n".join(alert_text(a) for a in alerts[:DIGEST_LIMIT])
    return doc


def alert_keyboard(alerts: list) -> list:
    rows = []
    stock = [a for a in alerts if a.kind in ("low_stock", "stock_forecast") and a.store_id]
    if len(alerts) == 1 and stock:
        rows.append([{"text": "📦 Transfer so'rash", "callback_data": f"an:trq:{alerts[0].id}"}])
    elif stock:
        names = {}
        for a in stock:
            names.setdefault(a.store_id, a.store.name if a.store else "Filial")
        for sid, name in list(names.items())[:3]:
            rows.append([{"text": f"📦 {name}: kamlarini to'ldirish", "callback_data": f"an:trs:{sid}"}])
    if len(alerts) == 1:
        rows.append([{"text": "✅ Ko'rildi, yopish", "callback_data": f"an:ack:{alerts[0].id}"}])
    url = dashboard_url()
    if url:
        rows.append([{"text": "🖥 Nazorat markazi", "url": url}])
    rows.append([{"text": "🛡 Hozirgi holat", "callback_data": "an:nazorat"}])
    return rows


def audience() -> list[dict]:
    """[{chat_id, store_ids (None = everything)}]: the analytics allowlist, then branch owners who started the bot."""
    from apps.telegram_bot.infrastructure import analytics_bot, staff_access

    out, seen = [], set()
    for chat in analytics_bot.recipients():
        out.append({"chat_id": chat, "store_ids": None})
        seen.add(str(chat))
    for sub in staff_access.subscribers("analytics"):
        if str(sub.chat_id) in seen:
            continue
        stores, _name = staff_access.owned_stores(sub.telegram_user_id or sub.chat_id)
        if stores:
            out.append({"chat_id": str(sub.chat_id), "store_ids": {st.id for st in stores}})
            seen.add(str(sub.chat_id))
    return out


def notify_pending(now=None) -> dict:
    """Pushes the not-yet-sent open findings of the last NOTIFY_WINDOW: one message per recipient."""
    from apps.platform.infrastructure.models import ControlAlert
    from apps.telegram_bot.infrastructure import analytics_bot
    from apps.telegram_bot.infrastructure import rich as R

    now = now or timezone.now()
    cfg = settings_obj()
    pending = list(ControlAlert.objects.filter(notified_at__isnull=True, resolved_at__isnull=True, created_at__gte=now - NOTIFY_WINDOW)
                   .order_by("severity", "happened_at"))
    if not pending:
        return {"pending": 0}
    if not cfg.telegram_enabled or not analytics_bot.is_live():
        return {"pending": len(pending), "skipped": "telegram off"}
    sent = failed = 0
    for who in audience():
        mine = [a for a in pending if who["store_ids"] is None or a.store_id in who["store_ids"]]
        if not mine:
            continue
        try:
            R.send(analytics_bot.token(), who["chat_id"], alerts_doc(mine), alert_keyboard(mine))
            sent += 1
        except R.RichSendError as exc:
            failed += 1
            logger.warning("control alert to %s failed: %s", who["chat_id"], exc)
            if R.is_blocked(exc):
                from apps.telegram_bot.infrastructure import staff_access

                staff_access.deactivate("analytics", who["chat_id"])
        except Exception:  # noqa: BLE001
            failed += 1
            logger.exception("control alert to %s failed", who["chat_id"])
    if sent or not failed:  # all failed -> keep them pending, the next scan retries
        ControlAlert.objects.filter(id__in=[a.id for a in pending]).update(notified_at=now)
    return {"pending": len(pending), "sent": sent, "failed": failed}


def live_doc(store_ids=None, label: str = ""):
    """/nazorat in the analytics bot: the branches right now + the open alerts."""
    from apps.telegram_bot.infrastructure import rich as R

    d = live(store_ids)
    ov = d["overview"] or {}
    doc = R.RichDoc()
    ch = ov.get("revenue_change") or {}
    trend = f"{ch['pct']:+.1f}%" if ch.get("pct") is not None else "—"
    doc.add(R.h(2, f"🛡 Nazorat · {R.e(label or 'Butun kompaniya')}"),
            R.p(f"🕒 {d['generated_at']:%H:%M} holati · kecha shu vaqtga nisbatan"),
            R.table([], [[R.e("💰 Bugungi tushum"), R.b(som(ov.get("revenue")))], [R.e("📊 Kechaga nisbatan"), R.b(trend)],
                         [R.e("🧾 Xaridlar"), R.b(str(ov.get("purchases") or 0))],
                         [R.e("💹 Yalpi foyda"), R.b(som(ov["gross_profit"])) if ov.get("gross_profit") is not None else R.e("tannarx to'liq emas")],
                         [R.e("🏪 Ochiq kassalar"), R.b(f"{d['open_shifts']} / {d['kassa_count']}")],
                         [R.e("🚨 Ochiq signallar"), R.b(f"🔴 {d['critical']} · 🟠 {d['warning']}")]], align=["left", "right"]))
    rows = []
    for b in d["branches"]:
        state = f"🟢 {b['shift']['by']}" if b["shift"] else ("🔴 yopiq" if b["kassa"] else "—")
        delta = f"{b['change']['pct']:+.0f}%" if b["change"]["pct"] is not None else "—"
        rows.append([R.e(b["name"]), R.e(som(b["revenue"])), R.e(delta), R.e(state)])
    if rows:
        doc.add(R.h(3, "🏪 Filiallar"), R.table(["Filial", "Tushum", "Kecha", "Kassa"], rows, align=["left", "right", "right", "left"]))
    if d["alerts"]:
        doc.add(R.h(3, "🚨 Ochiq signallar"))
        for a in d["alerts"][:DIGEST_LIMIT]:
            doc.add(R.details(f"{'🔴' if a.severity == 'critical' else '🟠'} {R.e(a.title)}", "".join(alert_blocks(a, R)[1:])))
    else:
        doc.add(R.p("✅ Ochiq signal yo'q — hammasi joyida."))
    fb = [f"🛡 <b>Nazorat · {R.e(label or 'Butun kompaniya')}</b> ({d['generated_at']:%H:%M})",
          f"💰 Tushum: <b>{som(ov.get('revenue'))}</b> ({trend})", f"🏪 Ochiq kassalar: {d['open_shifts']}/{d['kassa_count']}",
          f"🚨 Signallar: 🔴 {d['critical']} · 🟠 {d['warning']}"]
    fb += [f"• {R.e(b['name'])}: {som(b['revenue'])}" + (" · 🟢" if b["shift"] else "") for b in d["branches"]]
    doc.fallback = "\n".join(fb)
    return doc


# ---------------------------------------------------------------- "📦 Transfer so'rash" (a transfer DRAFT warehouse → branch)


def request_transfer(store_id, actor: str, variant_id=None, allowed_store_ids=None) -> dict:
    """
    Creates a transfer draft from the main warehouse to a branch: one product (from a stock alert) or everything the
    branch is short of (planning_service.transfer_suggestions). Quantities = what the rule / sales speed needs minus
    what is already on the way, capped by the warehouse's free stock -- so pressing the button twice never doubles it.
    {"ok": True, "transfer": t, "lines", "units"} or {"ok": False, "reason": text}.
    """
    from apps.stores.infrastructure import planning_service
    from apps.stores.infrastructure.models import Store

    store = Store.objects.filter(id=store_id, kind="store").first()
    if store is None or (allowed_store_ids is not None and store.id not in set(allowed_store_ids)):
        return {"ok": False, "reason": "Bu filial sizga biriktirilmagan."}
    source = planning_service.default_source(exclude=store)
    if source is None:
        return {"ok": False, "reason": "Faol sklad topilmadi."}
    wanted = {}
    if variant_id is not None:
        line = next((ln for ln in planning_service.plan(store, source)["lines"] if str(ln.variant_id) == str(variant_id)), None)
        if line is not None:
            want = line.suggest if line.rule else max(0, planning_service.suggested_rule(line.sold)[1] - line.projected)
            if want <= 0 and line.days_cover is not None:  # forecast without a rule: a week of sales on top
                want = max(1, round(line.per_day * 7))
            send = min(want, line.source_available)
            if send > 0:
                wanted[str(line.variant_id)] = send
        if not wanted:
            on_way = planning_service.incoming_map(store, [variant_id]).get(variant_id) if line else 0
            return {"ok": False, "reason": (f"Bu mahsulot allaqachon yo'lda yoki tayyorlanmoqda ({on_way} dona)." if on_way
                                             else f"{source.name} da bu mahsulotdan bo'sh qoldiq yo'q.")}
    else:
        for row in planning_service.transfer_suggestions(store, source):
            wanted[row["variant_id"]] = row["suggest"]
        if not wanted:
            return {"ok": False, "reason": "To'ldirish kerak bo'lgan mahsulot yo'q (yoki hammasi allaqachon yo'lda)."}
    t = planning_service.create_transfer(store, source, actor, wanted)
    return {"ok": True, "transfer": t, "lines": len(wanted), "units": sum(wanted.values()), "source": source, "store": store}


def request_transfer_for_alert(alert_id, actor: str, allowed_store_ids=None) -> dict:
    from apps.platform.infrastructure.models import ControlAlert

    a = ControlAlert.objects.filter(id=alert_id, kind__in=("low_stock", "stock_forecast")).first()
    if a is None:
        return {"ok": False, "reason": "Signal topilmadi."}
    _kind, store_id, variant_id = a.key.split(":", 2)
    return request_transfer(uuid.UUID(store_id), actor, uuid.UUID(variant_id), allowed_store_ids)
