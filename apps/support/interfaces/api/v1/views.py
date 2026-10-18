"""
`/api/v1/product-requests` -- "find this product for me" for signed-in customers.

    GET    product-requests             my requests, newest first
    POST   product-requests             multipart: product_name*, brand, description, url, quantity, image
    POST   product-requests/<id>/cancel cancel an open request
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.support.infrastructure import product_requests as svc
from apps.support.infrastructure.models import ProductRequest
from common.responses import error_response, success_response
from core.ratelimit import ScopedRateLimitThrottle


class ProductRequestCreateThrottle(ScopedRateLimitThrottle):
    scope = "support.product_request"
    limit = 10
    window_seconds = 3600
    identifier_source = "user"


def _error(exc: svc.ProductRequestError):
    category = "validation" if exc.status == 422 else "conflict" if exc.status == 409 else "business"
    return error_response(exc.code, exc.message, category, exc.status)


class MyProductRequestsView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_throttles(self):
        return [ProductRequestCreateThrottle()] if self.request.method == "POST" else []

    @extend_schema(tags=["Support"], summary="My product requests")
    def get(self, request):
        rows = ProductRequest.objects.filter(customer_id=request.user.id).select_related("offered_product")[:100]
        return success_response(data=[svc.payload(r) for r in rows])

    @extend_schema(tags=["Support"], summary="Ask the shop to find a product")
    def post(self, request):
        data = request.data
        url = (data.get("url") or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        if len(url) > 500:
            return error_response("URL_TOO_LONG", "Havola juda uzun.", "validation", 422)
        if url:
            from django.core.exceptions import ValidationError
            from django.core.validators import URLValidator

            try:
                URLValidator(schemes=["http", "https"])(url)
            except ValidationError:
                return error_response("URL_INVALID", "Havola noto'g'ri — to'liq manzilni kiriting (https://…).", "validation", 422)
        try:
            quantity = int(data.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        try:
            row = svc.create(request.user.id, product_name=data.get("product_name", ""), brand=data.get("brand", ""), description=data.get("description", ""),
                             url=url, quantity=quantity, image=request.FILES.get("image"))
        except svc.ProductRequestError as exc:
            return _error(exc)
        return success_response(data=svc.payload(row), status_code=201)


class CancelProductRequestView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Support"], summary="Cancel my product request")
    def post(self, request, request_id: uuid.UUID):
        try:
            row = svc.cancel(request.user.id, request_id)
        except svc.ProductRequestError as exc:
            return _error(exc)
        return success_response(data=svc.payload(row))
