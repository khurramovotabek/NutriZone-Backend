"""Receipt snapshots from a POS sale, an online order, or a manual entry -- all in the POS receipt() shape."""
from __future__ import annotations

import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.receipts.infrastructure.models import Receipt, ReceiptKind, ReceiptSettings, ReceiptSource, ReceiptStatus

ONLINE_SEQ, MANUAL_SEQ = "receipt_online_seq", "receipt_manual_seq"
TWO = Decimal("0.01")


def _next(seq: str, prefix: str) -> str:
    with connection.cursor() as cur:
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq}")
        cur.execute(f"SELECT nextval('{seq}')")
        return f"{prefix}-{cur.fetchone()[0]:06d}"


def vat_of(total: Decimal, s: ReceiptSettings) -> Decimal:
    """VAT included in the price: total × rate / (100 + rate)."""
    if not s.vat_payer or not total:
        return Decimal("0")
    rate = Decimal(s.vat_rate)
    return (Decimal(total) * rate / (Decimal(100) + rate)).quantize(TWO, ROUND_HALF_UP)


def _tax_codes(variant_ids) -> dict:
    """MXIK (IKPU) and package codes per variant (from the product), required on fiscal receipts."""
    from apps.products.infrastructure.models import ProductVariant

    return {v.id: (v.product.mxik_code, v.product.package_code) for v in ProductVariant.all_objects.filter(id__in=list(variant_ids)).select_related("product")}


def _decorate(data: dict, s: ReceiptSettings, codes_by_index: list | None = None) -> dict:
    data = dict(data)
    data["requisites"] = {"legal_name": s.legal_name, "tin": s.tin, "address": s.address, "phone": s.phone}
    data["vat"] = {"payer": s.vat_payer, "rate": str(s.vat_rate), "amount": str(vat_of(Decimal(data.get("total") or 0), s))}
    data["footer"] = s.footer
    if codes_by_index:
        data["items"] = [{**item, "mxik": c[0] if c else "", "package_code": c[1] if c else ""} for item, c in zip(data.get("items", []), codes_by_index)]
    return data


def _store(data: dict, **fields) -> Receipt:
    s = ReceiptSettings.get()
    total = Decimal(data.get("total") or 0)
    receipt = Receipt.objects.create(data=data, total=total, vat_amount=vat_of(total, s), **fields)
    if s.fiscal_auto and s.fiscal_provider != "none":
        from apps.receipts.infrastructure.tasks import fiscalize_receipt

        Receipt.objects.filter(pk=receipt.pk).update(status=ReceiptStatus.FISCAL_PENDING)
        transaction.on_commit(lambda: fiscalize_receipt.delay(str(receipt.pk)))
    return receipt


def from_sale(sale) -> Receipt | None:
    """A completed POS sale's receipt (idempotent -- one per sale; shares the slip's number and QR token)."""
    from apps.pos.infrastructure import receipts as pos_receipts
    from apps.pos.infrastructure.models import SaleLineItemModel

    existing = Receipt.objects.filter(sale_id=sale.id).first()
    if existing or not sale.receipt_number:
        return existing
    data = pos_receipts.receipt(sale, locale="uz", public=False)
    lines = list(SaleLineItemModel.objects.filter(sale_id=sale.id))
    codes = _tax_codes([li.product_variant_id for li in lines if li.product_variant_id])
    s = ReceiptSettings.get()
    data = _decorate(data, s, [codes.get(li.product_variant_id) for li in lines])
    customer = data.get("customer") or {}
    try:
        with transaction.atomic():
            return _store(data, number=sale.receipt_number, token=sale.receipt_token, source=ReceiptSource.POS, sale_id=sale.id,
                          store_id=sale.branch_id, customer_name=customer.get("name") or "", customer_phone=customer.get("phone") or "",
                          payment_method=sale.payment_method or "", issued_at=sale.completed_at or timezone.now(), created_by=data.get("cashier") or "")
    except IntegrityError:
        return Receipt.objects.filter(sale_id=sale.id).first()


def order_data(order) -> dict:
    from apps.loyalty.infrastructure.models import WalletTransaction
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.payment.infrastructure.models import PaymentModel
    from apps.pos.infrastructure.receipts import _names, _variant_label
    from apps.products.infrastructure.models import ProductVariant

    lines = list(OrderLineItemModel.objects.filter(order_id=order.id, status="active"))
    variants = {v.id: v for v in ProductVariant.all_objects.filter(id__in=[li.product_variant_id for li in lines]).select_related("package")}
    names = _names([v.product_id for v in variants.values()], "uz")
    items, subtotal, discount = [], Decimal(0), Decimal(0)
    for li in lines:
        v = variants.get(li.product_variant_id)
        line_total = li.unit_price_amount * li.quantity
        subtotal += line_total
        discount += li.discount_amount or 0
        items.append({"name": names.get(v.product_id) if v else "—", "variant_label": _variant_label(v) if v else None, "sku": v.sku if v else None,
                      "quantity": li.quantity, "unit_price": str(li.unit_price_amount), "line_total": str(line_total), "refunded_quantity": 0})
    coins = -sum((t.amount for t in WalletTransaction.objects.filter(order_id=order.id, kind="spend")), 0)
    delivery = Decimal(getattr(order, "shipping_estimated_amount", None) or 0)
    total = max(Decimal(0), subtotal - discount - Decimal(coins) + delivery)
    pay = PaymentModel.objects.filter(order_id=order.id, status__in=("captured", "paid", "performed", "succeeded")).order_by("-created_at").first()
    method = pay.provider if pay else "cash"
    return {
        "number": "", "token": "", "status": "completed", "channel": "online", "issued_at": None, "refunded_at": None,
        "seller": {"name": "NutriZone", "address": None, "phone": None}, "cashier": None, "kassa": None, "shift": None,
        "order_number": order.order_number, "items": items, "item_count": sum(li.quantity for li in lines),
        "subtotal": str(subtotal), "discount": str(discount), "coins": str(coins), "delivery": str(delivery), "total": str(total), "currency": order.currency or "UZS",
        "payment_method": method, "payments": [{"method": method, "amount": str(total)}], "refunds": [], "returned": "0",
        "amount_tendered": None, "change": None,
        "customer": {"name": order.shipping_recipient_name or order.billing_recipient_name, "phone": order.shipping_phone or order.billing_phone or ""},
        "coins_earned": 0, "tier": None,
    }


def from_order(order) -> Receipt | None:
    """A delivered / completed online order's receipt (idempotent)."""
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.platform.infrastructure.branding import brand_name

    existing = Receipt.objects.filter(order_id=order.id).first()
    if existing:
        return existing
    data = order_data(order)
    data["seller"]["name"] = brand_name()
    from apps.ordering.infrastructure.models import OrderStatusHistoryEntryModel

    done = OrderStatusHistoryEntryModel.objects.filter(order_id=order.id, to_status__in=("delivered", "completed")).order_by("changed_at").values_list("changed_at", flat=True).first()
    issued = done or order.updated_at or timezone.now()  # the moment the order was handed over (backfills keep their real date)
    number, token = _next(ONLINE_SEQ, "NZO"), secrets.token_urlsafe(12)
    data.update(number=number, token=token, issued_at=issued.isoformat())
    lines = list(OrderLineItemModel.objects.filter(order_id=order.id, status="active"))
    codes = _tax_codes([li.product_variant_id for li in lines])
    data = _decorate(data, ReceiptSettings.get(), [codes.get(li.product_variant_id) for li in lines])
    try:
        with transaction.atomic():
            return _store(data, number=number, token=token, source=ReceiptSource.ONLINE, order_id=order.id, order_number=order.order_number,
                          store_id=order.fulfilment_store_id, customer_name=data["customer"]["name"] or "", customer_phone=data["customer"]["phone"] or "",
                          payment_method=data["payment_method"], issued_at=issued)
    except IntegrityError:
        return Receipt.objects.filter(order_id=order.id).first()


def manual(*, lines: list[dict], customer_name: str = "", customer_phone: str = "", payment_method: str = "cash", note: str = "",
           kind: str = ReceiptKind.SALE, staff: str = "") -> Receipt:
    """A receipt typed in the dashboard: lines [{variant_id?, name, quantity, unit_price}]."""
    from apps.platform.infrastructure.branding import brand_name

    if not lines:
        raise ValueError("Kamida bitta mahsulot qatori kerak.")
    import uuid as _uuid

    def vid(ln):
        try:
            return _uuid.UUID(str(ln.get("variant_id"))) if ln.get("variant_id") else None
        except ValueError:
            return None

    items, subtotal, codes = [], Decimal(0), _tax_codes([vid(ln) for ln in lines if vid(ln)])
    code_list = []
    for ln in lines:
        qty, price = int(ln["quantity"]), Decimal(str(ln["unit_price"]))
        if qty <= 0 or price < 0:
            raise ValueError("Miqdor va narx musbat bo'lishi kerak.")
        subtotal += price * qty
        items.append({"name": ln["name"], "variant_label": None, "sku": ln.get("sku"), "quantity": qty, "unit_price": str(price), "line_total": str(price * qty), "refunded_quantity": 0})
        code_list.append(codes.get(vid(ln)))
    number, token = _next(MANUAL_SEQ, "NZM"), secrets.token_urlsafe(12)
    data = {"number": number, "token": token, "status": "completed", "channel": "manual", "issued_at": timezone.now().isoformat(), "refunded_at": None,
            "seller": {"name": brand_name(), "address": None, "phone": None}, "cashier": staff or None, "kassa": None, "shift": None,
            "items": items, "item_count": sum(i["quantity"] for i in items), "subtotal": str(subtotal), "discount": "0", "coins": "0", "delivery": "0",
            "total": str(subtotal), "currency": "UZS", "payment_method": payment_method, "payments": [{"method": payment_method, "amount": str(subtotal)}],
            "refunds": [], "returned": "0", "amount_tendered": None, "change": None,
            "customer": {"name": customer_name, "phone": customer_phone} if (customer_name or customer_phone) else None, "coins_earned": 0, "tier": None, "note": note}
    data = _decorate(data, ReceiptSettings.get(), code_list)
    return _store(data, number=number, token=token, source=ReceiptSource.MANUAL, kind=kind, customer_name=customer_name, customer_phone=customer_phone,
                  payment_method=payment_method, issued_at=timezone.now(), created_by=staff)


def public_view(receipt: Receipt) -> dict:
    """The snapshot as the customer may see it (first name, masked phone) + fiscal block."""
    from apps.pos.infrastructure.receipts import first_name, mask_phone

    data = dict(receipt.data)
    if data.get("customer"):
        data["customer"] = {"name": first_name(data["customer"].get("name")), "phone": mask_phone(data["customer"].get("phone"))}
    data["fiscal"] = {"number": receipt.fiscal_number, "sign": receipt.fiscal_sign, "terminal_id": receipt.fiscal_terminal_id, "url": receipt.fiscal_url,
                      "at": receipt.fiscalized_at.isoformat() if receipt.fiscalized_at else None} if receipt.status == ReceiptStatus.FISCALIZED else None
    return data
