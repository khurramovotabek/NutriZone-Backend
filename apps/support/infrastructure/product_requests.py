"""
"Find this product for me": a customer describes a product the shop doesn't sell (name, brand, description, link,
photo); staff search for it and answer from the dashboard. Every change goes through here so the customer is
notified once per answer and staff hear about new requests on Telegram.
"""
from __future__ import annotations

import logging
from html import escape

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from apps.support.infrastructure.models import PRODUCT_REQUEST_OPEN, ProductRequest, ProductRequestStatus

logger = logging.getLogger("nutrizone.app")

MAX_OPEN_PER_CUSTOMER = 10
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
# status → notification kind (the customer hears about answers, not about "searching" alone unless staff wrote a reply)
NOTIFY_KIND = {"searching": "product_request_searching", "found": "product_request_found", "not_found": "product_request_not_found"}


class ProductRequestError(Exception):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _next_number() -> str:
    last = ProductRequest.objects.select_for_update().aggregate(m=Max("number"))["m"]
    n = int(last.split("-")[1]) + 1 if last and last.split("-")[1].isdigit() else 1
    return f"PR-{n:06d}"


def validate_image(upload) -> None:
    if upload is None:
        return
    if upload.size > MAX_IMAGE_BYTES:
        raise ProductRequestError("IMAGE_TOO_LARGE", "Rasm 5 MB dan oshmasin.")
    if (getattr(upload, "content_type", "") or "").lower() not in IMAGE_TYPES:
        raise ProductRequestError("IMAGE_TYPE", "Faqat JPG, PNG yoki WEBP rasm yuklang.")
    try:
        from PIL import Image

        upload.seek(0)
        Image.open(upload).verify()
        upload.seek(0)
    except Exception as exc:  # noqa: BLE001 - anything Pillow can't read is not an image
        raise ProductRequestError("IMAGE_INVALID", "Rasmni o'qib bo'lmadi — boshqa fayl tanlang.") from exc


@transaction.atomic
def create(customer_id, *, product_name: str, brand: str = "", description: str = "", url: str = "", quantity: int = 1, image=None) -> ProductRequest:
    name = (product_name or "").strip()
    if len(name) < 2:
        raise ProductRequestError("NAME_REQUIRED", "Mahsulot nomini yozing.")
    if ProductRequest.objects.filter(customer_id=customer_id, status__in=PRODUCT_REQUEST_OPEN).count() >= MAX_OPEN_PER_CUSTOMER:
        raise ProductRequestError("TOO_MANY_OPEN", f"Bir vaqtda {MAX_OPEN_PER_CUSTOMER} tadan ko'p ochiq so'rov bo'lmaydi — avvalgilariga javobni kuting.", 409)
    validate_image(image)
    row = ProductRequest(
        number=_next_number(), customer_id=customer_id, product_name=name[:200], brand=(brand or "").strip()[:120],
        description=(description or "").strip()[:2000], url=(url or "").strip()[:500], quantity=max(1, min(int(quantity or 1), 999)),
    )
    if image is not None:
        row.image = image
    row.save()
    transaction.on_commit(lambda: _alert_staff(row.pk))
    return row


@transaction.atomic
def cancel(customer_id, request_id) -> ProductRequest:
    row = ProductRequest.objects.select_for_update().filter(pk=request_id, customer_id=customer_id).first()
    if row is None:
        raise ProductRequestError("NOT_FOUND", "So'rov topilmadi.", 404)
    if row.status not in PRODUCT_REQUEST_OPEN:
        raise ProductRequestError("CLOSED", "Bu so'rov allaqachon yopilgan.", 409)
    row.status = ProductRequestStatus.CANCELLED
    row.save(update_fields=["status", "updated_at"])
    return row


def answer(row: ProductRequest, *, previous_status: str, previous_reply: str, staff: str) -> None:
    """Called after staff saved the request: stamps who/when and notifies the customer when the answer changed."""
    changed_status = row.status != previous_status
    changed_reply = (row.staff_reply or "").strip() != (previous_reply or "").strip()
    if not (changed_status or changed_reply):
        return
    updates = {"handled_by": staff[:150] or row.handled_by}
    if row.status in (ProductRequestStatus.FOUND, ProductRequestStatus.NOT_FOUND) or changed_reply:
        updates["answered_at"] = timezone.now()
    ProductRequest.objects.filter(pk=row.pk).update(**updates)
    kind = NOTIFY_KIND.get(row.status)
    if kind is None and changed_reply and row.status != ProductRequestStatus.CANCELLED:
        kind = "product_request_reply"
    if kind is None:
        return
    from apps.notifications.infrastructure.notify import notify

    reply = (row.staff_reply or "").strip()
    price = ("≈ " + f"{int(row.offered_price):,}".replace(",", " ") + " so'm") if row.offered_price else ""
    notify(row.customer_id, kind, {"number": row.number, "product": row.product_name, "reply": reply, "price": price},
           link="/account/product-requests", dedupe_key=f"preq:{row.pk}:{row.status}:{hash(reply) & 0xFFFFFF:x}")


def payload(row: ProductRequest) -> dict:
    """The customer's view of one request (no internal note, no staff name)."""
    offered = None
    if row.offered_product_id:
        from apps.products.infrastructure.models import ProductTranslation

        rows = {t["locale_code"]: t for t in ProductTranslation.objects.filter(product_id=row.offered_product_id).values("locale_code", "name", "slug")}
        tr = rows.get("uz") or next(iter(rows.values()), None)
        if tr:
            offered = {"id": str(row.offered_product_id), "name": tr["name"], "slug": tr["slug"]}
    return {
        "id": str(row.id), "number": row.number, "product_name": row.product_name, "brand": row.brand, "description": row.description,
        "url": row.url, "quantity": row.quantity, "status": row.status, "status_label": row.get_status_display(),
        "image_url": f"{settings.MEDIA_URL}{row.image.name}" if row.image else None,
        "staff_reply": row.staff_reply, "offered_price": str(row.offered_price) if row.offered_price is not None else None,
        "offered_product": offered, "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        "answered_at": row.answered_at.isoformat() if row.answered_at else None, "can_cancel": row.status in PRODUCT_REQUEST_OPEN,
    }


def open_count() -> int:
    return ProductRequest.objects.filter(status=ProductRequestStatus.NEW).count()


def _alert_staff(request_id) -> None:
    """New request → the analytics bot's recipients (owners), else the Orders bot's staff chat. Best effort."""
    row = ProductRequest.objects.select_related("customer").filter(pk=request_id).first()
    if row is None:
        return
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    link = f"{base}{reverse('admin:support_productrequest_change', args=[row.pk])}" if base else ""
    who = escape(row.customer.full_name or row.customer.phone_number or "Mijoz")
    lines = [f"🔎 <b>Yangi mahsulot so'rovi {row.number}</b>", f"<b>{escape(row.product_name)}</b>" + (f" · {escape(row.brand)}" if row.brand else ""),
             f"Mijoz: {who} · {row.quantity} dona"]
    if row.description:
        lines.append(escape(row.description[:300]))
    if row.url:
        lines.append(escape(row.url[:200]))
    text = "\n".join(lines)
    keyboard = [[{"text": "Dashboard'da ochish", "url": link}]] if link.startswith("https://") else None
    try:
        from apps.telegram_bot.infrastructure import analytics_bot

        if analytics_bot.is_configured():
            for chat in analytics_bot.recipients():
                try:
                    analytics_bot.send(chat, text, keyboard)
                except Exception:  # noqa: BLE001
                    logger.exception("product request alert to %s failed", analytics_bot.mask_chat(chat))
            return
        chat = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
        if chat:
            from apps.notifications.infrastructure import composition

            composition.build_orders_telegram_gateway().send_message_with_keyboard(str(chat), text, keyboard or [])
    except Exception:  # noqa: BLE001 - an alert must never break the customer's request
        logger.exception("product request %s: staff alert failed", row.number)
