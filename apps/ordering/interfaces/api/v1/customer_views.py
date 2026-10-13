"""
Customer self-service endpoints for one's own order (see infrastructure/after_sales.py):

  GET  /api/v1/orders/<number>/after-sales      what the customer can do now + their earlier requests
  POST /api/v1/orders/<number>/customer-cancel  {reason, comment}
  POST /api/v1/orders/<number>/customer-return  {reason, lines: [{order_line_item_id, quantity}], comment}

Strictly owner-only (staff use the dashboard), unlike the staff workflow endpoints in views.py.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from apps.ordering.infrastructure import after_sales
from apps.ordering.interfaces.api.v1.permissions import ViewAnyOrder, ViewOwnOrder
from apps.ordering.interfaces.api.v1.responses import success_response
from apps.ordering.interfaces.api.v1.views import OrderingThrottle, _actor_id, _attach_identity


class CustomerCancelSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=after_sales.CUSTOMER_CANCEL_REASONS, default="customer_request")
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class CustomerReturnLineSerializer(serializers.Serializer):
    order_line_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=1000)


class CustomerReturnSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=("defective", "wrong_item", "not_as_described", "damaged_in_transit", "changed_mind", "other"))
    lines = CustomerReturnLineSerializer(many=True, allow_empty=False)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class _OwnOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    def _order(self, request, number):
        _attach_identity(request)
        return after_sales.own_order(number, _actor_id(request))


class AfterSalesView(_OwnOrderView):
    @extend_schema(tags=["Customer Order Actions"], summary="What the customer can do with their order (cancel / return) and their earlier requests")
    def get(self, request, number: str):
        return success_response(data=after_sales.snapshot(self._order(request, number)))


class CustomerCancelView(_OwnOrderView):
    @extend_schema(tags=["Customer Order Actions"], summary="Cancel my order (instantly before packing, otherwise as a request)", request=CustomerCancelSerializer)
    def post(self, request, number: str):
        order = self._order(request, number)
        data = CustomerCancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        outcome = after_sales.cancel(order, _actor_id(request), data.validated_data["reason"], data.validated_data["comment"])
        order.refresh_from_db()
        return success_response(data={"outcome": outcome, **after_sales.snapshot(order)})


class CustomerReturnView(_OwnOrderView):
    @extend_schema(tags=["Customer Order Actions"], summary="Ask for a return of a delivered order", request=CustomerReturnSerializer)
    def post(self, request, number: str):
        order = self._order(request, number)
        data = CustomerReturnSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        lines = [{"order_line_item_id": str(l["order_line_item_id"]), "quantity": l["quantity"]} for l in data.validated_data["lines"]]
        number_ = after_sales.request_return(order, _actor_id(request), data.validated_data["reason"], lines, data.validated_data["comment"])
        return success_response(data={"return_number": number_, **after_sales.snapshot(order)}, status_code=201)


class ReplenishmentView(APIView):
    """`GET /orders/replenishment` -- my products predicted to run out within 30 days (soonest first), with the card to reorder."""

    throttle_classes = [OrderingThrottle]
    permission_classes = [ViewOwnOrder | ViewAnyOrder]
    HORIZON_DAYS = 30

    @extend_schema(tags=["Customer Order Actions"], summary="My products that will run out soon (reorder reminders)")
    def get(self, request):
        import uuid

        from apps.ordering.infrastructure.replenishment import forecasts
        from apps.products.infrastructure import models as p_orm
        from apps.products.infrastructure.selectors import _cards_with_price_and_rating
        from common.utils.localization import SUPPORTED_LOCALES

        _attach_identity(request)
        customer_id = _actor_id(request)
        if customer_id is None:
            return success_response(data=[])
        locale = request.query_params.get("filter[locale]")
        soon = sorted((f for f in forecasts([uuid.UUID(str(customer_id))]) if f.days_left() <= self.HORIZON_DAYS), key=lambda f: f.days_left())
        rows = {p.id: p for p in p_orm.Product.objects.filter(id__in=[f.product_id for f in soon], status="published").prefetch_related("translations", "media", "variants")}
        cards = {c["id"]: c for c in _cards_with_price_and_rating(list(rows.values()), locale if locale in SUPPORTED_LOCALES else None)}
        data = [
            {"product": cards[str(f.product_id)], "days_left": f.days_left(), "runs_out_at": f.runs_out_at.isoformat(), "last_purchased_at": f.last_at.isoformat(),
             "supply_days": f.supply_days, "basis": f.basis, "variant_id": str(f.variant_id) if f.variant_id else None}
            for f in soon if str(f.product_id) in cards
        ]
        return success_response(data=data)
