from __future__ import annotations

from celery import shared_task


@shared_task(queue="default", name="receipts.fiscalize", autoretry_for=(), max_retries=0)
def fiscalize_receipt(receipt_id: str) -> str:
    from apps.receipts.infrastructure import fiscal
    from apps.receipts.infrastructure.models import Receipt

    r = Receipt.objects.filter(pk=receipt_id).first()
    if r is None:
        return "missing"
    try:
        fiscal.fiscalize(r)
        return "ok"
    except fiscal.FiscalError as exc:
        return f"failed: {exc}"
