"""
Wishlist `/api/v1/wishlist` endpoints -- real customer-facing bookmark
list. IsAuthenticated only: a customer manages only their own
wishlist, resolved from `request.user.id`, never a client-supplied
customer_id.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.products.infrastructure import composition
from common.exceptions import ValidationFailed
from common.responses import paginated_response, success_response


class AddToWishlistSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()


class WishlistListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Wishlist"], summary="List the current customer's wishlist", responses={200: OpenApiResponse(description="Wishlist items")})
    def get(self, request):
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 20)), 100)
        items, total = composition.build_list_wishlist().execute(customer_id=request.user.id, page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return paginated_response(data=items, pagination={"strategy": "page", "page": page, "page_size": page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Wishlist"], summary="Add a product to the wishlist", request=AddToWishlistSerializer, responses={201: OpenApiResponse(description="Added"), 404: OpenApiResponse(description="Product not found")})
    def post(self, request):
        serializer = AddToWishlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = composition.build_add_to_wishlist(actor_id=request.user.id).execute(customer_id=request.user.id, product_id=serializer.validated_data["product_id"])
        return success_response(data=result, status_code=201)


class WishlistItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Wishlist"], summary="Remove a product from the wishlist", responses={204: OpenApiResponse(description="Removed")})
    def delete(self, request, product_id: str):
        try:
            product_uuid = uuid.UUID(product_id)
        except ValueError:
            raise ValidationFailed("Invalid product_id.")
        composition.build_remove_from_wishlist(actor_id=request.user.id).execute(customer_id=request.user.id, product_id=product_uuid)
        return success_response(data=None, status_code=204)
