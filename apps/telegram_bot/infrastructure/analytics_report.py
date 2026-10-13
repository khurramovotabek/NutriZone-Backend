"""
NutriZoneAnalyticsBot -- business_analytics.build() → Telegram HTML messages.

Only Telegram's own HTML subset is used (<b> <i> <code> <a>), every dynamic text is escaped, and a long report is
split between sections (never inside one) so each message stays under Telegram's 4096-character limit.
"""
from __future__ import annotations

from decimal import Decimal
from html import escape

LIMIT = 3900  # below Telegram's 4096 (entities count after parsing; leave headroom)
RULE = "━━━━━━━━━━━━━━━━━━"

TITLES = {
    "today": "BUGUNGI PULS", "yesterday": "KUNLIK HISOBOT", "week": "HAFTALIK HISOBOT", "month": "OYLIK HISOBOT",
    "7d": "SO'NGGI 7 KUN", "30d": "SO'NGGI 30 KUN", "this_month": "SHU OY", "custom": "HISOBOT",
}
BADGES = {"today": "DAILY", "yesterday": "DAILY", "week": "WEEKLY", "month": "MONTHLY"}

# Store colours → the closest coloured circle, so each branch keeps the same mark it has on the dashboard.
CIRCLES = (("🔴", (239, 68, 68)), ("🟠", (249, 115, 22)), ("🟡", (234, 179, 8)), ("🟢", (34, 197, 94)), ("🔵", (59, 130, 246)),
           ("🟣", (139, 92, 246)), ("🟤", (146, 64, 14)), ("⚫", (30, 41, 59)), ("⚪", (203, 213, 225)))
MEDALS = ("🥇", "🥈", "🥉")


# ---------------------------------------------------------------- formatting helpers


def num(value) -> str:
    return f"{int(round(Decimal(str(value or 0)))):,}".replace(",", " ")


def money(value) -> str:
    return f"{num(value)} so'm"


def pct(value, signed: bool = False) -> str:
    text = (f"{value:+.1f}" if signed else f"{abs(value):.1f}").replace(".", ",")
    return (text[:-2] if text.endswith(",0") else text) + "%"


def arrow(ch: dict | None, label: str = "", unit: str = "pct") -> str:
    """▲ 12,4% / ▼ 3 ta / — ; empty when there is nothing honest to compare against."""
    if not ch or ch.get("dir") is None:
        return ""
    if ch["dir"] == "flat":
        return f"▬ o'zgarishsiz{' ' + label if label else ''}"
    sign = "▲" if ch["dir"] == "up" else "▼"
    if unit == "pct":
        if ch.get("pct") is None:
            return ""
        body = pct(ch["pct"])
    else:
        body = f"{num(abs(ch['diff']))} {unit}"
    return f"{sign} {body}{' ' + label if label else ''}"


def circle(hex_color: str | None, kind: str = "store") -> str:
    if kind == "online":
        return "🌐"
    if kind == "central":
        return "💻"
    try:
        h = (hex_color or "").lstrip("#")
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "⚪"
    return min(CIRCLES, key=lambda c: sum((a - b) ** 2 for a, b in zip(c[1], rgb, strict=False)))[0]


def e(text) -> str:
    return escape(str(text or ""), quote=False)


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values) -> str:
    peak = max(values or [0])
    if peak <= 0:
        return ""
    return "".join(SPARK[min(len(SPARK) - 1, int(v / peak * (len(SPARK) - 1) + 0.5))] if v > 0 else "·" for v in values)


def expandable(lines: list[str]) -> str:
    """A collapsed quote Telegram shows with a "show more" toggle -- keeps long lists out of the way."""
    return "<blockquote expandable>" + "\n".join(lines) + "</blockquote>"


# ---------------------------------------------------------------- sections


def trend(r: dict) -> str | None:
    """📈 the period at a glance: a bar per day (per hour for one day), the best slot and the busiest time."""
    s, h = r.get("series"), r.get("heatmap")
    if not s or not any(s.get("totals") or []):
        return None
    totals = s["totals"]
    out = ["〽️ <b>DINAMIKA</b>"]
    if s["hourly"]:
        first = next(i for i, v in enumerate(totals) if v > 0)
        last = max(i for i, v in enumerate(totals) if v > 0)
        out.append(f"<code>{sparkline(totals[first:last + 1])}</code>  {s['labels'][first]}–{s['labels'][last][:2]}:59")
        best = totals.index(max(totals))
        out.append(f"⏰ Eng faol soat: <b>{s['labels'][best]}</b> · {money(totals[best])}")
    else:
        out.append(f"<code>{sparkline(totals)}</code>  {s['labels'][0]} → {s['labels'][-1]}")
        best = totals.index(max(totals))
        active = sum(1 for v in totals if v > 0)
        out.append(f"🏆 Eng yaxshi kun: <b>{s['labels'][best]}</b> · {money(totals[best])}")
        out.append(f"📅 Savdo bo'lgan kunlar: {active} / {len(totals)} · kunlik o'rtacha {money(sum(totals) / len(totals))}")
        if h and h.get("peak"):
            out.append(f"⏰ Eng gavjum vaqt: <b>{h['peak']['day']} {h['peak']['hour']:02d}:00</b> · eng kuchli kun: {h['best_day']}")
    return "\n".join(out)


def sellers(r: dict) -> str | None:
    rows = r.get("sellers") or []
    if not rows:
        return None
    items = [f"{MEDALS[i] if i < 3 else f'{i + 1}.'} <b>{e(x['name'])}</b> · {e(x['branch'])}\n      {money(x['revenue'])} · {num(x['count'])} ta chek · o'rtacha {money(x['average'])}"
             for i, x in enumerate(rows)]
    out = ["🧑‍💼 <b>KASSIRLAR</b>", *items[:3]]
    if len(items) > 3:
        out.append(expandable(items[3:]))
    return "\n".join(out)


def mix(r: dict) -> str | None:
    m = r.get("mix")
    if not m or not (m["categories"] or m["brands"]):
        return None
    out = ["🧩 <b>KATEGORIYA VA BRENDLAR</b>"]
    if m["categories"]:
        out.append("🗂 " + " · ".join(f"{e(x['name'])} <b>{pct(x['share'])}</b>" for x in m["categories"][:4]))
    if m["brands"]:
        out.append("🏷 " + " · ".join(f"{e(x['name'])} <b>{pct(x['share'])}</b>" for x in m["brands"][:4]))
    return "\n".join(out)


def header(r: dict, on_demand: bool = False) -> str:
    p = r["period"]
    title = TITLES.get(p.key, "HISOBOT")
    badge = BADGES.get(p.key)
    lines = [f"📊 <b>NUTRIZONE — {title}</b>", f"📅 {e(p.range_text())}" + (f"  ·  <code>{badge}</code>" if badge else "")]
    if on_demand:
        lines.append("<i>So'rov bo'yicha hisobot</i>")
    return "\n".join(lines) + "\n" + RULE


def overview(r: dict) -> str | None:
    ov = r.get("overview")
    if not ov:
        return None
    label = r["period"].compare_label
    out = ["📈 <b>BIZNES HOLATI</b>"]
    out.append(f"💰 Savdo tushumi: <b>{money(ov['revenue'])}</b>")
    trend = arrow(ov["revenue_change"], label)
    if trend:
        out.append(f"      {trend}")
    elif ov["prev_revenue"] == 0 and ov["revenue"] > 0:
        out.append("      <i>oldingi davrda savdo bo'lmagan</i>")
    purchases = f"🧾 Xaridlar: <b>{num(ov['purchases'])} ta</b>"
    t = arrow(ov["purchases_change"], unit="ta")
    out.append(purchases + (f"  {t}" if t else ""))
    units = f"📦 Sotilgan mahsulot: <b>{num(ov['units'])} dona</b>"
    t = arrow(ov["units_change"], unit="dona")
    out.append(units + (f"  {t}" if t else ""))
    if ov["average"] is not None:
        out.append(f"🧮 O'rtacha chek: <b>{money(ov['average'])}</b>")
    if ov["gross_profit"] is not None:
        line = f"📊 Yalpi foyda: <b>{money(ov['gross_profit'])}</b> · marja {pct(ov['margin'])}" if ov["margin"] is not None else f"📊 Yalpi foyda: <b>{money(ov['gross_profit'])}</b>"
        out.append(line)
    elif ov["cost_coverage"] is not None:
        out.append(f"📊 Yalpi foyda: <i>hisoblanmadi — tannarx savdoning {ov['cost_coverage']}% qismida ma'lum</i>")
    if ov["revenue"] and (ov["pos_revenue"] or ov["online_revenue"]):
        out.append(f"🏬 Do'konlar: {money(ov['pos_revenue'])}  ·  🌐 Onlayn: {money(ov['online_revenue'])}")
    if ov["pipeline_orders"]:
        out.append(f"🚚 Yo'ldagi onlayn buyurtmalar: {num(ov['pipeline_orders'])} ta · {money(ov['pipeline_value'])} <i>(hali tushum emas)</i>")
    return "\n".join(out)


def finance(r: dict) -> str | None:
    f, ov = r.get("finance"), r.get("overview")
    if not f:
        return None
    out = ["💵 <b>MOLIYAVIY TAHLIL</b>"]
    out.append(f"• Yalpi savdo: {money(f['gross_sales'])}")
    if f["discounts"]:
        out.append(f"• Chegirmalar: −{money(f['discounts'])}")
    if f["delivery"]:
        out.append(f"• Yetkazish puli: +{money(f['delivery'])}")
    if f["refunds"]:
        out.append(f"• Qaytarishlar: −{money(f['refunds'])} ({num(f['refunds_count'])} ta)")
    out.append(f"• <b>Sof tushum: {money(f['net_revenue'])}</b>")
    if ov and ov.get("cogs") is not None:
        out.append(f"• Tannarx (COGS): {money(ov['cogs'])}")
        out.append(f"• <b>Yalpi foyda: {money(ov['gross_profit'])}</b>" + (f" · {pct(ov['margin'])}" if ov["margin"] is not None else ""))
    if f["lost_value"]:
        out.append(f"• Bekor/qaytgan onlayn buyurtmalar: {money(f['lost_value'])} <i>(tushumga kirmaydi)</i>")
    out.append("")
    out.append("🗓 " + "  ·  ".join(f"{e(w['label'])}: <b>{money(w['revenue'])}</b>" for w in f["windows"]))
    out.append(f"🏦 Jami qayd etilgan tushum: <b>{money(f['lifetime'])}</b>")
    out.append("<i>Operatsion xarajatlar tizimda yuritilmaydi — sof foyda ko'rsatilmaydi.</i>")
    return "\n".join(out)


def payments(r: dict) -> str | None:
    f = r.get("finance")
    if not f or not f["payments"]["rows"]:
        return None
    out = ["💳 <b>TO'LOVLAR</b>"]
    for row in f["payments"]["rows"]:
        out.append(f"• {e(row['label'])}: <b>{money(row['amount'])}</b> · {num(row['count'])} ta · {pct(row['share'])}")
    return "\n".join(out)


def stores(r: dict, limit: int = 8) -> str | None:
    rows = r.get("stores")
    if not rows:
        return None
    out = ["🏪 <b>FILIALLAR REYTINGI</b>"]
    items = []
    for s in rows[:limit]:
        medal = MEDALS[s["rank"] - 1] if s["rank"] <= 3 and s["revenue"] > 0 else f"{s['rank']}."
        line = f"{medal} {circle(s['color'], s['kind'])} <b>{e(s['name'])}</b>\n"
        if s["revenue"] > 0:
            t = arrow(s["change"])
            line += f"      {money(s['revenue'])} · {num(s['purchases'])} ta xarid · {pct(s['share'])}" + (f"  {t}" if t else "")
        else:
            line += "      <i>savdo yo'q</i>"
        items.append(line)
    out += items[:3]
    if len(items) > 3:
        out.append(expandable(items[3:]))
    if len(rows) > limit:
        out.append(f"<i>… yana {len(rows) - limit} ta</i>")
    return "\n".join(out)


def products(r: dict, limit: int = 5) -> str | None:
    pr = r.get("products")
    if pr is None:
        return None
    out = ["🔥 <b>TOP MAHSULOTLAR</b>"]
    if not pr["top"]:
        out.append("<i>Bu davrda mahsulot sotilmagan</i>")
    rows = []
    for i, t in enumerate(pr["top"][:limit], 1):
        size = f" · {e(t['size'])}" if t["size"] else ""
        rows.append(f"{MEDALS[i - 1] if i <= 3 else f'{i}.'} <b>{e(t['name'])}</b>{size}\n      {num(t['units'])} dona · {money(t['revenue'])}")
    out += rows[:3]
    if len(rows) > 3:
        out.append(expandable(rows[3:]))
    return "\n".join(out)


def inventory(r: dict, detailed: bool = False) -> str | None:
    inv = r.get("inventory")
    if not inv:
        return None
    out = ["📦 <b>OMBOR NAZORATI</b>"]
    low = inv["low_stock_total"]
    out.append(f"• Kam qolgan mahsulotlar: <b>{num(low)} ta</b>" + (f" (tugagan: {num(inv['out_of_stock'])})" if inv["out_of_stock"] else ""))
    out.append(f"• Muddati yaqin ({inv['expiry_days']} kun): <b>{num(inv['expiring_skus'])} ta</b>" + (f" · {num(inv['expiring_units'])} dona" if inv["expiring_units"] else ""))
    if inv["expired_skus"]:
        out.append(f"• Muddati o'tgan (javonda): <b>{num(inv['expired_skus'])} ta</b> · {num(inv['expired_units'])} dona")
    if inv["slow_history_ok"]:
        out.append(f"• {inv['slow_days']} kun sotilmagan: <b>{num(inv['slow_total'])} ta</b>")
    else:
        out.append(f"• Sekin sotilayotganlar: <i>{inv['slow_days']} kunlik tarix hali yo'q</i>")
    if detailed:
        if inv["low_stock"]:
            out.append("")
            out.append("<b>Kam qolganlar:</b>")
            for i in inv["low_stock"][:8]:
                out.append(f"  ▫️ {e(i['code'])} — {num(i['available_quantity'])} / min {num(i['low_stock_at'])}")
        if inv["expiring"]:
            out.append("")
            out.append("<b>Muddati yaqinlar:</b>")
            for x in inv["expiring"][:8]:
                out.append(f"  ▫️ {e(x['name'])} · {e(x['store'])} — {num(x['quantity'])} dona, {x['days_left']} kun ({x['expiry'].strftime('%d.%m.%Y')})")
        if inv["slow"]:
            out.append("")
            out.append(f"<b>{inv['slow_days']} kun sotilmaganlar:</b>")
            for x in inv["slow"][:8]:
                out.append(f"  ▫️ {e(x['name'])} — {num(x['on_hand'])} dona · {money(x['value'])}")
    return "\n".join(out)


def orders(r: dict) -> str | None:
    o = r.get("orders")
    if not o:
        return None
    out = ["🧾 <b>ONLAYN BUYURTMALAR</b>"]
    t = arrow(o["change"], unit="ta")
    out.append(f"• Yangi: <b>{num(o['placed'])} ta</b>" + (f"  {t}" if t else ""))
    out.append(f"• Yetkazilgan: <b>{num(o['delivered'])} ta</b>")
    out.append(f"• Bekor qilingan: <b>{num(o['cancelled'])} ta</b>" + (f" ({pct(o['cancel_rate'])})" if o["placed"] else "") + (" ⚠️" if o["cancel_spike"] else ""))
    if o["returned"]:
        out.append(f"• Qaytarilgan: <b>{num(o['returned'])} ta</b>")
    if o["backlog_total"]:
        out.append(f"• Hozir jarayonda: <b>{num(o['backlog_total'])} ta</b> — " + ", ".join(f"{e(b['label']).lower()} {num(b['count'])}" for b in o["backlog"]))
    return "\n".join(out)


def customers(r: dict) -> str | None:
    c = r.get("customers")
    if not c:
        return None
    out = ["👥 <b>MIJOZLAR</b>"]
    t = arrow(c["new_change"], unit="ta")
    out.append(f"• Yangi ro'yxatdan o'tganlar: <b>{num(c['new'])}</b>" + (f"  {t}" if t else ""))
    if c["buyers"]:
        out.append(f"• Xaridorlar (tanilgan): <b>{num(c['buyers'])}</b> — takroriy {num(c['repeat'])} ({c['repeat_share']}%), birinchi marta {num(c['first_time'])}")
        out.append(f"• Xarid chastotasi: <b>{str(c['frequency']).replace('.', ',')}</b> ta / mijoz")
    else:
        out.append("• Tanilgan xaridor yo'q")
    if c["anonymous"]:
        out.append(f"• Mijozsiz kassa cheklari: {num(c['anonymous'])} ta <i>(hisobga kirmaydi)</i>")
    return "\n".join(out)


def alerts(r: dict) -> str | None:
    items = r.get("alerts") or []
    if not items:
        return "✅ <b>DIQQAT TALAB QILADI</b>\n• Muhim ogohlantirish yo'q"
    return "⚠️ <b>DIQQAT TALAB QILADI</b>\n" + "\n".join(f"{a['icon']} {e(a['text'])}" for a in items)


def summary(r: dict) -> str | None:
    lines = r.get("summary") or []
    if not lines:
        return None
    return "🧠 <b>XULOSA</b>\n" + "\n".join(e(x) for x in lines)


def footer(on_demand: bool = False) -> str:
    return f"<i>NutriZoneAnalyticsBot · {'So‘rov bo‘yicha' if on_demand else 'Avtomatik'} hisobot</i>"


def chats(items: list[dict]) -> str:
    if not items:
        return "💬 <b>JAVOBSIZ CHATLAR</b>\n✅ Hamma chatlarga javob berilgan"
    out = [f"💬 <b>JAVOBSIZ CHATLAR — {len(items)} ta</b>"]
    for it in items[:15]:
        out.append(f"• <b>{e(it['who'])}</b> · {e(it['ago'])} oldin\n   «{e(it['preview'])}»")
    if len(items) > 15:
        out.append(f"<i>… yana {len(items) - 15} ta</i>")
    return "\n".join(out)


# ---------------------------------------------------------------- assembling


LAYOUTS = {
    # the evening pulse: the essentials only
    "today": (overview, trend, stores, products, inventory, orders, payments, alerts, summary),
    "yesterday": (overview, trend, stores, products, sellers, inventory, orders, payments, alerts, summary),
    "full": (overview, trend, finance, payments, stores, sellers, products, mix, orders, customers, inventory, alerts, summary),
    "stores": (stores, sellers),
    "products": (products, lambda r: inventory(r, detailed=True)),
    "inventory": (lambda r: inventory(r, detailed=True), alerts),
    "finance": (overview, finance, payments),
}


def split(blocks: list[str], limit: int = LIMIT) -> list[str]:
    """Joins blocks into messages under `limit`, breaking only between blocks (or, for one oversized block, between lines)."""
    messages, current = [], ""
    for block in blocks:
        parts = [block]
        if len(block) > limit:
            parts, chunk = [], ""
            for line in block.split("\n"):
                if chunk and len(chunk) + len(line) + 1 > limit:
                    parts.append(chunk)
                    chunk = ""
                chunk = f"{chunk}\n{line}" if chunk else line[:limit]
            if chunk:
                parts.append(chunk)
        for part in parts:
            if current and len(current) + len(part) + 2 > limit:
                messages.append(current)
                current = ""
            current = f"{current}\n\n{part}" if current else part
    if current:
        messages.append(current)
    return messages


def render(r: dict, layout: str | None = None, on_demand: bool = False) -> list[str]:
    key = layout or ("full" if r["period"].key in ("week", "month", "7d", "30d", "this_month", "custom") else r["period"].key)
    sections = LAYOUTS.get(key, LAYOUTS["full"])
    blocks = [header(r, on_demand)]
    for fn in sections:
        text = fn(r)
        if text:
            blocks.append(text)
    blocks.append(footer(on_demand))
    return split(blocks)
