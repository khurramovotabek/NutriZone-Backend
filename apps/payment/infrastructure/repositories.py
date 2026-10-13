from __future__ import annotations

import uuid

from apps.payment.domain.aggregates import Payment
from apps.payment.domain.value_objects import PaymentAmount, PaymentStatus
from apps.payment.infrastructure.models import PaymentModel


class DjangoPaymentRepository:
    def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        row = PaymentModel.objects.filter(id=payment_id).first()
        return self._to_domain(row) if row else None

    def get_by_provider_reference(self, provider_reference: str) -> Payment | None:
        row = PaymentModel.objects.filter(provider_reference=provider_reference).first()
        return self._to_domain(row) if row else None

    def save(self, payment: Payment) -> Payment:
        PaymentModel.objects.update_or_create(
            id=payment.id,
            defaults={
                "order_id": payment.order_id,
                "customer_id": payment.customer_id,
                "amount": payment.amount.amount,
                "currency": payment.amount.currency,
                "provider": payment.provider,
                "status": payment.status.value,
                "provider_reference": payment.provider_reference,
                "failure_reason": payment.failure_reason,
            },
        )
        return payment

    @staticmethod
    def _to_domain(row: PaymentModel) -> Payment:
        return Payment(
            id=row.id, order_id=row.order_id, customer_id=row.customer_id,
            amount=PaymentAmount(amount=row.amount, currency=row.currency),
            provider=row.provider, status=PaymentStatus(row.status),
            provider_reference=row.provider_reference, failure_reason=row.failure_reason,
            created_at=row.created_at, updated_at=row.updated_at,
        )
