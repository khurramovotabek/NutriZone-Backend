"""
Daily payment reconciliation: does what the providers say, what our payments say and what the orders
say still agree? Every discrepancy becomes a PaymentReconciliationIssue (one per problem, keyed by
`dedupe_key`); when a later run no longer sees it, the issue closes itself.

Internal checks (all providers):
  paid_not_confirmed     money captured, order still waiting for payment
  paid_order_closed      money captured, order cancelled/returned and nothing refunded  → refund needed
  double_payment         two captured payments for one order                           → refund one
  amount_mismatch        captured amount ≠ what the order costs now (lines removed later)
  missing_order_ref      captured payment not recorded on the order
  stuck_at_provider      a provider transaction left half-way (Payme/Uzum state 1 > 13 h, Click prepared > 2 h)
  auth_errors            many auth/signature failures in 24 h (wrong key in the cabinet, or someone probing)

External check (Click Merchant API, when merchant_user_id is set):
  provider_paid_only     Click says paid, we don't
  we_paid_only           we say paid, Click doesn't
  provider_unreachable   Click's API couldn't be asked (informational)

Payme has no merchant-side statement API: Payme itself reconciles by calling our GetStatement, which
serves exactly the transactions stored here, so the internal checks cover our side of that comparison.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from apps.payment.infrastructure import service
from apps.payment.infrastructure.models import (
    PaymentCallbackLog,
    PaymentModel,
    PaymentReconciliationIssue,
    PaymentSettings,
    PaymentStatusChoices,
    ReconciliationStatus,
)
from apps.payment.infrastructure.providers import registry

logger = logging.getLogger("nutrizone.app")

CLICK_API = "https://api.click.uz/v2/merchant"
AUTH_ERROR_CODES = {"payme": -32504, "click": -1, "uzum": 10001}
AUTH_ERROR_THRESHOLD = 5

KINDS = {
    "paid_not_confirmed": ("critical", "To'langan, lekin buyurtma tasdiqlanmagan", "Buyurtmani tasdiqlang yoki holatini tekshiring."),
    "paid_order_closed": ("critical", "To'langan buyurtma bekor qilingan", "Mijozga pulni qaytaring (provayder kabineti orqali)."),
    "double_payment": ("critical", "Buyurtma ikki marta to'langan", "Ortiqcha to'lovni mijozga qaytaring."),
    "amount_mismatch": ("warning", "To'lov summasi buyurtmadan farq qiladi", "Buyurtma o'zgargan bo'lsa, farqni qaytaring."),
    "missing_order_ref": ("warning", "To'lov buyurtmaga yozilmagan", "Buyurtma kartasini tekshiring."),
    "stuck_at_provider": ("warning", "Tranzaksiya provayderda yarim yo'lda qolgan", "Provayder kabinetida holatini tekshiring."),
    "auth_errors": ("warning", "Ko'p imzo/kalit xatolari", "Kabinetdagi kalit bilan dashboard'dagi kalit mosligini tekshiring."),
    "provider_paid_only": ("critical", "Provayderda to'langan, bizda yo'q", "Callback yetib kelmagan — buyurtmani qo'lda tasdiqlang yoki provayder bilan bog'laning."),
    "we_paid_only": ("critical", "Bizda to'langan, provayderda yo'q", "Provayder kabinetida to'lovni tekshiring."),
    "provider_unreachable": ("info", "Provayder API javob bermadi", "Keyingi tekshiruvda qayta urinib ko'riladi."),
}


class _Collector:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.counts: dict[str, int] = {}

    def add(self, kind: str, key: str, *, payment: PaymentModel | None = None, order_number: str = "", provider: str = "", amount=None, **details) -> None:
        dedupe = f"{kind}:{key}"[:160]
        self.seen.add(dedupe)
        self.counts[kind] = self.counts.get(kind, 0) + 1
        severity = KINDS[kind][0]
        issue, created = PaymentReconciliationIssue.objects.get_or_create(
            dedupe_key=dedupe,
            defaults={"kind": kind, "severity": severity, "payment": payment, "order_number": order_number or (payment.order_number if payment else ""),
                      "provider": provider or (payment.provider if payment else ""), "amount": amount, "details": details},
        )
        if not created:
            issue.details = details
            if issue.status == ReconciliationStatus.RESOLVED and issue.resolved_by_id is None:
                issue.status, issue.resolved_at = ReconciliationStatus.OPEN, None  # came back after an automatic close
            issue.save(update_fields=["details", "status", "resolved_at", "last_seen_at"])


def run(now=None, external: bool = True) -> dict:
    now = now or timezone.now()
    c = _Collector()
    o = service._orders()
    paid = PaymentModel.objects.filter(status=PaymentStatusChoices.SUCCEEDED).exclude(provider="cash")

    orders = {x.id: x for x in o.OrderModel.objects.filter(id__in=paid.values("order_id")).only("id", "order_number", "status", "currency")}
    refs = set(o.OrderPaymentReferenceModel.objects.filter(payment_id__in=paid.values("id"), status__in=("captured", "refunded")).values_list("payment_id", flat=True))
    for p in paid:
        order = orders.get(p.order_id)
        if order is None:
            continue
        if order.status == "pending_payment":
            c.add("paid_not_confirmed", str(p.pk), payment=p, amount=p.amount)
        if order.status in service.CLOSED_ORDER_STATUSES:
            c.add("paid_order_closed", str(p.pk), payment=p, amount=p.amount, order_status=order.status)
        elif order.status != "pending_payment":
            due = service.payable(order)
            if due != p.amount and not order_has_multiple_paid(p.order_id):
                c.add("amount_mismatch", str(p.pk), payment=p, amount=p.amount - due, paid=str(p.amount), due=str(due))
        if p.pk not in refs:
            c.add("missing_order_ref", str(p.pk), payment=p, amount=p.amount)

    for row in paid.values("order_id", "order_number").annotate(n=Count("id")).filter(n__gt=1):
        extra = paid.filter(order_id=row["order_id"]).order_by("paid_at")
        c.add("double_payment", str(row["order_id"]), payment=extra.last(), order_number=row["order_number"],
              amount=sum((x.amount for x in list(extra)[1:]), Decimal(0)), payments=[str(x.pk) for x in extra])

    for p in PaymentModel.objects.filter(status=PaymentStatusChoices.PENDING, provider_state=1):
        limit = timedelta(hours=2) if p.provider == "click" else timedelta(hours=13)
        if now - p.updated_at > limit:
            c.add("stuck_at_provider", str(p.pk), payment=p, amount=p.amount, since=p.updated_at.isoformat())

    day = now - timedelta(days=1)
    for provider, code in AUTH_ERROR_CODES.items():
        n = PaymentCallbackLog.objects.filter(provider=provider, created_at__gte=day, error_code=code).count()
        if n >= AUTH_ERROR_THRESHOLD:
            c.add("auth_errors", f"{provider}:{timezone.localdate(now).isoformat()}", provider=provider, count=n)

    checked_external = _click_external(c, now) if external else 0

    # Anything not seen this run is fixed: close it automatically (manual resolutions are kept as they are).
    closed = PaymentReconciliationIssue.objects.filter(status=ReconciliationStatus.OPEN).exclude(dedupe_key__in=c.seen).update(
        status=ReconciliationStatus.RESOLVED, resolved_at=now, resolution_note="Avtomatik: keyingi tekshiruvda muammo topilmadi"
    )
    summary = {"at": now.isoformat(), "checked": paid.count(), "external": checked_external, "found": c.counts, "auto_closed": closed,
               "open": PaymentReconciliationIssue.objects.filter(status=ReconciliationStatus.OPEN).count()}
    cfg = PaymentSettings.load()
    cfg.last_reconciled_at, cfg.last_reconcile_summary = now, summary
    cfg.save(update_fields=["last_reconciled_at", "last_reconcile_summary", "updated_at"])
    return summary


def order_has_multiple_paid(order_id) -> bool:
    return PaymentModel.objects.filter(order_id=order_id, status=PaymentStatusChoices.SUCCEEDED).count() > 1


# ---------------------------------------------------------------- Click Merchant API


def click_get(state: registry.ProviderState, path: str) -> dict:
    """GET on Click's Merchant API. Auth header: merchant_user_id:sha1(timestamp + secret_key):timestamp."""
    ts = str(int(time.time()))
    digest = hashlib.sha1((ts + state.value("secret_key")).encode()).hexdigest()  # noqa: S324 - Click's documented scheme
    req = urllib.request.Request(f"{CLICK_API}{path}", headers={"Accept": "application/json", "Content-Type": "application/json", "Auth": f"{state.value('merchant_user_id')}:{digest}:{ts}"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode() or "{}")


def _click_external(c: _Collector, now) -> int:
    state = registry.load("click")
    if state.status != "active" or not state.value("merchant_user_id") or state.test_mode:
        return 0
    service_id = state.value("service_id")
    since = now - timedelta(days=2)
    checked = 0
    for p in PaymentModel.objects.filter(provider="click", created_at__gte=since).exclude(provider_reference__isnull=True):
        day = timezone.localdate(p.created_at).isoformat()
        try:
            found = click_get(state, f"/payment/status_by_mti/{service_id}/{p.order_number}/{day}")
            status = None
            if int(found.get("error_code", -1)) == 0 and found.get("payment_id"):
                status = click_get(state, f"/payment/status/{service_id}/{found['payment_id']}").get("payment_status")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            c.add("provider_unreachable", f"click:{timezone.localdate(now).isoformat()}", provider="click", error=str(exc)[:200])
            break
        checked += 1
        provider_paid = status is not None and int(status) == 2  # Click: 2 = payment succeeded
        if provider_paid and p.status != PaymentStatusChoices.SUCCEEDED:
            c.add("provider_paid_only", str(p.pk), payment=p, amount=p.amount, click_status=status)
        elif p.status == PaymentStatusChoices.SUCCEEDED and not provider_paid:
            c.add("we_paid_only", str(p.pk), payment=p, amount=p.amount, click_status=status)
    return checked
