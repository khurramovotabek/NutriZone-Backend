from __future__ import annotations

from rest_framework import serializers


class CreatePaymentSerializer(serializers.Serializer):
    """Phase 10: only order_id and provider -- no amount, no currency, no total. The serializer's own field set is itself the financial-integrity guarantee: there is nothing here to tamper with."""

    order_id = serializers.UUIDField()
    provider = serializers.CharField(max_length=32, default="fake")


class PaymentWebhookSerializer(serializers.Serializer):
    """
    Phase 10b: represents provider callback data. Deliberately has NO
    payment_id/order_id/customer_id field -- the server resolves the
    Payment entirely from provider_reference (never a caller-chosen
    identifier). amount/currency are accepted only as values to
    VERIFY against the already-authoritative Payment, never to
    redefine it.
    """

    provider_reference = serializers.CharField(max_length=128)
    status = serializers.ChoiceField(choices=["succeeded", "failed"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3)
