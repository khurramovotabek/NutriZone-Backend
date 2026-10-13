"""
@NutriZoneOrdersBot -- the interactive side: /start, the menu and the lists.

/start registers the chat (staff_access.register) and answers with what this person may see: a store owner gets
their own branches only (today's till sales + online orders assigned to them), the staff allowlist gets every branch.
New sales/orders then arrive by themselves (store_posts.py). Everything is a Telegram rich message.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.telegram_bot.infrastructure import rich as R
from apps.telegram_bot.infrastructure import staff_access

logger = logging.getLogger("nutrizone.telegram_bot.orders")
TZ = ZoneInfo("Asia/Tashkent")
BOT = "orders"


def token() -> str:
    return getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None) or ""


def send(chat_id, doc: R.RichDoc, keyboard: list | None = None, silent: bool = False) -> int:
    return R.send(token(), chat_id, doc, keyboard, silent=silent)


def menu_keyboard() -> list:
    cb = lambda text, data: {"text": text, "callback_data": f"ob:{data}"}  # noqa: E731
    return [[cb("📋 Bugun", "today"), cb("🧾 Kassa savdolari", "sales")], [cb("🛒 Onlayn buyurtmalar", "orders"), cb("⏳ Jarayonda", "open")], [cb("🔄 Yangilash", "today")]]


def _today_bounds():
    now = timezone.localtime(timezone.now(), TZ)
    start = datetime.combine(now.date(), time.min, tzinfo=TZ)
    return start, start + timedelta(days=1)


def _sales(store_ids, start, end):
    from apps.pos.infrastructure import sales_reports as rep

    qs = rep.closed_sales().filter(channel="store", branch_id__in=list(store_ids), completed_at__gte=start, completed_at__lt=end)
    return rep.rows(qs)


def _orders(store_ids, start=None, end=None, statuses=None):
    from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum

    from apps.ordering.infrastructure.models import OrderModel

    line_total = ExpressionWrapper(F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
    qs = OrderModel.objects.exclude(status="draft").filter(fulfilment_store_id__in=list(store_ids))
    if start:
        qs = qs.filter(placed_at__gte=start, placed_at__lt=end)
    if statuses:
        qs = qs.filter(status__in=statuses)
    return list(qs.annotate(amount=Sum(line_total, filter=Q(lines__status="active"))).order_by("-placed_at").values("id", "order_number", "status", "placed_at", "amount", "fulfilment_method", "fulfilment_store_id", "shipping_recipient_name")[:40])


def _no_access(chat_id) -> R.RichDoc:
    doc = R.RichDoc()
    doc.add(R.h(2, "🔒 NutriZone Orders"),
            R.p("Bu bot filial egalari va NutriZone xodimlari uchun: kassa savdolari va onlayn buyurtmalar shu yerga keladi."),
            R.p(f"Sizning chat ID: {R.code(chat_id)}"),
            R.quote(R.e("Filial egasi bo'lsangiz — shu Telegram akkaunti bilan NutriZone'da ro'yxatdan o'tgan bo'lishingiz va filial sizga biriktirilgan bo'lishi kerak. Xodimlar uchun administratorga murojaat qiling.")))
    doc.fallback = f"🔒 Bu bot filial egalari va xodimlar uchun.\nChat ID: <code>{chat_id}</code>"
    return doc


def today_doc(scope: staff_access.Scope, focus: str = "today") -> R.RichDoc:
    from apps.pos.infrastructure import sales_reports as rep
    from apps.telegram_bot.infrastructure.orders_rich import STATUS, num, som

    start, end = _today_bounds()
    ids = scope.store_ids
    sales = [r for r in _sales(ids, start, end) if r["status"] in ("completed", "refunded")]
    orders = _orders(ids, start, end)
    open_orders = _orders(ids, statuses=("pending_payment", "confirmed", "processing", "shipped"))
    store_names = {s.id: s.name for s in scope.stores}
    people = rep.people_names({r["cashier_id"] for r in sales})
    revenue = sum((r["revenue"] for r in sales), 0)
    coins = sum((r["coins_kept"] for r in sales), 0)
    online_value = sum(((o["amount"] or 0) for o in orders if o["status"] not in ("cancelled", "failed", "returned")), 0)

    doc = R.RichDoc()
    title = "Barcha filiallar" if scope.all_access else ", ".join(s.name for s in scope.stores)
    doc.add(R.h(2, f"📋 {R.e(title)}"),
            R.p(f"Bugun · {R.time_tag(timezone.now(), 'dT', timezone.localtime(timezone.now(), TZ).strftime('%d.%m.%Y %H:%M'))} holatiga"),
            R.table(["Ko'rsatkich", "Qiymat"], [row for row in (
                [R.e("🧾 Kassa savdolari"), R.b(f"{len(sales)} ta · {som(revenue)}")],
                [R.e("🪙 Shundan coins bilan"), R.e(som(coins))] if coins else None,
                [R.e("🛒 Bugungi onlayn buyurtmalar"), R.b(f"{len(orders)} ta · {som(online_value)}")],
                [R.e("⏳ Jarayondagi buyurtmalar"), R.b(f"{len(open_orders)} ta")],
            ) if row], align=["left", "right"]))
    if focus in ("today", "sales"):
        rows = [[R.e(timezone.localtime(r["when"], TZ).strftime("%H:%M")), R.code(r["receipt_number"] or str(r["id"])[:8]),
                 R.e(store_names.get(r["branch_id"], "—")) if scope.all_access or len(scope.stores) > 1 else R.e(people.get(r["cashier_id"], "—")),
                 R.e(f"{r['units']} dona"), R.b(num(r["revenue"]))] for r in sales[:25]]
        third = "Filial" if scope.all_access or len(scope.stores) > 1 else "Kassir"
        doc.add(R.h(3, "🧾 Kassa savdolari"),
                R.table(["Vaqt", "Chek", third, "Soni", "Summa"], rows, align=["center", "left", "left", "center", "right"]) if rows else R.p(R.i("Bugun hali kassa savdosi yo'q")))
    if focus in ("today", "orders"):
        rows = [[R.e(timezone.localtime(o["placed_at"], TZ).strftime("%H:%M") if o["placed_at"] else "—"), R.code(o["order_number"]),
                 R.e(("🏪 " if o["fulfilment_method"] == "pickup" else "🚚 ") + (o["shipping_recipient_name"] or "")[:18]),
                 R.e(" ".join(STATUS.get(o["status"], ("", o["status"])))), R.b(num(o["amount"] or 0))] for o in orders[:25]]
        doc.add(R.h(3, "🛒 Bugungi onlayn buyurtmalar"),
                R.table(["Vaqt", "Raqam", "Mijoz", "Holat", "Summa"], rows, align=["center", "left", "left", "left", "right"]) if rows else R.p(R.i("Bugun onlayn buyurtma yo'q")))
    if focus in ("today", "open") and open_orders:
        rows = [[R.code(o["order_number"]), R.e(store_names.get(o["fulfilment_store_id"], "—")), R.e(" ".join(STATUS.get(o["status"], ("", o["status"])))),
                 R.e(timezone.localtime(o["placed_at"], TZ).strftime("%d.%m %H:%M") if o["placed_at"] else "—"), R.b(num(o["amount"] or 0))] for o in open_orders[:25]]
        block = R.table(["Raqam", "Filial", "Holat", "Berilgan", "Summa"], rows, align=["left", "left", "left", "center", "right"])
        doc.add(R.h(3, "⏳ Jarayondagi buyurtmalar") if focus == "open" else "", block if focus == "open" else R.details(f"⏳ Jarayondagi buyurtmalar — {len(open_orders)} ta", block))
    doc.add(R.footer("NutriZone Orders · yangi savdo va buyurtmalar shu chatga avtomatik keladi"))
    doc.fallback = (f"📋 <b>{R.e(title)}</b>\n🧾 Kassa: {len(sales)} ta · {som(revenue)}\n🛒 Onlayn: {len(orders)} ta · {som(online_value)}\n⏳ Jarayonda: {len(open_orders)} ta")
    return doc


def welcome_doc(scope: staff_access.Scope) -> R.RichDoc:
    doc = R.RichDoc()
    who = R.e(scope.name.split()[0]) if scope.name else "xush kelibsiz"
    stores = ", ".join(R.b(s.name) for s in scope.stores[:6]) + (f" va yana {len(scope.stores) - 6} ta" if len(scope.stores) > 6 else "")
    doc.add(R.h(1, "📦 NutriZone Orders"),
            R.p(f"Assalomu alaykum, {who}! " + ("Siz <b>barcha filiallar</b> bo'yicha xabarlarni olasiz." if scope.all_access else f"Siz {stores} filial(lar)i egasisiz.")),
            R.checklist([("Kassada (POS) har bir savdo — mahsulotlar, qoldiq, coins va naqd taqsimoti bilan", True),
                         ("Filialingizga biriktirilgan onlayn buyurtmalar va ularning holati", True),
                         ("Bugungi ro'yxat — istalgan payt «📋 Bugun» tugmasi bilan", True)]))
    doc.fallback = "📦 <b>NutriZone Orders</b>\nKassa savdolari va onlayn buyurtmalar shu chatga keladi."
    return doc


def handle_update(update: dict) -> bool:
    """/start, other texts and ob:* buttons. False = not handled here (e.g. the manager:* buttons)."""
    callback = update.get("callback_query")
    if callback:
        data = callback.get("data") or ""
        if not data.startswith("ob:"):
            return False
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        _answer(callback.get("id"))
        sc = staff_access.scope(BOT, chat_id, (callback.get("from") or {}).get("id"))
        if not sc.allowed:
            send(chat_id, _no_access(chat_id))
            return True
        send(chat_id, today_doc(sc, data[3:] or "today"), menu_keyboard())
        return True
    message = update.get("message")
    if not message or (message.get("chat") or {}).get("type") != "private":
        return False
    chat_id = message["chat"]["id"]
    staff_access.register(BOT, message)
    sc = staff_access.scope(BOT, chat_id, (message.get("from") or {}).get("id"))
    if not sc.allowed:
        send(chat_id, _no_access(chat_id))
        return True
    text = (message.get("text") or "").strip()
    if text.startswith("/start") or text.startswith("/menu"):
        send(chat_id, welcome_doc(sc))
    send(chat_id, today_doc(sc), menu_keyboard())
    return True


def _answer(callback_id) -> None:
    import contextlib

    with contextlib.suppress(Exception):
        R._api(token(), "answerCallbackQuery", json_body={"callback_query_id": callback_id})


def set_commands() -> None:
    R._api(token(), "setMyCommands", json_body={"commands": [{"command": "start", "description": "📋 Bugungi savdo va buyurtmalar"}, {"command": "menu", "description": "☰ Menyu"}]})
    R._api(token(), "setMyDescription", json_body={"description": "NutriZone filial egalari va xodimlari uchun: kassa savdolari, onlayn buyurtmalar, coins va naqd taqsimoti — har biri premium formatda."})
    R._api(token(), "setMyShortDescription", json_body={"short_description": "NutriZone — savdo va buyurtmalar"})
