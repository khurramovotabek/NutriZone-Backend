"""To'lovlar tahlili → Excel: summary, per-provider table, daily series, funnel, failure reasons, callback health."""
from __future__ import annotations

from apps.finance.infrastructure.finance_excel import Book


def analytics_book(an: dict, cb: dict) -> bytes:
    book = Book()
    t = an["totals"]
    ws = book.sheet("Xulosa", "To'lovlar tahlili", f"Oxirgi {an['days']} kun")
    Book.header(ws, ["Ko'rsatkich", "Qiymat"], [40, 20])
    for label, value in (
        ("To'langan summa (so'm)", t["volume"]), ("To'lovlar soni", t["paid"]), ("Checkout urinishlari", t["attempts"]),
        ("Provayderda boshlangan", t["started"]), ("Konversiya, %", t["conversion"]), ("Provayderda muvaffaqiyat, %", t["success"]),
        ("O'rtacha chek (so'm)", t["avg"]), ("Oldingi davrga nisbatan summa, %", t["d_volume"]), ("To'lash vaqti (mediana)", t["ttp"]),
    ):
        Book.row(ws, [label, value])

    ws = book.sheet("Provayderlar", "Provayderlar bo'yicha", f"Oxirgi {an['days']} kun")
    hr = Book.header(ws, ["Provayder", "Urinishlar", "Boshlangan", "To'langan", "Konversiya %", "Muvaffaqiyat %", "Summa", "Ulush %", "O'rtacha chek",
                          "Qaytarilgan", "To'lash vaqti", "p90", "Asosiy xato sabablari"], [16, 12, 12, 12, 13, 14, 16, 10, 15, 15, 13, 11, 44])
    for p in an["providers"]:
        Book.row(ws, [p["name"], p["attempts"], p["started"], p["paid"], p["conversion"], p["success"], p["volume"], p["share"], p["avg"], p["refunded"],
                      p["ttp"], p["ttp_p90"], "; ".join(f"{r} ({n})" for r, n in p["fails"])], pct_cols=(5, 6, 8))
    Book.finish(ws, hr + 1)

    ws = book.sheet("Kunlik", "Kunlik to'lovlar (so'm)", f"Oxirgi {an['days']} kun")
    series = an["chart"]["series"]
    hr = Book.header(ws, ["Sana", *[s["name"] for s in series], "Jami"], [12] + [16] * (len(series) + 1))
    for i, label in enumerate(an["chart"]["labels"]):
        vals = [s["data"][i] for s in series]
        Book.row(ws, [label, *vals, sum(vals)])
    Book.finish(ws, hr + 1, ws.max_row)

    ws = book.sheet("Voronka", "To'lov voronkasi")
    Book.header(ws, ["Bosqich", "Soni", "Urinishlardan %"], [30, 12, 16])
    for f in an["funnel"]:
        Book.row(ws, [f["label"], f["n"], f["pct"]], pct_cols=(3,))
    Book.row(ws, [])
    Book.header(ws, ["Xato / bekor sababi", "Soni"])
    for reason, n in an["fails"]:
        Book.row(ws, [reason, n])
    Book.row(ws, [])
    Book.header(ws, ["Soat", "To'lovlar"])
    for h in an["hours"]:
        Book.row(ws, [f"{h['h']:02d}:00", h["n"]])

    ws = book.sheet("Callback", "Callback'lar sog'lig'i", f"Oxirgi {cb['days']} kun")
    hr = Book.header(ws, ["Provayder", "Metod", "So'rovlar", "Xatolar", "Xato %", "O'rtacha ms", "p95 ms"], [14, 30, 12, 10, 10, 13, 10])
    for r in cb["rows"]:
        Book.row(ws, [r["name"], r["method"], r["n"], r["errors"], r["err_rate"], r["avg"], r["p95"]], pct_cols=(5,), money_from=3)
    Book.row(ws, [])
    Book.header(ws, ["Provayder", "Kod", "Soni", "Ma'nosi", "Nima qilish kerak"])
    for e in cb["top"]:
        Book.row(ws, [e["name"], e["code"], e["n"], e["title"], e["hint"]], money_from=99)
    return book.bytes()
