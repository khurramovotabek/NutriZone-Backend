"""
Product page extras: `GET products/<slug>/extras` (bundle, trust, price history, watched variants),
`POST|DELETE products/price-watch/<variant_id>` ("tell me when it's cheaper") and
`GET|POST products/<slug>/questions` (Savol-javob). See infrastructure/pdp_extras.py, pricing/price_watch.py,
reviews/questions.py.
"""
from __future__ import annotations

import uuid

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.products.infrastructure import models as orm
from common.exceptions import ResourceNotFound, ValidationFailed
from common.responses import success_response
from common.utils.localization import resolve_locale
from core.ratelimit import ScopedRateLimitThrottle


class AskQuestionThrottle(ScopedRateLimitThrottle):
    scope = "products.questions"
    limit = 10
    window_seconds = 3600
    identifier_source = "user"


class PriceWatchThrottle(ScopedRateLimitThrottle):
    scope = "products.price_watch"
    limit = 60
    window_seconds = 3600
    identifier_source = "user"


def _published_product_id(slug: str):
    pid = orm.Product.objects.filter(translations__slug=slug, status="published").values_list("id", flat=True).first()
    if pid is None:
        raise ResourceNotFound("Product not found.")
    return pid


def _customer_id(request):
    user = getattr(request, "user", None)
    return user.id if user is not None and getattr(user, "is_authenticated", False) else None


class ProductExtrasView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        from apps.products.infrastructure.pdp_extras import extras

        product_id = _published_product_id(slug)
        locale = resolve_locale(request, explicit=request.query_params.get("filter[locale]"))
        return success_response(data=extras(product_id, customer_id=_customer_id(request), locale=locale))


class PriceWatchView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PriceWatchThrottle]

    def _variant(self, variant_id: str):
        try:
            vid = uuid.UUID(variant_id)
        except ValueError as exc:
            raise ValidationFailed("Invalid variant id.") from exc
        if not orm.ProductVariant.objects.filter(id=vid, status="active", product__status="published").exists():
            raise ResourceNotFound("Variant not found.")
        return vid

    def post(self, request, variant_id: str):
        from apps.pricing.infrastructure import price_watch

        vid = self._variant(variant_id)
        try:
            w = price_watch.watch(request.user.id, vid)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
        return success_response(data={"variant_id": str(vid), "watching": True, "baseline": str(w.baseline_amount)}, status_code=201)

    def delete(self, request, variant_id: str):
        from apps.pricing.infrastructure import price_watch

        vid = self._variant(variant_id)
        price_watch.unwatch(request.user.id, vid)
        return success_response(data={"variant_id": str(vid), "watching": False})


class ProductQuestionsView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "POST" else [AllowAny()]

    def get_throttles(self):
        return [AskQuestionThrottle()] if self.request.method == "POST" else []

    def get(self, request, slug: str):
        from apps.reviews.infrastructure import questions

        product_id = _published_product_id(slug)
        rows, total = questions.public(product_id, limit=min(int(request.query_params.get("limit", 20) or 20), 50))
        customer = _customer_id(request)
        return success_response(data={"items": rows, "total": total, "mine": questions.mine(product_id, customer) if customer else []})

    def post(self, request, slug: str):
        from apps.reviews.infrastructure import questions

        product_id = _published_product_id(slug)
        try:
            q = questions.ask(product_id, request.user.id, str(request.data.get("question") or ""))
        except questions.QuestionError as exc:
            raise ValidationFailed(str(exc)) from exc
        return success_response(data={"id": str(q.id), "question": q.question, "asked_at": q.created_at.isoformat()}, status_code=201)
