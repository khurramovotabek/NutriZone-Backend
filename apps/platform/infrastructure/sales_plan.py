"""
Sotuv rejasi -- monthly revenue targets per branch (and for the company) and how the month is going against them,
with the same revenue definition as business_analytics (store tills net of returns + delivered/completed online orders
assigned to the branch; the company figure counts every channel).

For the running month: done so far, expected by now (target x elapsed share of the month), forecast at the current
pace, what is still needed per remaining day, and today against the daily target. Sellers (cashiers) show their
share of the branch's till revenue. Targets are set on the Dashboard page; nothing here pays bonuses.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal(0)


def month_start(d: date | None = None) -> date:
    d = d or timezone.localdate()
    return d.replace(day=1)


def parse_month(value: str | None) -> date:
    try:
        y, m = (int(x) for x in str(value or "").split("-")[:2])
        return date(y, m, 1)
    except (TypeError, ValueError):
        return month_start()


def _at(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=TZ)


def _revenue(start, end, store_ids=None) -> tuple[Decimal, list]:
    from apps.platform.infrastructure import business_analytics as ba

    base = ba._base(start, end, store_ids)
    return base["revenue"], ba._sellers(base)


def targets(month: date) -> dict:
    """{store_id or None: SalesTarget}"""
    from apps.platform.infrastructure.models import SalesTarget

    return {t.store_id: t for t in SalesTarget.objects.filter(month=month)}


def _row(name: str, color: str, store_id, target, month: date, now: datetime) -> dict:
    days = calendar.monthrange(month.year, month.month)[1]
    start = _at(month)
    end = _at(month + timedelta(days=days))
    running = start <= now < end
    until = now if running else end
    ids = [store_id] if store_id else None
    done, sellers = _revenue(start, until, ids)
    t = target.revenue_target if target else None
    elapsed = ((now - start).total_seconds() / 86400) if running else days
    share = min(1.0, elapsed / days) if days else 1.0
    row = {
        "store_id": str(store_id) if store_id else "", "name": name, "color": color, "target": t, "done": done,
        "pct": round(float(done / t * 100), 1) if t else None, "expected": (t * Decimal(str(share))).quantize(Decimal("1")) if t else None,
        "forecast": (done / Decimal(str(max(elapsed, 0.5))) * days).quantize(Decimal("1")) if running and done else done,
        "sellers": sellers[:6], "note": target.note if target else "", "running": running,
    }
    row["forecast_pct"] = round(float(row["forecast"] / t * 100), 1) if t else None
    row["ahead"] = (done - row["expected"]) if t else None
    if running and t:
        left_days = max(1, days - now.astimezone(TZ).day + 1)
        row["needed_per_day"] = max(ZERO, (t - done) / left_days).quantize(Decimal("1"))
        today_start = _at(now.astimezone(TZ).date())
        today, _s = _revenue(today_start, now, ids)
        row["today"] = today
        row["today_target"] = (t / days).quantize(Decimal("1"))
        row["today_pct"] = round(float(today / row["today_target"] * 100)) if row["today_target"] else None
    row["state"] = "none" if not t else "ok" if (row["forecast_pct"] or 0) >= 100 else "warn" if (row["forecast_pct"] or 0) >= 85 else "bad"
    return row


def progress(month: date | None = None, store_ids=None, now=None) -> dict:
    """The company row (unless narrowed to branches) + one row per active branch."""
    from apps.stores.infrastructure.models import Store

    month = month or month_start()
    now = now or timezone.now()
    tg = targets(month)
    branches = Store.objects.filter(kind="store", status="active").order_by("name")
    if store_ids is not None:
        branches = branches.filter(id__in=list(store_ids))
    rows = [_row(s.name, s.color or "#64748b", s.id, tg.get(s.id), month, now) for s in branches]
    company = _row("Butun kompaniya", "#4f46e5", None, tg.get(None), month, now) if store_ids is None else None
    days = calendar.monthrange(month.year, month.month)[1]
    return {"month": month, "days": days, "company": company, "branches": rows, "label": f"{month:%m.%Y}"}


def save_targets(month: date, values: dict, actor: str) -> int:
    """{store_id or "company": "12 000 000" | ""} -- empty removes the month's target."""
    from apps.platform.infrastructure.models import SalesTarget

    saved = 0
    for key, raw in values.items():
        store_id = None if key == "company" else key
        clean = str(raw or "").replace(" ", "").replace(" ", "").replace(",", "")
        if not clean:
            SalesTarget.objects.filter(month=month, store_id=store_id).delete()
            continue
        amount = Decimal(clean)
        if amount < 0 or amount > Decimal("1e14"):
            raise ValueError("Reja summasi noto'g'ri.")
        SalesTarget.objects.update_or_create(month=month, store_id=store_id, defaults={"revenue_target": amount, "updated_by": actor[:150]})
        saved += 1
    return saved


# ---------------------------------------------------------------- Telegram (NutriZoneAnalyticsBot /reja)


def telegram_doc(store_ids=None, label: str = ""):
    """The month against plan: progress picture + table, and the daily need, for a company or branch view."""
    from apps.telegram_bot.infrastructure import charts
    from apps.telegram_bot.infrastructure import rich as R

    d = progress(store_ids=store_ids)
    rows = ([d["company"]] if d["company"] else []) + d["branches"]
    doc = R.RichDoc()
    planned = [r for r in rows if r["target"]]
    picture = [(r["name"], float(min(r["pct"], 150)), charts.GREEN if r["state"] == "ok" else charts.AMBER if r["state"] == "warn" else charts.hex_rgb("#ef4444"),
                f"{r['pct']:.0f}% · {charts.compact(float(r['done']))}") for r in planned]
    if picture and doc.image("plan", charts.hbar("Sotuv rejasi", f"{d['label']} · bajarilish foizi", sorted(picture, key=lambda x: -x[1]))):
        doc.add(R.figure("plan"))
    doc.add(R.h(2, f"🎯 Sotuv rejasi · {R.e(label or 'Butun kompaniya')}"), R.p(f"📅 {d['label']} · prognoz — hozirgi sur'atda oy oxiriga"))
    table = []
    for r in rows:
        som = lambda v: charts.compact(float(v)) if v is not None else "—"  # noqa: E731
        state = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}.get(r["state"], "⚪")
        table.append([R.e(f"{state} {r['name']}"), R.e(som(r["done"])), R.e(som(r["target"])), R.b(f"{r['pct']:.0f}%") if r["pct"] is not None else R.i("reja yo'q"),
                      R.e(som(r["forecast"]) + (f" ({r['forecast_pct']:.0f}%)" if r["forecast_pct"] else ""))])
    doc.add(R.table(["Filial", "Bajarildi", "Reja", "%", "Prognoz"], table, align=["left", "right", "right", "center", "right"]))
    lead = d["company"] or (rows[0] if rows else None)
    if lead and lead.get("needed_per_day") is not None:
        doc.add(R.p(f"📌 Rejaga yetish uchun kuniga <b>{charts.compact(float(lead['needed_per_day']))} so'm</b> kerak · bugun {charts.compact(float(lead['today']))} / {charts.compact(float(lead['today_target']))} ({lead['today_pct'] or 0}%)"))
    if not planned:
        doc.add(R.p("ℹ️ Bu oy uchun reja kiritilmagan — Dashboard → Sotuv rejasi."))
    doc.fallback = f"🎯 <b>Sotuv rejasi · {R.e(label or 'Butun kompaniya')}</b> ({d['label']})\n" + "\n".join(
        f"• {R.e(r['name'])}: {charts.compact(float(r['done']))}" + (f" / {charts.compact(float(r['target']))} ({r['pct']:.0f}%)" if r["target"] else "") for r in rows)
    return doc
