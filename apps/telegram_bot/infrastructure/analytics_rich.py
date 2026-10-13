"""
@NutriZoneAnalyticsBot -- the report as a Telegram rich message: a KPI picture, the revenue chart, the branch ranking
and the payment donut as images, then tables (business health, branches, products, cashiers, payments, orders,
customers, stock), the alerts and the summary -- the long parts folded into <details>. Built from
business_analytics.build(), so the numbers are exactly the dashboard's.
"""
from __future__ import annotations

from decimal import Decimal

from apps.telegram_bot.infrastructure import charts
from apps.telegram_bot.infrastructure import rich as R

TITLES = {"today": "Bugungi puls", "yesterday": "Kunlik hisobot", "week": "Haftalik hisobot", "month": "Oylik hisobot",
          "7d": "So'nggi 7 kun", "30d": "So'nggi 30 kun", "this_month": "Shu oy", "custom": "Hisobot"}


def som(v) -> str:
    return f"{int(round(Decimal(str(v or 0)))):,}".replace(",", " ") + " so'm"


def num(v) -> str:
    return f"{int(round(Decimal(str(v or 0)))):,}".replace(",", " ")


def pct(v) -> str:
    if v is None:
        return "—"
    t = f"{float(v):.1f}".replace(".", ",")
    return (t[:-2] if t.endswith(",0") else t) + "%"


def trend(ch, unit: str = "pct") -> str:
    """"▲ 12%" / "▼ 3 ta" -- nothing when there is no honest baseline."""
    if not ch or ch.get("dir") in (None, "flat"):
        return "" if not ch or ch.get("dir") is None else "▬ 0%"
    arrow = "▲" if ch["dir"] == "up" else "▼"
    if unit == "pct":
        return f"{arrow} {pct(abs(ch['pct']))}" if ch.get("pct") is not None else ""
    return f"{arrow} {num(abs(ch['diff']))} {unit}"


def _trend_cell(ch, unit: str = "pct") -> str:
    t = trend(ch, unit)
    if not t:
        return R.i("—")
    return f"<b>{R.e(t)}</b>" if t.startswith("▲") else f"<mark>{R.e(t)}</mark>" if t.startswith("▼") else R.e(t)


def _top_visuals(doc: R.RichDoc, top: list[dict]) -> str:
    """Top products as a ranked bar chart, or -- when the chart can't be drawn -- a collage of their photos."""
    chart = charts.hbar("Top mahsulotlar", "Tushum bo'yicha", [(t["name"] if len(t["name"]) <= 34 else t["name"][:33] + "…", float(t["revenue"]), charts.PALETTE[k % len(charts.PALETTE)],
                                                                 f"{charts.compact(float(t['revenue']))} · {t['units']} dona") for k, t in enumerate(top[:6])]) if len(top) > 1 else None
    if doc.image("topchart", chart):
        return R.figure("topchart")
    from apps.telegram_bot.infrastructure import shop_rich

    try:
        return shop_rich.pictures(doc, [t.get("image") for t in top[:4] if t.get("image")], "top")
    except Exception:  # noqa: BLE001
        return ""


def build_doc(r: dict, *, scheduled: bool = False, dashboard_url: str | None = None) -> R.RichDoc:
    p = r["period"]
    ov, fin, st = r.get("overview"), r.get("finance"), r.get("stores") or []
    scope = ", ".join(r.get("scope_names") or []) or "Barcha filiallar"
    doc = R.RichDoc()

    # ---- KPI picture
    if ov:
        tiles = [("Tushum", f"{charts.compact(float(ov['revenue']))} so'm", trend(ov["revenue_change"]), charts.INDIGO),
                 ("Xaridlar", num(ov["purchases"]), trend(ov["purchases_change"], "ta"), charts.CYAN)]
        if ov["gross_profit"] is not None:
            tiles.append(("Yalpi foyda", charts.compact(float(ov["gross_profit"])), f"marja {pct(ov['margin'])}", charts.GREEN))
        else:
            tiles.append(("Sotilgan", f"{num(ov['units'])} dona", trend(ov["units_change"], "dona"), charts.GREEN))
        tiles.append(("O'rtacha chek", charts.compact(float(ov["average"])) if ov["average"] is not None else "—", trend(ov["average_change"]) if ov.get("average_change") else "", charts.AMBER))
        doc.image("kpi", charts.kpi_banner(f"{TITLES.get(p.key, 'Hisobot')} · {scope}", p.range_text(), tiles))
        doc.add(R.figure("kpi"))
    doc.add(R.h(1, f"📊 {R.e(TITLES.get(p.key, 'Hisobot'))}"),
            R.p(f"🏪 <b>{R.e(scope)}</b> · 📅 {R.e(p.range_text())} · {R.e(p.compare_label)}"))

    # ---- business health
    if ov:
        rows = [[R.e("💰 Savdo tushumi"), R.b(som(ov["revenue"])), _trend_cell(ov["revenue_change"])],
                [R.e("🧾 Xaridlar"), R.b(f"{num(ov['purchases'])} ta"), _trend_cell(ov["purchases_change"], "ta")],
                [R.e("📦 Sotilgan mahsulot"), R.b(f"{num(ov['units'])} dona"), _trend_cell(ov["units_change"], "dona")],
                [R.e("🧮 O'rtacha chek"), R.b(som(ov["average"])) if ov["average"] is not None else R.i("—"), _trend_cell(ov.get("average_change"))]]
        if ov["gross_profit"] is not None:
            rows.append([R.e("📈 Yalpi foyda"), R.b(som(ov["gross_profit"])), R.e(f"marja {pct(ov['margin'])}")])
        elif ov["cost_coverage"] is not None:
            rows.append([R.e("📈 Yalpi foyda"), R.i("hisoblanmadi"), R.e(f"tannarx {ov['cost_coverage']}% ma'lum")])
        rows.append([R.e("🏬 Do'konlar / 🌐 Onlayn"), R.e(f"{charts.compact(float(ov['pos_revenue']))} / {charts.compact(float(ov['online_revenue']))}"), ""])
        if ov["pipeline_orders"]:
            rows.append([R.e("🚚 Yo'ldagi buyurtmalar"), R.e(f"{ov['pipeline_orders']} ta · {som(ov['pipeline_value'])}"), R.i("hali tushum emas")])
        doc.add(R.h(2, "📈 Biznes holati"), R.table(["Ko'rsatkich", "Qiymat", "O'zgarish"], rows, align=["left", "right", "center"]))

    # ---- revenue chart
    s = r.get("series")
    if s and any(s.get("totals") or []):
        png = charts.bar_chart("Tushum dinamikasi", "Soatlar bo'yicha" if s["hourly"] else "Kunlar bo'yicha",
                               s["labels"], [("Do'konlar", charts.INDIGO, s["pos"]), ("Onlayn", charts.CYAN, s["online"])], s.get("previous"),
                               every=3 if s["hourly"] else 0)
        if doc.image("trend", png):
            best = s["totals"].index(max(s["totals"]))
            h = r.get("heatmap") or {}
            note = f"Eng yaxshi {'soat' if s['hourly'] else 'kun'}: {s['labels'][best]} · {som(s['totals'][best])}"
            if h.get("peak") and not s["hourly"]:
                note += f" · eng gavjum vaqt {h['peak']['day']} {h['peak']['hour']:02d}:00"
            doc.add(R.figure("trend", R.e(note)))

    # ---- branches
    if st:
        if len(st) > 1 and doc.image("stores", charts.hbar("Filiallar reytingi", "Tushum bo'yicha",
                                                           [(x["name"], float(x["revenue"]), charts.hex_rgb(x["color"]), f"{charts.compact(float(x['revenue']))} · {x['purchases']} ta") for x in st])):
            doc.add(R.figure("stores"))
        rows = [[str(x["rank"]), R.b(x["name"]), num(x["revenue"]), str(x["purchases"]), num(x["average"]), pct(x["share"]), _trend_cell(x["change"])] for x in st]
        doc.add(R.h(2, "🏪 Filiallar"), R.table(["#", "Filial", "Tushum", "Xarid", "O'rtacha", "Ulush", "O'zg."], rows,
                                                 align=["center", "left", "right", "center", "right", "center", "center"]))

    # ---- products
    pr = r.get("products")
    if pr and pr["top"]:
        rows = [[str(k), R.b(t["name"]) + (f" · {R.e(t['size'])}" if t["size"] else ""), str(t["units"]), num(t["revenue"])] for k, t in enumerate(pr["top"], 1)]
        doc.add(R.h(2, "🔥 Top mahsulotlar"), _top_visuals(doc, pr["top"]), R.table(["#", "Mahsulot", "Dona", "Tushum"], rows[:5], align=["center", "left", "center", "right"]))
        if len(rows) > 5:
            doc.add(R.details(f"Yana {len(rows) - 5} ta mahsulot", R.table(["#", "Mahsulot", "Dona", "Tushum"], rows[5:], align=["center", "left", "center", "right"])))
    mix = r.get("mix")
    if mix and (mix["categories"] or mix["brands"]):
        body = ""
        if mix["categories"]:
            body += R.table(["Kategoriya", "Tushum", "Ulush"], [[R.e(x["name"]), num(x["revenue"]), pct(x["share"])] for x in mix["categories"]], align=["left", "right", "center"])
        if mix["brands"]:
            body += R.table(["Brend", "Tushum", "Ulush"], [[R.e(x["name"]), num(x["revenue"]), pct(x["share"])] for x in mix["brands"]], align=["left", "right", "center"])
        doc.add(R.details("🧩 Kategoriya va brendlar ulushi", body))

    # ---- cashiers
    sellers = r.get("sellers") or []
    if sellers:
        rows = [[str(k), R.b(x["name"]), R.e(x["branch"]), str(x["count"]), num(x["average"]), num(x["revenue"])] for k, x in enumerate(sellers, 1)]
        doc.add(R.details(f"🧑‍💼 Kassirlar — {len(sellers)} ta", R.table(["#", "Kassir", "Filial", "Chek", "O'rtacha", "Tushum"], rows,
                                                                           align=["center", "left", "left", "center", "right", "right"]), open_=p.key in ("today", "yesterday")))

    # ---- money
    if fin:
        rows = [[R.e("Yalpi savdo"), num(fin["gross_sales"])]]
        if fin["discounts"]:
            rows.append([R.e("Chegirmalar"), f"−{num(fin['discounts'])}"])
        if fin["delivery"]:
            rows.append([R.e("Yetkazish puli"), f"+{num(fin['delivery'])}"])
        if fin["refunds"]:
            rows.append([R.e(f"Qaytarishlar ({fin['refunds_count']} ta)"), f"−{num(fin['refunds'])}"])
        rows.append([R.b("Sof tushum"), R.b(som(fin["net_revenue"]))])
        if ov and ov.get("cogs") is not None:
            rows += [[R.e("Tannarx (COGS)"), f"−{num(ov['cogs'])}"], [R.b("Yalpi foyda"), R.b(f"{som(ov['gross_profit'])} · {pct(ov['margin'])}")]]
        body = R.table([], rows, align=["left", "right"])
        pays = fin["payments"]["rows"]
        if pays:
            if doc.image("pay", charts.donut("To'lov usullari", "Sof tushum taqsimoti", [(x["label"], float(x["amount"])) for x in pays],
                                             charts.compact(float(fin["payments"]["total"])), "so'm")):
                body += R.figure("pay")
            body += R.table(["Usul", "Summa", "Soni", "Ulush"], [[R.e(x["label"]), num(x["amount"]), str(x["count"]), pct(x["share"])] for x in pays],
                            align=["left", "right", "center", "center"])
        body += R.p(" · ".join(f"{R.e(w['label'])}: <b>{charts.compact(float(w['revenue']))}</b>" for w in fin["windows"]) + f" · Jami qayd etilgan: <b>{charts.compact(float(fin['lifetime']))}</b>")
        doc.add(R.details("💵 Moliya va to'lovlar", body, open_=p.key in ("week", "month")))

    # ---- orders / customers / stock
    o = r.get("orders")
    if o:
        rows = [[R.e(x["label"]), str(x["count"])] for x in o["statuses"]]
        body = R.table(["Holat", "Soni"], rows, align=["left", "center"]) if rows else R.p(R.i("Bu davrda onlayn buyurtma yo'q"))
        if o["backlog_total"]:
            body += R.p(f"⏳ Hozir jarayonda: <b>{o['backlog_total']} ta</b> — " + ", ".join(f"{R.e(b['label'].lower())} {b['count']}" for b in o["backlog"]))
        doc.add(R.details(f"🧾 Onlayn buyurtmalar — {o['placed']} ta" + (f" · bekor {o['cancelled']}" if o["cancelled"] else ""), body))
    c = r.get("customers")
    if c:
        rows = []
        if c["new"] is not None:
            rows.append([R.e("Yangi ro'yxatdan o'tganlar"), str(c["new"])])
        rows += [[R.e("Xaridorlar (tanilgan)"), str(c["buyers"])], [R.e("Takroriy / birinchi marta"), f"{c['repeat']} / {c['first_time']}"],
                 [R.e("Takroriy ulushi"), pct(c["repeat_share"]) if c["repeat_share"] is not None else "—"],
                 [R.e("Xarid chastotasi"), str(c["frequency"]).replace(".", ",") if c["frequency"] else "—"], [R.e("Mijozsiz kassa cheklari"), str(c["anonymous"])]]
        doc.add(R.details("👥 Mijozlar", R.table([], rows, align=["left", "right"])))
    inv = r.get("inventory")
    if inv:
        rows = [[R.e("Kam qolgan"), f"{inv['low_stock_total']} ta" + (f" (tugagan {inv['out_of_stock']})" if inv["out_of_stock"] else "")],
                [R.e(f"Muddati yaqin ({inv['expiry_days']} kun)"), f"{inv['expiring_skus']} ta · {inv['expiring_units']} dona"],
                [R.e("Muddati o'tgan (javonda)"), f"{inv['expired_skus']} ta · {inv['expired_units']} dona"],
                [R.e(f"{inv['slow_days']} kun sotilmagan"), f"{inv['slow_total']} ta" if inv["slow_history_ok"] else R.i("tarix hali yetarli emas")]]
        body = R.table([], rows, align=["left", "right"])
        if inv["low_stock"]:
            body += R.table(["Mahsulot · joy", "Bor", "Min"], [[R.e(x["code"]), str(x["available_quantity"]), str(x["low_stock_at"])] for x in inv["low_stock"][:10]], align=["left", "center", "center"])
        if inv["expiring"]:
            body += R.table(["Muddati yaqin", "Joy", "Dona", "Qoldi"], [[R.e(x["name"]), R.e(x["store"]), str(x["quantity"]), f"{x['days_left']} kun"] for x in inv["expiring"]],
                            align=["left", "left", "center", "center"])
        doc.add(R.details("📦 Ombor nazorati", body))

    # ---- alerts & summary
    alerts = r.get("alerts") or []
    doc.add(R.h(2, "⚠️ Diqqat talab qiladi" if alerts else "✅ Muhim ogohlantirish yo'q"))
    if alerts:
        doc.add(R.ul([f"{a['icon']} {R.e(a['text'])}" for a in alerts]))
    if r.get("summary"):
        doc.add(R.h(2, "🧠 Xulosa"), R.ul([R.e(x) for x in r["summary"]]))
    if dashboard_url:
        doc.add(R.buttons(R.button("🖥 Dashboard'da ochish", url=dashboard_url, style="primary")))
    doc.add(R.footer(f"NutriZoneAnalyticsBot · {'Avtomatik' if scheduled else 'So‘rov bo‘yicha'} hisobot · {R.e(r['generated_at'].strftime('%d.%m.%Y %H:%M'))}"))

    from apps.telegram_bot.infrastructure import analytics_report

    doc.fallback = analytics_report.render(r, on_demand=not scheduled)[0]  # one complete classic message (never cut mid-tag)
    return doc
