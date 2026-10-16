import uuid
from decimal import Decimal

import pytest

from apps.payment.infrastructure.models import PaymentEvent, PaymentModel

pytestmark = pytest.mark.django_db


def test_every_status_change_is_kept():
    p = PaymentModel.objects.create(order_id=uuid.uuid4(), customer_id=uuid.uuid4(), amount=Decimal("150000"), currency="UZS", provider="payme", order_number="ORD-000777")
    p.status = "pending"
    p.provider_state = 1
    p.save()
    p.method = "uzcard"
    p.save()  # no status change -> no event
    p.status = "succeeded"
    p.provider_state = 2
    p.save()
    events = list(PaymentEvent.objects.filter(payment=p).values_list("from_status", "to_status", "provider_state"))
    assert events == [("", "created", None), ("created", "pending", 1), ("pending", "succeeded", 2)]
