"""
Telegram catalog + cart service -- Phase 15C.

Every operation here delegates to the exact same application services
the web storefront already uses (confirmed via direct reconnaissance
of apps/products and apps/cart) -- Telegram is an interface, not a
second backend, per this phase's own explicit architectural rule.

Cart ownership is token-based, not customer_id-based (a confirmed,
pre-existing architectural fact from Phase 09.2) -- Telegram has no
cookie to persist this across stateless webhook requests, so the
cart_id/cart_token pair is stored on the User row itself, exactly
mirroring what the web storefront's own HttpOnly cookie does.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from common.exceptions import ResourceNotFound

logger = logging.getLogger("nutrizone.telegram_bot")

_BEST_SELLERS_LIMIT = 20  # A real, bounded "top N" leaderboard -- not a substitute for paginating the full catalog, matching list_best_sellers()'s own intended semantics.

_BROWSE_SOURCES = ("best", "new", "all", "sale", "brand", "category", "search", "product")


class TelegramCatalogService:
    def list_categories(self, locale: str = "uz") -> list[dict]:
        from apps.products.infrastructure import models as products_orm

        categories = products_orm.Category.objects.filter(is_active=True).prefetch_related("translations").order_by("sort_order")
        result = []
        for cat in categories:
            translation = next((t for t in cat.translations.all() if t.locale_code == locale), None) or next((t for t in cat.translations.all() if t.locale_code == "uz"), None)
            result.append({"id": str(cat.id), "name": translation.name if translation else str(cat.id)})
        return result

    def list_products(self, category_id: uuid.UUID | None = None, brand_id: uuid.UUID | None = None, page: int = 1, page_size: int = 5) -> tuple[list[dict], int]:
        from apps.products.infrastructure.selectors import CatalogSelector

        return CatalogSelector().list(category_id=category_id, brand_id=brand_id, page=page, page_size=page_size)

    def get_product(self, product_id: uuid.UUID, locale: str = "uz") -> dict | None:
        from apps.products.infrastructure.selectors import ProductDetailSelector

        return ProductDetailSelector().get_by_id(product_id, locale=locale)

    def list_brands(self, locale: str = "uz") -> list[dict]:
        from apps.products.infrastructure.selectors import BrandSelector

        return BrandSelector().list_active(locale=locale)

    def get_brand_name(self, brand_id: uuid.UUID, locale: str = "uz") -> str | None:
        brand = next((b for b in self.list_brands(locale=locale) if b["id"] == str(brand_id)), None)
        return brand["name"] if brand else None

    def browse(
        self, source: str, page: int = 1, locale: str = "uz", brand_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None,
        query: str | None = None, rating_gte: int | None = None, price_min: int | None = None, price_max: int | None = None,
        product_id: uuid.UUID | None = None,
    ) -> tuple[dict | None, int]:
        """
        The single entry point behind every "one product, one message,
        paginated" screen (Best Sellers / Newest / All Products / a
        Brand's products / a Category's products) -- always re-fetches
        the current page fresh from the same real selectors the website
        uses, so a paginated browse session can never show stale price/
        stock. Returns `(None, total)` for an out-of-range page (e.g. a
        filter just made the list shorter) rather than raising, so the
        caller can clamp/re-render instead of crashing on a stale page
        number.
        """
        from apps.products.infrastructure.selectors import CatalogSelector

        if source not in _BROWSE_SOURCES:
            raise ValueError(f"Unknown browse source '{source}'.")

        if source == "best":
            # Real, bounded "top N" list (list_best_sellers has no page
            # param of its own) -- paginated in-memory across that
            # already-small, already-fetched top-N, never the full catalog.
            items = self.list_best_sellers_cards(limit=_BEST_SELLERS_LIMIT, locale=locale)
            total = len(items)
            index = page - 1
            product = items[index] if 0 <= index < total else None
            return (self.enrich(product) if product else None), total

        if source == "product":  # one product opened from a link (inline result / shared deep link)
            product = self.get_product(product_id, locale=locale) if product_id else None
            return (self.enrich(product) if product else None), (1 if product else 0)

        # Every other screen goes through the website's own catalog engine (catalog_browse): the same smart search
        # (typos, Latin/Cyrillic, synonyms, goals) for a typed query, and the same real brand / category / price /
        # rating filters as the storefront -- newest first when browsing, by relevance when searching.
        from apps.products.infrastructure.selectors import DjangoProductSearchBackend

        filters: dict = {}
        if brand_id:
            filters["brand_ids"] = [str(brand_id)]
        if category_id:
            filters["category_id"] = str(category_id)
        if rating_gte:
            filters["rating_gte"] = str(rating_gte)
        if price_min is not None or price_max is not None:
            filters["price"] = {k: str(v) for k, v in (("gte", price_min), ("lte", price_max)) if v is not None}
        if source == "sale":  # promotions: products with a real old price above today's price, biggest saving first
            filters["on_sale"] = True
        searching = source == "search"
        sort = "relevance" if searching else "-discount" if source == "sale" else "-created_at"
        found = DjangoProductSearchBackend().search((query or "") if searching else "", filters, page, 1, sort, locale)
        product = found["results"][0] if found["results"] else None
        return (self.enrich(product) if product else None), found["total_count"]

    def list_best_sellers_cards(self, limit: int = _BEST_SELLERS_LIMIT, locale: str | None = None) -> list[dict]:
        from apps.products.infrastructure.selectors import CatalogSelector

        return CatalogSelector().list_best_sellers(limit=limit, locale=locale)

    @staticmethod
    def enrich(product: dict) -> dict:
        """
        Adds `brand_name`/`weight_value`/`weight_unit`/`available_quantity` to a
        catalog-list-shaped card -- reuses the exact same, already-real,
        already-tested `ProductDetailSelector.get_pos_display_info` the
        POS terminal already relies on for the identical "brand name +
        variant weight + real inventory count" need, rather than a
        second, bot-only aggregation. Only ever called for the single
        product a browse page is currently showing, never batched across
        a list -- one extra query per navigation action, not an N+1.
        """
        from apps.products.infrastructure.selectors import ProductDetailSelector

        info = ProductDetailSelector().get_pos_display_info([uuid.UUID(product["id"])]).get(product["id"], {})
        return {**product, **info}


class OrderNotOwnedByCustomer(Exception):
    """Raised when the resolved order does not belong to the requesting customer -- an IDOR guard, never a client-trusted check."""


class TelegramOrderService:
    def list_my_orders(self, customer_id: uuid.UUID, page: int = 1, page_size: int = 5) -> tuple[list[dict], int]:
        from apps.ordering.infrastructure.selectors import OrderSelector

        return OrderSelector().list(status=None, customer_id=customer_id, page=page, page_size=page_size)

    def get_order_detail(self, order_number: str, customer_id: uuid.UUID) -> dict:
        """
        Reuses the exact same `LoadOrder` Application Service and real
        Order aggregate the website's own `OrderDetailView` reads (see
        `apps.ordering.interfaces.api.v1.views._load_order_by_number`) --
        never a second, divergent order-detail read path. Ownership is
        re-checked here exactly like that view's own
        `_require_order_ownership_or_staff` (customer-only, never a
        client-supplied id treated as sufficient authorization) --
        raises `ResourceNotFound` for an unknown order number and
        `OrderNotOwnedByCustomer` for one that exists but belongs to a
        different customer, so the caller can tell "not found" from
        "not yours" apart if it ever needs to.
        """
        from apps.ordering.infrastructure import composition as ordering_composition

        order = ordering_composition.build_load_order().execute(order_number=order_number)
        if order.customer_id != customer_id:
            raise OrderNotOwnedByCustomer("This order does not belong to the requesting customer.")

        lines = []
        for line in order.lines.values():
            lines.append({
                "product_variant_id": str(line.product_variant_id),
                "quantity": line.quantity,
                "line_total_amount": str(line.line_total().amount),
                "currency": line.line_total().currency,
            })
        total = order.compute_total().grand_total
        address = order.shipping_address
        return {
            "order_number": order.order_number.value,
            "status": order.status.value,
            "lines": lines,
            "total_amount": str(total.amount),
            "currency": total.currency,
            "address": {
                "line1": address.line1, "line2": address.line2, "city": address.city, "region": address.region,
            } if address else None,
        }


class TelegramWishlistService:
    """Thin adapter over the exact same real `AddToWishlist`/`RemoveFromWishlist`/`ListWishlist` Application Services the website's own `/api/v1/wishlist` endpoints use -- no second, bot-only wishlist concept."""

    def is_wishlisted(self, customer_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        from apps.products.infrastructure.models import WishlistItem

        return WishlistItem.objects.filter(customer_id=customer_id, product_id=product_id).exists()

    def toggle(self, customer_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        """Returns the new wishlisted state (True if now wishlisted, False if just removed)."""
        from apps.products.infrastructure import composition as products_composition

        if self.is_wishlisted(customer_id, product_id):
            products_composition.build_remove_from_wishlist(actor_id=customer_id).execute(customer_id=customer_id, product_id=product_id)
            return False
        products_composition.build_add_to_wishlist(actor_id=customer_id).execute(customer_id=customer_id, product_id=product_id)
        return True


class TelegramCartService:
    """
    All cart mutations resolve the Telegram customer's own cart via
    `telegram_cart_id`/`telegram_cart_token` on their User row --
    never trusts a cart/item ID supplied in callback data as
    sufficient authorization by itself; every operation re-loads the
    cart via the stored token (the same ownership boundary
    `_load_cart_by_code` enforces for the web storefront) before
    acting on it.
    """

    def _get_or_create_cart(self, user) -> tuple:
        from django.db import transaction

        from apps.cart.infrastructure import composition as cart_composition

        if user.telegram_cart_id:
            cart = cart_composition.build_cart_repository().get_by_id(user.telegram_cart_id)
            # A cart that was checked out / archived / left locked can't take new items -- start a fresh one.
            if cart is not None and str(cart.token.value) == str(user.telegram_cart_token) and cart.status.value == "active" and cart.lock_reason is None:
                return cart, user

        # Phase 15I: shared transaction -- without it, a failure in user.save()
        # after build_create_cart had already committed (a separately-atomic
        # service) would leave a real, orphaned Cart with no User ever linked to it.
        with transaction.atomic():
            cart = cart_composition.build_create_cart(user.id).execute(currency="UZS", cart_type="authenticated", source="web")
            user.telegram_cart_id = cart.id
            user.telegram_cart_token = cart.token.value
            user.save(update_fields=["telegram_cart_id", "telegram_cart_token"])
        return cart, user

    def _load_owned_cart(self, user):
        from apps.cart.infrastructure import composition as cart_composition

        if not user.telegram_cart_id:
            raise ResourceNotFound("No cart yet.")
        cart = cart_composition.build_cart_repository().get_by_id(user.telegram_cart_id)
        if cart is None or str(cart.token.value) != str(user.telegram_cart_token):
            raise ResourceNotFound("Cart not found.")
        return cart

    def add_item(self, user, product_variant_id: uuid.UUID, quantity: int = 1) -> dict:
        from django.db import transaction

        from apps.cart.infrastructure import composition as cart_composition
        from apps.pricing.infrastructure import composition as pricing_composition

        cart, user = self._get_or_create_cart(user)

        # Phase 15I: shared transaction across all three service calls --
        # found via reconnaissance that this was the same class of bug
        # already confirmed and fixed twice this session (Phase 09.7c,
        # Phase 15H). Without this, a failure in build_attach_price_snapshot
        # would leave a real, committed cart item with no price attached,
        # and a real, committed PriceSnapshot issued but never used.
        with transaction.atomic():
            updated = cart_composition.build_add_item(user.id).execute(cart_id=cart.id, product_variant_id=product_variant_id, quantity=quantity)
            # add_item() merges into an existing line for the same variant rather than
            # always appending a new one (confirmed via Cart.add_item()'s own domain
            # code) -- so the correct item is found by product_variant_id, not by
            # assuming dict insertion order.
            new_item = next(i for i in updated.items.values() if i.product_variant_id == product_variant_id)

            snapshot = pricing_composition.build_issue_variant_price_snapshot(user.id).execute(product_variant_id=product_variant_id, quantity=quantity, coupon_code=None, region=None)
            priced = cart_composition.build_attach_price_snapshot(user.id).execute(
                cart_id=updated.id, item_id=new_item.id, price_snapshot_id=snapshot.id, unit_amount=snapshot.locked_price.amount, currency=snapshot.locked_price.currency,
            )
        return self._cart_payload(priced)

    def view_cart(self, user) -> dict:
        cart = self._load_owned_cart(user)
        return self._cart_payload(self._price_missing(user, cart))

    def _price_missing(self, user, cart):
        """The cart is shared with the Mini App: a line added there before sign-in has no price yet -- lock today's
        price for it here, one line at a time (a line with no active price just stays "price pending")."""
        from apps.cart.domain.enums import CartItemStatus
        from apps.cart.infrastructure import composition as cart_composition
        from apps.pricing.infrastructure import composition as pricing_composition

        for item in [i for i in cart.items.values() if i.status != CartItemStatus.REMOVED and i.price_reference is None]:
            try:
                snapshot = pricing_composition.build_issue_variant_price_snapshot(user.id).execute(product_variant_id=item.product_variant_id, quantity=item.quantity.value, coupon_code=None, region=None)
                cart = cart_composition.build_attach_price_snapshot(user.id).execute(
                    cart_id=cart.id, item_id=item.id, price_snapshot_id=snapshot.id, unit_amount=snapshot.locked_price.amount, currency=snapshot.locked_price.currency,
                )
            except Exception:  # noqa: BLE001
                logger.info("telegram cart: line %s could not be priced", item.id)
        return cart

    def update_quantity(self, user, item_id: uuid.UUID, quantity: int) -> dict:
        from apps.cart.infrastructure import composition as cart_composition

        cart = self._load_owned_cart(user)
        if item_id not in cart.items:
            raise ResourceNotFound("Item not found in your cart.")
        updated = cart_composition.build_update_quantity(user.id).execute(cart_id=cart.id, item_id=item_id, quantity=quantity)
        return self._cart_payload(updated)

    def remove_item(self, user, item_id: uuid.UUID) -> dict:
        from apps.cart.infrastructure import composition as cart_composition

        cart = self._load_owned_cart(user)
        if item_id not in cart.items:
            raise ResourceNotFound("Item not found in your cart.")
        updated = cart_composition.build_remove_item(user.id).execute(cart_id=cart.id, item_id=item_id)
        return self._cart_payload(updated)

    @staticmethod
    def _cart_payload(cart) -> dict:
        from apps.cart.domain.enums import CartItemStatus

        items = []
        total = Decimal("0")
        currency = None
        for item in cart.items.values():
            if item.status == CartItemStatus.REMOVED:
                continue
            entry = {"id": str(item.id), "product_variant_id": str(item.product_variant_id), "quantity": item.quantity.value, "priced": item.price_reference is not None}
            if item.price_reference is not None:
                entry["unit_amount"] = str(item.price_reference.unit_amount.amount)
                entry["currency"] = item.price_reference.unit_amount.currency
                total += item.price_reference.unit_amount.amount * item.quantity.value
                currency = item.price_reference.unit_amount.currency
            items.append(entry)
        return {"cart_id": str(cart.id), "items": items, "total": str(total), "currency": currency or "UZS"}
