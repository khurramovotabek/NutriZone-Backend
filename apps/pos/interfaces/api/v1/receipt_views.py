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
        sale = receipts.by_token(token)
        if sale is None:
            raise ResourceNotFound("Receipt not found.")
        locale = (request.query_params.get("locale") or "uz")[:2]
        return success_response(data=receipts.receipt(sale, locale=locale, public=True))
