"""
Wishlist Application Services -- Add/Remove/List.

Deliberately no domain aggregate, no outbox event: a wishlist item is
a simple bookmark with no state machine and no other bounded context
needs to react to it (unlike Cart/Order/Review). Real, minimal
Application Service layer, matching this build's own established
composition-root/audit conventions.
"""
from __future__ import annotations

import uuid

from apps.products.application.services._shared import ProductServiceContext
from common.exceptions import ResourceNotFound


class AddToWishlist:
    def __init__(self, ctx: ProductServiceContext) -> None:
        self._ctx = ctx

    def execute(self, customer_id: uuid.UUID, product_id: uuid.UUID) -> dict:
        from apps.products.infrastructure.models import Product, WishlistItem

        if not Product.objects.filter(id=product_id).exists():
            raise ResourceNotFound("Product not found.")

        item, created = WishlistItem.objects.get_or_create(customer_id=customer_id, product_id=product_id)
        if created:
            self._ctx.audit().created(entity_type="WishlistItem", entity_id=str(item.id), after={"customer_id": str(customer_id), "product_id": str(product_id)})
        return {"id": str(item.id), "product_id": str(product_id), "created": created}


class RemoveFromWishlist:
    def __init__(self, ctx: ProductServiceContext) -> None:
        self._ctx = ctx

    def execute(self, customer_id: uuid.UUID, product_id: uuid.UUID) -> None:
        from apps.products.infrastructure.models import WishlistItem

        deleted, _ = WishlistItem.objects.filter(customer_id=customer_id, product_id=product_id).delete()
        if deleted:
            self._ctx.audit().deleted(entity_type="WishlistItem", entity_id=str(product_id), before={"customer_id": str(customer_id), "product_id": str(product_id)})


class ListWishlist:
    def execute(self, customer_id: uuid.UUID, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        from apps.products.domain.enums import ProductStatus
        from apps.products.infrastructure.models import WishlistItem
        from apps.products.infrastructure.selectors import _bulk_default_variant_prices, _bulk_rating_summary, _product_card

        qs = WishlistItem.objects.filter(customer_id=customer_id, product__status=ProductStatus.PUBLISHED.value).select_related("product").prefetch_related(
            "product__translations", "product__media", "product__variants"
        )
        total = qs.count()
        start = (page - 1) * page_size
        rows = list(qs[start : start + page_size])
        products = [r.product for r in rows]
        price_by_product_id = _bulk_default_variant_prices(products)
        rating_by_product_id = _bulk_rating_summary([p.id for p in products])
        cards = [
            {**_product_card(r.product, price_info=price_by_product_id.get(r.product_id), rating_info=rating_by_product_id.get(str(r.product_id))), "wishlisted_at": r.created_at.isoformat()}
            for r in rows
        ]
        return cards, total
