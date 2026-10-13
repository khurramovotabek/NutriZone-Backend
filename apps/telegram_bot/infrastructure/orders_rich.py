"""
@NutriZoneOrdersBot -- premium rich posts (Telegram Rich Messages) for a till sale and an online order:

  header picture   kind badge, receipt / order number, branch + cashier, the amount and how it was paid
  who / where      branch, cashier, customer (name, phone, how many purchases), time, delivery address + live map
  basket table     # · product (size) · qty · unit price · line total · stock left at that branch right now
  money table      items, discount, delivery, returns, TOTAL, then the split: coins (and their share) vs. every
                   money method (cash, Uzcard, Humo, Payme …), coins earned on this purchase
The same documents go to the staff Orders channel and to the owner of the branch (store_posts.py).
"""
from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.telegram_bot.infrastructure import charts
from apps.telegram_bot.infrastructure import rich as R

TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")
METHOD = {"cash": "💵 Naqd", "uzcard": "💳 Uzcard", "humo": "💳 Humo", "card": "💳 Karta", "click": "📱 Click", "payme": "📱 Payme", "uzum": "📱 Uzum",
          "mixed": "🔀 Aralash", "cod": "💵 Naqd (qabul qilishda)"}
STATUS = {"pending_payment": ("⏳", "To'lov kutilmoqda"), "confirmed": ("✅", "Tasdiqlangan"), "processing": ("📦", "Yig'ilmoqda"), "shipped": ("🚚", "Yo'lda"),
          "delivered": ("🎉", "Yetkazildi"), "completed": ("🏁", "Yakunlandi"), "cancelled": ("❌", "Bekor qilindi"), "returned": ("↩️", "Qaytarildi"), "failed": ("⚠️", "Muvaffaqiyatsiz")}


def som(v) -> str:
    return f"{int(round(Decimal(str(v or 0)))):,}".replace(",", " ") + " so'm"


def num(v) -> str:
    return f"{int(round(Decimal(str(v or 0)))):,}".replace(",", " ")


def _base_url() -> str:
    return (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")


def _customer(customer_id) -> dict:
    """Name, phone and how many purchases (till + online) this customer has made so far."""
    if not customer_id:
        return {}
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel
    from apps.pos.infrastructure.models import SaleModel

    u = User.objects.filter(id=customer_id).only("full_name", "phone_number", "telegram_username").first()
    if u is None:
        return {}
    n = SaleModel.objects.filter(customer_id=customer_id, status__in=("completed", "refunded")).count() + OrderModel.objects.filter(customer_id=customer_id).exclude(status="draft").count()
    return {"name": u.full_name or "Mijoz", "phone": u.phone_number or "", "username": u.telegram_username or "", "count": n}


def _customer_cell(c: dict) -> str:
    if not c:
        return R.i("Mijozsiz (anonim chek)")
    badge = "🆕 birinchi xarid" if c["count"] <= 1 else f"⭐ {c['count']}-xarid"
    tg = f" · @{R.e(c['username'])}" if c.get("username") else ""
    return f"{R.b(c['name'])} · {R.phone(c['phone'])}{tg} · {R.e(badge)}"


def _stock_map(store_id, variant_ids) -> dict:
    if not store_id or not variant_ids:
        return {}
    from apps.stores.infrastructure.models import Store
    from apps.stores.infrastructure.stock_service import available_map

    store = Store.objects.filter(id=store_id).first()
    return available_map(store, variant_ids) if store else {}


def _stock_cell(left) -> str:
    if left is None:
        return "—"
    if left <= 0:
        return "<mark>tugadi</mark>"
    return f"<b>{left}</b>" + (" ⚠️" if left <= 3 else "")


def _variant_names(variant_ids) -> dict:
    from apps.stores.infrastructure.stock_service import variant_infos

    return variant_infos([v for v in variant_ids if v])


def _product_names(product_ids) -> dict:
    from apps.products.infrastructure.models import ProductTranslation

    names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in=list(product_ids)).values("product_id", "locale_code", "name"):
        if tr["name"] and (tr["product_id"] not in names or tr["locale_code"] == "uz"):
            names[tr["product_id"]] = tr["name"]
    return names


def _photos(doc: R.RichDoc, urls: list) -> str:
    """The basket's product photos in one compact band -- staff recognise the box faster than the name."""
    from apps.telegram_bot.infrastructure import shop_rich

    try:
        return R.figure("items") if doc.image("items", shop_rich.strip(list(dict.fromkeys(u for u in urls if u)))) else ""
    except Exception:  # noqa: BLE001 -- pictures are a bonus, never block the post
        return ""


def _info_table(rows: list[tuple[str, str]]) -> str:
    return R.table([], [[R.e(k), v] for k, v in rows if v], align=["left", "left"])


# ---------------------------------------------------------------- POS sale


def sale_doc(sale_id, audience: str = "channel") -> tuple[R.RichDoc, list] | tuple[None, None]:
    from apps.loyalty.infrastructure.models import WalletTransaction
    from apps.pos.infrastructure import sales_reports as rep
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel
    from apps.stores.infrastructure.models import Store

    rows = rep.rows(SaleModel.objects.filter(id=sale_id))
    if not rows:
        return None, None
    s = rows[0]
    sale = SaleModel.objects.get(id=sale_id)
    key = rep.branch_key(s)
    branch_name = rep.store_names([key]).get(key, "—")
    store = Store.objects.filter(id=s["branch_id"]).first() if key != rep.CENTRAL else None
    cashier = rep.people_names([s["cashier_id"]]).get(s["cashier_id"], "—")
    cust = _customer(s["customer_id"])
    when = timezone.localtime(s["when"], TZ)
    number = s["receipt_number"] or f"#{str(sale_id)[:8].upper()}"

    lines = list(SaleLineItemModel.objects.filter(sale_id=sale_id).values("product_id", "product_variant_id", "quantity", "refunded_quantity", "unit_price_amount"))
    infos = _variant_names({ln["product_variant_id"] for ln in lines})
    pnames = _product_names({ln["product_id"] for ln in lines if ln["product_variant_id"] not in infos})
    stock = _stock_map(store.id if store else None, [ln["product_variant_id"] for ln in lines if ln["product_variant_id"]])
    basket = []
    for k, ln in enumerate(lines, 1):
        info = infos.get(ln["product_variant_id"])
        name = info.name if info else pnames.get(ln["product_id"], "Mahsulot")
        size = f" · {info.size}" if info and info.size else ""
        sku = f" · <code>{R.e(info.sku)}</code>" if info and info.sku else ""
        qty = ln["quantity"] - ln["refunded_quantity"]
        qty_txt = f"{qty}" + (f" <s>{ln['quantity']}</s>" if ln["refunded_quantity"] else "")
        basket.append([str(k), f"{R.b(name)}{R.e(size)}{sku} · <i>{qty_txt} × {num(ln['unit_price_amount'])}</i>", R.b(num(ln["unit_price_amount"] * qty)),
                       _stock_cell(stock.get(ln["product_variant_id"])) if ln["product_variant_id"] else "—"])
    units = sum(ln["quantity"] - ln["refunded_quantity"] for ln in lines)

    coins = s["coins_kept"]
    total = s["revenue"]
    split = {m: v for m, v in s["split"].items() if v}
    money_rows = [[R.e("Mahsulotlar"), num(s["gross"])]]
    if s["discount_amount"]:
        money_rows.append([R.e(f"Chegirma{(' — ' + sale.discount_reason) if sale.discount_reason else ''}"), f"−{num(s['discount_amount'])}"])
    if s["delivery_fee_amount"]:
        money_rows.append([R.e("Yetkazib berish"), f"+{num(s['delivery_fee_amount'])}"])
    if s["returned"]:
        money_rows.append([R.e("Qaytarilgan"), f"−{num(s['returned'])}"])
    money_rows.append([R.b("JAMI"), R.b(som(total))])
    pay_rows = []
    if coins:
        share = f" ({coins / total * 100:.0f}%)" if total else ""
        pay_rows.append([R.e("🪙 NutriZone Coins") + R.e(share), R.b(num(coins))])
    for m, v in split.items():
        pay_rows.append([R.e(METHOD.get(m, m)), R.b(num(v))])
    earned = WalletTransaction.objects.filter(order_id=sale_id, kind="earn").values_list("amount", flat=True).first()

    pay_note = " · ".join([f"Coins {num(coins)}"] * bool(coins) + [f"{METHOD.get(m, m).split(' ', 1)[-1]} {num(v)}" for m, v in split.items()]) or "To'lov yo'q"
    doc = R.RichDoc()
    accent = charts.hex_rgb(store.color if store else "#6366F1")
    doc.image("head", charts.receipt_banner("POS SAVDO", number, f"{branch_name} · Kassir: {cashier}", som(total), pay_note, accent))
    status = "↩️ <b>Qisman qaytarilgan</b>" if s["returned"] and s["status"] == "completed" else ("↩️ <b>Qaytarilgan</b>" if s["status"] == "refunded" else "✅ <b>To'langan</b>")
    doc.add(
        R.figure("head"),
        R.h(2, f"🧾 Kassa savdosi · {R.e(number)}"),
        R.p(f"{status} · {R.time_tag(when)} · {units} dona"),
        _info_table([("🏪 Filial", R.b(branch_name)), ("🧑‍💼 Kassir", R.e(cashier)), ("👤 Mijoz", _customer_cell(cust)),
                     ("🕒 Vaqt", R.e(when.strftime("%d.%m.%Y · %H:%M"))), ("🏷 Kanal", R.e("Kassa (POS terminal)" if s["channel"] == "store" else "Dashboard kassa"))]),
        R.h(3, "🛍 Mahsulotlar"),
        _photos(doc, [infos[ln["product_variant_id"]].image_url for ln in lines if ln["product_variant_id"] in infos]),
        R.table(["#", "Mahsulot", "Summa", "Qoldiq"], basket, align=["center", "left", "right", "center"]),
        R.h(3, "💰 Hisob-kitob"),
        R.table([], money_rows, align=["left", "right"]),
        R.h(3, "💳 To'lov taqsimoti") if pay_rows else "",
        R.table(["Usul", "Summa"], pay_rows, align=["left", "right"]) if pay_rows else "",
        R.aside(f"🪙 Bu xariddan {num(earned)} coin to'plandi") if earned else "",
    )
    keyboard = _sale_keyboard(sale)
    doc.add(R.footer(f"NutriZone Orders · {R.e(timezone.localtime(timezone.now(), TZ).strftime('%d.%m.%Y %H:%M'))}"))
    doc.fallback = _sale_fallback(number, branch_name, cashier, cust, lines, infos, pnames, total, coins, split)
    return doc, keyboard


def _sale_keyboard(sale) -> list:
    from apps.pos.infrastructure.receipts import public_url

    row = []
    base = _base_url()
    if base.startswith("https://"):
        row.append({"text": "🖥 Dashboard", "url": f"{base}/django-admin/pos/salemodel/{sale.id}/change/"})
    receipt = public_url(sale.receipt_token)
    if receipt and receipt.startswith("https://"):
        row.append({"text": "🧾 Elektron chek", "url": receipt})
    return [row] if row else []


def _sale_fallback(number, branch, cashier, cust, lines, infos, pnames, total, coins, split) -> str:
    items = "\n".join(f"• {R.e((infos[ln['product_variant_id']].name if ln['product_variant_id'] in infos else pnames.get(ln['product_id'], 'Mahsulot')))} — "
                      f"{ln['quantity'] - ln['refunded_quantity']} × {som(ln['unit_price_amount'])}" for ln in lines)
    pay = "\n".join([f"🪙 Coins: {som(coins)}"] * bool(coins) + [f"{METHOD.get(m, m)}: {som(v)}" for m, v in split.items()])
    who = f"{R.e(cust.get('name'))} · {R.e(cust.get('phone'))}" if cust else "Anonim"
    return (f"🧾 <b>KASSA SAVDOSI · {R.e(number)}</b>\n🏪 {R.e(branch)} · 🧑‍💼 {R.e(cashier)}\n👤 {who}\n\n{items}\n\n"
            f"💰 <b>Jami: {som(total)}</b>\n{pay}")


# ---------------------------------------------------------------- online order


def order_doc(order_id, banner: str | None = None, audience: str = "channel") -> tuple[R.RichDoc, dict] | tuple[None, None]:
    """(doc, meta) for an online order; meta carries what the keyboards need (has_point, lat/lng, number, status)."""
    from apps.loyalty.infrastructure.services import coins_spent_on_order
    from apps.ordering.infrastructure import composition as ordering_composition
    from apps.ordering.infrastructure.models import OrderModel
    from apps.payment.infrastructure.models import PaymentModel
    from apps.stores.infrastructure.models import Store

    order = ordering_composition.build_order_repository().get_by_id(order_id)
    row = OrderModel.objects.filter(pk=order_id).values("fulfilment_method", "fulfilment_store_id", "status").first()
    if order is None or row is None:
        return None, None
    status = row["status"]
    pickup = row["fulfilment_method"] == "pickup"
    store = Store.objects.filter(pk=row["fulfilment_store_id"]).first() if row["fulfilment_store_id"] else None
    address = order.shipping_address
    has_point = bool(address and address.latitude is not None and address.longitude is not None)
    cust = _customer(order.customer_id)
    placed = timezone.localtime(order.placed_at or timezone.now(), TZ)

    lines = order.active_lines()
    infos = _variant_names({ln.product_variant_id for ln in lines})
    stock = _stock_map(store.id if store else _warehouse_id(), [ln.product_variant_id for ln in lines])
    basket = []
    for k, ln in enumerate(lines, 1):
        info = infos.get(ln.product_variant_id)
        name = info.name if info else "Mahsulot"
        size = f" · {info.size}" if info and info.size else ""
        sku = f" · <code>{R.e(info.sku)}</code>" if info and info.sku else ""
        basket.append([str(k), f"{R.b(name)}{R.e(size)}{sku} · <i>{ln.quantity} × {num(ln.unit_price.amount)}</i>", R.b(num(ln.unit_price.amount * ln.quantity)),
                       _stock_cell(stock.get(ln.product_variant_id))])
    units = sum(ln.quantity for ln in lines)

    totals = order.compute_total()
    cash = totals.grand_total.amount
    coins = Decimal(coins_spent_on_order(order.id) or 0)
    gross = cash + totals.discount_total.amount
    other_discount = totals.discount_total.amount - coins
    money_rows = [[R.e("Mahsulotlar"), num(gross)]]
    if other_discount > 0:
        money_rows.append([R.e("Chegirma / kupon"), f"−{num(other_discount)}"])
    money_rows.append([R.b("JAMI"), R.b(som(cash + coins))])
    pay_rows = []
    if coins:
        pay_rows.append([R.e(f"🪙 NutriZone Coins ({coins / (cash + coins) * 100:.0f}%)") if cash + coins else R.e("🪙 NutriZone Coins"), R.b(num(coins))])
    paid = PaymentModel.objects.filter(order_id=order.id, status="succeeded").values_list("method", "provider").first()
    if paid:
        pay_rows.append([R.e(METHOD.get(paid[0] or paid[1], (paid[0] or paid[1]).title()) + " ✅ to'langan"), R.b(num(cash))])
    elif status == "pending_payment":
        pay_rows.append([R.e("⏳ Onlayn to'lov kutilmoqda"), R.b(num(cash))])
    else:
        pay_rows.append([R.e("💵 Naqd — qabul qilishda olinadi"), R.b(num(cash))])

    icon, label = STATUS.get(status, ("•", status))
    kind = "OLIB KETISH" if pickup else "ONLAYN BUYURTMA"
    where = f"{store.name}" if store else ("Filial tanlanmagan" if pickup else "Yetkazib berish")
    accent = charts.hex_rgb(store.color if store else "#06B6D4", charts.CYAN)
    doc = R.RichDoc()
    doc.image("head", charts.receipt_banner(kind, order.order_number.value, where, som(cash + coins),
                                            (f"Coins {num(coins)} · " if coins else "") + ("To'langan" if paid else "Naqd " + num(cash)), accent))
    head = banner or f"{icon} <b>{R.e(label)}</b>"
    info = [("📌 Holat", head), ("🏪 Filial", R.b(store.name) if store else R.i("hali biriktirilmagan")),
            ("🚚 Usul", R.e("Do'kondan olib ketish" if pickup else "Yetkazib berish")), ("👤 Mijoz", _customer_cell(cust) if cust else R.e(address.recipient_name if address else "—")),
            ("📞 Qabul qiluvchi", (R.e(address.recipient_name) + " · " + R.phone(address.phone)) if address and address.phone else ""),
            ("🕒 Berilgan", R.e(placed.strftime("%d.%m.%Y · %H:%M")))]
    if address and not pickup:
        info.append(("🏠 Manzil", R.e(", ".join(x for x in (address.line1, address.city) if x)) + (f" · 🚪 {R.e(address.line2)}" if address.line2 else "")))
    doc.add(
        R.figure("head"),
        R.h(2, f"{'🏪' if pickup else '🛒'} {R.e(order.order_number.value)}"),
        R.p(f"{head} · {R.time_tag(placed)} · {units} dona"),
        _info_table(info),
    )
    if order.customer_comment:
        doc.add(R.quote(R.e(order.customer_comment.text[:400]), cite="Mijoz izohi"))
    if has_point and not pickup:
        doc.add(R.map_block(float(address.latitude), float(address.longitude), 16, "📍 Yetkazish nuqtasi"))
    doc.add(
        R.h(3, "🛍 Mahsulotlar"),
        _photos(doc, [infos[ln.product_variant_id].image_url for ln in lines if ln.product_variant_id in infos]),
        R.table(["#", "Mahsulot", "Summa", "Qoldiq"], basket, align=["center", "left", "right", "center"]),
        R.h(3, "💰 Hisob-kitob"),
        R.table([], money_rows, align=["left", "right"]),
        R.h(3, "💳 To'lov"),
        R.table(["Usul", "Summa"], pay_rows, align=["left", "right"]),
        R.footer(f"NutriZone Orders · {R.e(timezone.localtime(timezone.now(), TZ).strftime('%d.%m.%Y %H:%M'))}"),
    )
    from apps.telegram_bot.infrastructure import orders_post

    doc.fallback = orders_post.build(order, banner=banner)["text"]
    meta = {"order": order, "has_point": has_point and not pickup, "address": address, "status": status, "number": order.order_number.value}
    return doc, meta


def _warehouse_id():
    from apps.stores.infrastructure.models import Store

    return Store.objects.filter(kind="warehouse", status="active").values_list("id", flat=True).first()


# ---------------------------------------------------------------- the customer's own receipt (@nutrizonebot)


def customer_receipt_doc(order_number: str, lang: str = "uz") -> R.RichDoc | None:
    """What the shopper gets right after ordering in the bot: a branded header, the basket, what they pay and how,
    coins used, where it goes -- and a Mini App button to follow the order."""
    from apps.loyalty.infrastructure.services import coins_spent_on_order
    from apps.ordering.infrastructure import composition as ordering_composition
    from apps.ordering.infrastructure.models import OrderModel

    row = OrderModel.objects.filter(order_number=order_number).values("id", "fulfilment_method").first()
    if row is None:
        return None
    order = ordering_composition.build_order_repository().get_by_id(row["id"])
    lines = order.active_lines()
    infos = _variant_names({ln.product_variant_id for ln in lines})
    totals = order.compute_total()
    cash = totals.grand_total.amount
    coins = Decimal(coins_spent_on_order(order.id) or 0)
    basket = [[R.b(infos[ln.product_variant_id].name if ln.product_variant_id in infos else "Mahsulot") + (f" · {R.e(infos[ln.product_variant_id].size)}" if ln.product_variant_id in infos and infos[ln.product_variant_id].size else ""),
               str(ln.quantity), num(ln.unit_price.amount * ln.quantity)] for ln in lines]
    money = [[R.e("Mahsulotlar"), num(cash + totals.discount_total.amount)]]
    if totals.discount_total.amount - coins > 0:
        money.append([R.e("Chegirma"), f"−{num(totals.discount_total.amount - coins)}"])
    if coins:
        money.append([R.e("🪙 Coins bilan to'landi"), f"−{num(coins)}"])
    money.append([R.b("To'lanadi"), R.b(som(cash))])
    addr = order.shipping_address
    pickup = row["fulfilment_method"] == "pickup"
    doc = R.RichDoc()
    doc.image("head", charts.receipt_banner("BUYURTMA QABUL QILINDI", order.order_number.value, "Olib ketish" if pickup else "Yetkazib berish", som(cash),
                                            f"Coins {num(coins)} ishlatildi" if coins else "To'lov: qabul qilishda", charts.GREEN))
    doc.add(R.figure("head"), R.h(2, "🎉 Buyurtmangiz qabul qilindi!"),
            R.p(f"🧾 {R.b(order.order_number.value)} · operator tez orada bog'lanadi."),
            R.table(["Mahsulot", "Soni", "Summa"], basket, align=["left", "center", "right"]),
            R.table([], money, align=["left", "right"]))
    if addr and not pickup:
        doc.add(R.p(f"🏠 {R.e(', '.join(x for x in (addr.line1, addr.city) if x))}"))
    frontend = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    if frontend.startswith("https://"):
        doc.add(R.buttons(R.button("📦 Buyurtmani kuzatish", web_app=f"{frontend}/tg?next=/orders/{order.order_number.value}", style="primary")))
    doc.add(R.footer("NutriZone · rahmat, xaridingiz uchun!"))
    doc.fallback = (f"🎉 <b>Buyurtmangiz qabul qilindi!</b>\n🧾 {R.e(order.order_number.value)}\n💰 To'lanadi: {som(cash)}" + (f"\n🪙 Coins: {num(coins)}" if coins else ""))
    return doc
