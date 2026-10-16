"""`GET /api/v1/receipts/{token}` -- the public e-receipt behind a receipt's QR code (no login: the unguessable token is the key)."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

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
