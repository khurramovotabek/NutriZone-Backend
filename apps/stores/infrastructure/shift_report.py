"""
Z-report on Telegram: when a branch closes its shift, the owner gets the summary in their inbox + Telegram
(notify kind "shift_closed") and the full report -- totals, payment split, cash count, every cashier's sales --
is posted to the Orders channel (TELEGRAM_ORDERS_CHAT_ID). Best effort, after the closing transaction commits.
"""
from __future__ import annotations

import html
import logging
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count

logger = logging.getLogger("nutrizone.app")
TZ = ZoneInfo("Asia/Tashkent")


def _som(v) -> str:
    return f"{int(round(Decimal(v or 0))):,}".replace(",", " ")


def by_cashier(session) -> list[dict]:
    """Every cashier's completed sales in this shift: count and revenue (what customers paid, coins included)."""
    from apps.pos.infrastructure import sales_reports as rep
    from apps.pos.infrastructure.models import SaleModel

    sales = SaleModel.objects.filter(cash_session_id=session.id, status__in=("completed", "refunded"))
    rows = rep.rows(sales)
    out: dict = {}
    for r in rows:
        c = out.setdefault(r["cashier_id"], {"sales": 0, "revenue": Decimal(0)})
        c["sales"] += r["status"] == "completed"
        c["revenue"] += r["revenue"]
    names = rep.people_names(out)
    return sorted(({"name": names.get(cid) or "—", **v} for cid, v in out.items()), key=lambda x: -x["revenue"])


def report_text(session) -> str:
    store = session.store
    opened = session.opened_at.astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    closed = session.closed_at.astimezone(TZ).strftime("%H:%M") if session.closed_at else "—"
    revenue = (session.cash_sales or 0) + (session.uzcard_sales or 0) + (session.humo_sales or 0) + (session.coins_redeemed or 0)
    diff = session.cash_difference or Decimal(0)
    from apps.stores.infrastructure.pos_cashiers import kassa_name
    from apps.stores.infrastructure.pos_service import session_payload

    info = session_payload(session)
    lines = [
        f"\U0001F9FE <b>Z-hisobot · {html.escape(kassa_name(store))}</b> · smena №{info['number']}",
        f"\U0001F552 {opened} → {closed}",
        f"\U0001F464 Ochdi: {html.escape(info['opened_by'] or '—')}" + (f" · yopdi: {html.escape(info['closed_by'])}" if info.get("closed_by") else ""),
        "",
        f"Savdolar: <b>{session.sales_count}</b> · {session.items_sold} dona",
        f"Tushum: <b>{_som(revenue)} so'm</b>",
        f"\U0001F4B5 Naqd: {_som(session.cash_sales)} · \U0001F4B3 Uzcard: {_som(session.uzcard_sales)} · Humo: {_som(session.humo_sales)}",
    ]
    if session.coins_redeemed:
        lines.append(f"\U0001FA99 Coin: {_som(session.coins_redeemed)}")
    if session.discounts_total:
        lines.append(f"Chegirmalar: {_som(session.discounts_total)}")
    if session.refunds_count:
        lines.append(f"↩️ Qaytarishlar: {session.refunds_count} ta · {_som(session.refunds_total)}")
    lines += ["", f"Kassada kutilgan: {_som(session.expected_cash)} · sanaldi: {_som(session.counted_cash)}",
              ("✅ Farq yo'q" if not diff else f"{'⚠️ Kamomad' if diff < 0 else '➕ Ortiqcha'}: <b>{_som(abs(diff))} so'm</b>")]
    cashiers = by_cashier(session)
    if cashiers:
        lines += ["", "<b>Kassirlar:</b>"] + [f"• {html.escape(c['name'])}: {c['sales']} ta · {_som(c['revenue'])} so'm" for c in cashiers]
    if session.closing_note:
        lines += ["", f"\U0001F4DD {html.escape(session.closing_note)}"]
    return "\n".join(lines)


def send(session_id) -> dict:
    from apps.notifications.infrastructure.notify import notify
    from apps.stores.infrastructure.models import CashSession

    session = CashSession.objects.select_related("store").filter(id=session_id).first()
    if session is None or session.status != "closed":
        return {"sent": False}
    out = {"owner": False, "channel": False}
    if session.store.owner_id:
        revenue = (session.cash_sales or 0) + (session.uzcard_sales or 0) + (session.humo_sales or 0) + (session.coins_redeemed or 0)
        notify(session.store.owner_id, "shift_closed", {"store": session.store.name, "sales": session.sales_count, "revenue": _som(revenue),
                                                        "difference": _som(session.cash_difference)}, dedupe_key=f"shift_closed:{session.id}")
        out["owner"] = True
    chat = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    if chat:
        try:
            from apps.notifications.infrastructure import composition

            composition.build_orders_telegram_gateway().send_message_with_keyboard(str(chat), report_text(session), [])
            out["channel"] = True
        except Exception:  # noqa: BLE001 - a Telegram hiccup must never affect the closed shift
            logger.exception("Z-report: Telegram channel post failed for session %s", session_id)
    return out
