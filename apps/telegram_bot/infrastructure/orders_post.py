"""
@NutriZoneOrdersBot -- the order card posted to the staff Orders channel, built in one place so the post looks the same
when it is first sent and after a manager confirms / cancels it (the details stay; only the status banner and the
buttons change). Telegram HTML only; every customer-typed text is escaped.
"""
from __future__ import annotations

from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")
CAPTION_LIMIT = 1024  # a photo caption can't be longer -- longer cards go out as a text message
METHOD = {"cash": "Naqd", "payme": "Payme", "click": "Click", "uzum": "Uzum", "uzcard": "Uzcard", "humo": "Humo"}


def money(amount, currency: str = "UZS") -> str:
    unit = "so'm" if currency == "UZS" else currency
    return f"{int(round(Decimal(str(amount or 0)))):,}".replace(",", " ") + f" {unit}"


def _product_names(variant_ids) -> tuple[dict, str | None]:
    from apps.products.infrastructure import models as products_orm
    from apps.products.infrastructure.selectors import ProductDetailSelector

    selector, names, image = ProductDetailSelector(), {}, None
    for variant in products_orm.ProductVariant.objects.filter(id__in=list(variant_ids)).select_related("product", "flavour").prefetch_related("flavour__translations"):
        product = selector.get_by_id(variant.product_id, locale="uz")
        if product:
            from apps.products.infrastructure.variant_labels import variant_label

            label = variant_label(variant, package=False)
            size = f" · {label}" if label else ""
            names[variant.id] = f"{product['name']}{size}"
            image = image or product.get("primary_image_path")
    return names, image


def _payment_line(order) -> str:
    from apps.payment.infrastructure.models import PaymentModel

    paid = PaymentModel.objects.filter(order_id=order.id, status="succeeded").order_by("-paid_at").values_list("method", "provider").first()
    if paid:
        return f"💳 To'lov: ✅ <b>{escape(METHOD.get(paid[0] or paid[1], (paid[0] or paid[1] or '').title()))} orqali to'langan</b>"
    if order.status.value == "pending_payment":
        pending = PaymentModel.objects.filter(order_id=order.id).exclude(status__in=("failed", "cancelled")).values_list("method", "provider").first()
        if pending:
            return f"💳 To'lov: ⏳ {escape(METHOD.get(pending[0] or pending[1], 'onlayn'))} — kutilmoqda"
    return "💳 To'lov: 💵 Naqd (qabul qilishda)"


def _totals(order) -> list[str]:
    from apps.loyalty.infrastructure.services import coins_spent_on_order

    totals = order.compute_total()
    cash = totals.grand_total
    coins = Decimal(coins_spent_on_order(order.id) or 0)
    other_discount = totals.discount_total.amount - coins
    out = []
    if other_discount > 0:
        out.append(f"🎟 Chegirma: −{money(other_discount, cash.currency)}")
    if coins:
        out.append(f"🪙 Coins bilan: −{money(coins, cash.currency)}")
        out.append(f"💰 <b>Olinadigan summa: {money(cash.amount, cash.currency)}</b>  <i>(jami {money(cash.amount + coins, cash.currency)})</i>")
    else:
        out.append(f"💰 <b>Jami: {money(cash.amount, cash.currency)}</b>")
    return out


def _customer_line(order, address) -> str:
    from apps.ordering.infrastructure.models import OrderModel

    name = escape(address.recipient_name) if address and address.recipient_name else "Mijoz"
    badge = ""
    if order.customer_id:
        n = OrderModel.objects.filter(customer_id=order.customer_id).exclude(status="draft").count()
        badge = " · 🆕 birinchi buyurtma" if n <= 1 else f" · ⭐ {n}-buyurtma"
    return f"👤 <b>{name}</b>{badge}"


def build(order, banner: str | None = None) -> dict:
    """{'text', 'image', 'has_point', 'address'} for one order. `banner` replaces the "new order" headline once resolved."""
    from apps.ordering.infrastructure.models import OrderModel
    from apps.stores.infrastructure.models import Store

    address = order.shipping_address
    row = OrderModel.objects.filter(pk=order.id).values("fulfilment_method", "fulfilment_store_id").first() or {}
    pickup = row.get("fulfilment_method") == "pickup"
    branch = Store.objects.filter(pk=row.get("fulfilment_store_id")).first() if row.get("fulfilment_store_id") else None
    has_point = address is not None and address.latitude is not None and address.longitude is not None

    lines = order.active_lines()
    names, image = _product_names({ln.product_variant_id for ln in lines})
    units = sum(ln.quantity for ln in lines)
    items = "\n".join(
        f"▫️ {escape(names.get(ln.product_variant_id, 'Mahsulot'))}\n      {ln.quantity} × {money(ln.unit_price.amount, ln.unit_price.currency)} = <b>{money(ln.unit_price.amount * ln.quantity, ln.unit_price.currency)}</b>"
        for ln in lines
    )

    placed = order.placed_at.astimezone(TZ).strftime("%d.%m.%Y · %H:%M") if order.placed_at else ""
    method = f"🏪 <b>Olib ketish</b> — {escape(branch.name)}" if pickup and branch else "🚚 <b>Yetkazib berish</b>" + (f" — {escape(branch.name)}" if branch else "")
    head = banner or "🆕 <b>YANGI BUYURTMA</b>"
    out = [f"{head}  ·  <code>{escape(order.order_number.value)}</code>", f"{method}" + (f"\n🕒 {placed}" if placed else ""), ""]
    out.append(_customer_line(order, address))
    if address and address.phone:
        out.append(f"📞 {escape(address.phone)}")
    if not pickup and address:
        out.append(f"🏠 {escape(', '.join(x for x in (address.line1, address.city) if x))}")
        if address.line2:
            out.append(f"🚪 {escape(address.line2)}")  # podyezd · qavat · domofon · mo'ljal
    if has_point:  # links in the text too: buttons are lost when the post is forwarded to a courier
        out.append(f"📍 <a href=\"https://yandex.uz/maps/?pt={address.longitude:.6f},{address.latitude:.6f}&z=17\">Yandex</a> · "
                   f"<a href=\"https://maps.google.com/?q={address.latitude},{address.longitude}\">Google</a>")
    if order.customer_comment:
        out.append(f"💬 <i>«{escape(order.customer_comment.text[:300])}»</i>")
    out += ["", f"🛍 <b>Mahsulotlar</b> — {len(lines)} xil, {units} dona", f"<blockquote>{items}</blockquote>", _payment_line(order), *_totals(order)]
    return {"text": "\n".join(out), "image": image, "has_point": has_point, "address": address}


def dashboard_url(order_id) -> str | None:
    from django.conf import settings

    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return f"{base}/django-admin/ordering/ordermodel/{order_id}/change/" if base.startswith("https://") else None


def map_rows(order, address) -> list:
    la, ln = f"{address.latitude:.6f}", f"{address.longitude:.6f}"
    return [
        [{"text": "🧭 Yandex yo'nalish", "url": f"https://yandex.uz/maps/?rtext=~{la},{ln}&rtt=auto"}, {"text": "Google", "url": f"https://www.google.com/maps/search/?api=1&query={la},{ln}"}],
        [{"text": "Apple Maps", "url": f"https://maps.apple.com/?ll={la},{ln}&q={order.order_number.value}"}, {"text": "2GIS", "url": f"https://2gis.uz/geo/{ln},{la}"}],
    ]


def open_keyboard(order, card: dict) -> list:
    row = [{"text": "✅ Tasdiqlash", "callback_data": f"manager:confirm:{order.id}"}, {"text": "❌ Bekor qilish", "callback_data": f"manager:cancel:{order.id}"}]
    keyboard = [row]
    if card["has_point"]:
        keyboard += map_rows(order, card["address"])
    url = dashboard_url(order.id)
    if url:
        keyboard.append([{"text": "🖥 Dashboard'da ochish", "url": url}])
    return keyboard


def resolved_keyboard(order, card: dict, confirmed: bool) -> list:
    """After a decision: no more Confirm/Cancel; a confirmed delivery keeps the route buttons for the courier."""
    keyboard = map_rows(order, card["address"]) if confirmed and card["has_point"] else []
    url = dashboard_url(order.id)
    if url:
        keyboard.append([{"text": "🖥 Dashboard'da ochish", "url": url}])
    return keyboard


def banner(action: str, who: str | None) -> str:
    from django.utils import timezone

    at = timezone.now().astimezone(TZ).strftime("%H:%M")
    by = f" — {escape(who)}" if who else ""
    return f"✅ <b>TASDIQLANDI</b> · {at}{by}" if action == "confirm" else f"❌ <b>BEKOR QILINDI</b> · {at}{by}"


def fits_caption(text: str) -> bool:
    import re

    return len(re.sub(r"<[^>]+>", "", text)) <= CAPTION_LIMIT

