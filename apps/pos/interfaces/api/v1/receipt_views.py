"""`GET /api/v1/receipts/{token}` -- the public e-receipt behind a receipt's QR code (no login: the unguessable token is the key)."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.pos.infrastructure import receipts
from common.exceptions import ResourceNotFound
from common.responses import success_response


class PublicReceiptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(tags=["Receipts"], summary="Public e-receipt by its QR token")
    def get(self, request, token: str):
        from apps.receipts.infrastructure.builders import public_view
        from apps.receipts.infrastructure.models import Receipt

        registered = Receipt.objects.filter(token=token).first() if token and len(token) <= 32 else None
        if registered is not None and registered.source != "pos":  # online order / manual receipt (frozen snapshot + fiscal block)
            return success_response(data=public_view(registered))
        sale = receipts.by_token(token)
        if sale is None:
            raise ResourceNotFound("Receipt not found.")
        locale = (request.query_params.get("locale") or "uz")[:2]
        data = receipts.receipt(sale, locale=locale, public=True)
        if registered is not None:  # live POS data + the registry's fiscal block / seller requisites
            extra = public_view(registered)
            data.update(fiscal=extra.get("fiscal"), requisites=extra.get("requisites"), vat=extra.get("vat"), footer=extra.get("footer"))
        return success_response(data=data)


class MyReceiptsView(APIView):
    """`GET /api/v1/receipts/mine` -- every receipt the signed-in customer got: online orders, shop purchases (the
    kassa linked them, or the receipt carries their phone) and manual receipts; newest first."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Receipts"], summary="My receipts")
    def get(self, request):
        from django.db.models import Q

        from apps.identity.infrastructure.models import User
        from apps.ordering.infrastructure.models import OrderModel
        from apps.pos.infrastructure.models import SaleModel
        from apps.receipts.infrastructure.models import Receipt
        from apps.stores.infrastructure.models import Store

        uid = request.user.id
        phone = User.objects.filter(pk=uid).values_list("phone_number", flat=True).first() or ""
        match = Q(order_id__in=OrderModel.objects.filter(customer_id=uid).values("id")) | Q(sale_id__in=SaleModel.objects.filter(customer_id=uid).values("id"))
        if phone:
            match |= Q(customer_phone=phone)
        rows = list(Receipt.objects.filter(match).exclude(status="cancelled").order_by("-issued_at")[:100])
        stores = dict(Store.objects.filter(id__in={r.store_id for r in rows if r.store_id}).values_list("id", "name"))
        return success_response(data=[{
            "number": r.number, "token": r.token, "source": r.source, "kind": r.kind, "status": r.status,
            "total": str(r.total), "vat": str(r.vat_amount), "payment_method": r.payment_method, "issued_at": r.issued_at.isoformat(),
            "order_number": r.order_number, "store": stores.get(r.store_id, ""), "items": (r.data or {}).get("item_count") or len((r.data or {}).get("items") or []),
            "fiscal": bool(r.fiscal_number), "fiscal_url": r.fiscal_url,
        } for r in rows])
