"""
Fiscal receipts through Payme's virtual kassa (Payme Business → "Фискализация").

1. CheckPerformTransaction answers with `detail` -- the receipt Payme registers with the tax OFD:
   {receipt_type: 0, shipping: {title, price}, items: [{title, price (per unit, tiyin), count, code (MXIK/IKPU),
   package_code, vat_percent, discount (tiyin, for the whole line)}]}. The lines add up exactly to the amount Payme
   charges: each line carries its own discount (coupons / coins live there), delivery goes in `shipping` only when
   Payme charges it, and any other gap is spread over the lines with the remainder on the last one.
2. Payme then calls SetFiscalData {id, type: PERFORM|CANCEL, fiscal_data: {receipt_id, status_code, message,
   terminal_id, fiscal_sign, qr_code_url, date}}: kept on the payment and copied onto the order's receipt (now or
   when the receipt is made at delivery), so the customer's e-receipt shows the tax QR.

Switched on in Dashboard → Cheklar → Chek sozlamalari ("Payme orqali fiskal chek"); off → plain {"allow": true}.
A line without MXIK / package code never blocks the payment: the detail is left out and the reason is logged.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

logger = logging.getLogger("nutrizone.receipts.payme")


def _tiyin(value) -> int:
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def enabled() -> bool:
    from apps.receipts.infrastructure.models import ReceiptSettings

    return ReceiptSettings.get().payme_fiscal


def detail(order, amount_tiyin: int) -> dict | None:
    """The Payme `detail` for this order, or None (with a log line) when it can't be a valid fiscal receipt."""
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.receipts.infrastructure.builders import _tax_codes, order_data
    from apps.receipts.infrastructure.models import ReceiptSettings

    s = ReceiptSettings.get()
    data = order_data(order)
    lines = list(OrderLineItemModel.objects.filter(order_id=order.id, status="active").order_by("id"))
    codes = _tax_codes([li.product_variant_id for li in lines])
    vat = float(s.vat_rate) if s.vat_payer else 0
    items, missing = [], []
    for item, li in zip(data["items"], lines):
        mxik, package = codes.get(li.product_variant_id) or ("", "")
        if not (mxik and package):
            missing.append(item["name"])
        items.append({"title": (item["name"] + (f" {item['variant_label']}" if item.get("variant_label") else ""))[:128],
                      "price": _tiyin(item["unit_price"]), "count": int(item["quantity"]), "code": mxik, "package_code": package,
                      "vat_percent": vat, "discount": 0})
    if not items:
        return None
    if missing:
        logger.warning("payme fiscal: order %s sent without detail -- no MXIK/package code: %s", order.order_number, ", ".join(missing[:5]))
        return None

    # each line's own discount (coupons / coins already sit there, like service.payable); shipping only when Payme charges it
    for i, li in zip(items, lines):
        i["discount"] = min(_tiyin(li.discount_amount) - _tiyin(li.tax_amount), i["price"] * i["count"])
    shipping = _tiyin(data.get("delivery"))
    net = sum(i["price"] * i["count"] - i["discount"] for i in items)
    if net + shipping == amount_tiyin and shipping:
        pass
    elif net == amount_tiyin:
        shipping = 0
    else:  # anything else (partly prepaid, rounding): spread the difference over the lines, last line takes the remainder
        shipping = 0
        gross = sum(i["price"] * i["count"] for i in items)
        off = gross - amount_tiyin
        if off < 0 or off > gross:
            logger.warning("payme fiscal: order %s amounts don't reconcile (lines %s vs %s)", order.order_number, gross, amount_tiyin)
            return None
        left = off
        for n, i in enumerate(items):
            line = i["price"] * i["count"]
            share = left if n == len(items) - 1 else min(left, int(Decimal(off) * line / gross))
            i["discount"], left = share, left - share
    for i in items:
        if i["discount"] <= 0:
            i.pop("discount")
    out = {"receipt_type": 0, "items": items}
    if shipping:
        out["shipping"] = {"title": "Yetkazib berish", "price": shipping}
    return out


def save_fiscal_data(payment, kind: str, data: dict) -> None:
    """SetFiscalData: keep it on the payment; a successful PERFORM receipt also lands on the order's receipt."""
    from apps.payment.infrastructure.models import PaymentModel

    fiscal = dict((payment.meta or {}).get("fiscal") or {})
    fiscal[kind.lower()] = {**data, "received_at": timezone.now().isoformat()}
    PaymentModel.objects.filter(pk=payment.pk).update(meta={**(payment.meta or {}), "fiscal": fiscal})
    if kind == "PERFORM":
        apply_to_receipt(payment.order_id, data)


def _ok(data: dict) -> bool:
    return bool(data.get("fiscal_sign")) and str(data.get("status_code", 0)) in ("0", "None", "")


def apply_to_receipt(order_id, data: dict | None = None) -> bool:
    """Copies Payme's fiscal sign / QR onto the order's receipt (called on SetFiscalData and when the receipt is made)."""
    from apps.payment.infrastructure.models import PaymentModel
    from apps.receipts.infrastructure.models import Receipt, ReceiptStatus

    if data is None:
        for meta in PaymentModel.objects.filter(order_id=order_id, provider="payme").values_list("meta", flat=True):
            perform = ((meta or {}).get("fiscal") or {}).get("perform")
            if perform and _ok(perform):
                data = perform
                break
    receipt = Receipt.objects.filter(order_id=order_id).first()
    if receipt is None or not data:
        return False
    if not _ok(data):
        Receipt.objects.filter(pk=receipt.pk).update(status=ReceiptStatus.FISCAL_FAILED, fiscal_provider="payme",
                                                     fiscal_error=f"Payme OFD: {data.get('status_code')} {data.get('message') or ''}"[:1000])
        return False
    Receipt.objects.filter(pk=receipt.pk).update(
        status=ReceiptStatus.FISCALIZED, fiscal_provider="payme", fiscal_terminal_id=str(data.get("terminal_id") or "")[:64],
        fiscal_number=str(data.get("receipt_id") or "")[:64], fiscal_sign=str(data.get("fiscal_sign") or "")[:128],
        fiscal_url=str(data.get("qr_code_url") or "")[:500], fiscalized_at=timezone.now(), fiscal_error="")
    return True
