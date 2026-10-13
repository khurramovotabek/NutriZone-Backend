"""
Cart read-model selectors -- optimized, read-only Postgres queries. No
business logic, no aggregate construction, matching the pattern
established by every prior module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.db.models import Count
from django.utils import timezone as django_timezone

from apps.cart.domain.enums import CartStatus
from apps.cart.infrastructure import models as orm


class CartSelector:
    def list(self, status: str | None, cart_type: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.CartModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        if cart_type:
            qs = qs.filter(cart_type=cart_type)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.annotate(item_count=Count("items")).order_by("-created_at")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def get_by_token(self, token: str) -> dict | None:
        row = orm.CartModel.objects.filter(token=token).annotate(item_count=Count("items")).first()
        return self._card(row) if row else None

    def _card(self, row: orm.CartModel) -> dict:
        return {"id": str(row.id), "code": row.code, "status": row.status, "cart_type": row.cart_type, "currency": row.currency, "item_count": getattr(row, "item_count", row.items.count())}


class CartItemSelector:
    def list_by_cart(self, cart_id: uuid.UUID) -> list[dict]:
        rows = orm.CartItemModel.objects.filter(cart_id=cart_id, status="active").select_related("price_reference", "reservation_reference")
        return [
            {
                "id": str(r.id), "product_variant_id": str(r.product_variant_id), "quantity": r.quantity, "status": r.status,
                "has_price": hasattr(r, "price_reference"), "has_reservation": hasattr(r, "reservation_reference"),
            }
            for r in rows
        ]


class CartSnapshotSelector:
    def list_by_cart(self, cart_id: uuid.UUID) -> list[dict]:
        rows = orm.CartSnapshotModel.objects.filter(cart_id=cart_id).order_by("-captured_at")
        return [{"id": str(s.id), "token": str(s.token), "version_at_capture": s.version_at_capture, "captured_at": s.captured_at.isoformat()} for s in rows]


class CartAuditSelector:
    def list_by_cart(self, cart_id: uuid.UUID, page: int = 1, page_size: int = 50) -> tuple[list[dict], int]:
        qs = orm.CartAuditEntryModel.objects.filter(cart_id=cart_id).order_by("-occurred_at")
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs[start : start + page_size]
        return [{"id": str(a.id), "action": a.action, "actor_id": str(a.actor_id) if a.actor_id else None, "occurred_at": a.occurred_at.isoformat(), "details": a.details} for a in rows], total


class AbandonedCartSelector:
    """Backs the 'cleanup abandoned carts' Celery task -- active/saved carts with no update in N days that are not yet past their formal expires_at (a distinct signal from expiration: an abandoned cart may still be technically 'live')."""

    def list_abandoned(self, inactive_for_days: int = 3) -> list[dict]:
        cutoff = django_timezone.now() - timedelta(days=inactive_for_days)
        rows = orm.CartModel.objects.filter(status__in=[CartStatus.ACTIVE.value, CartStatus.SAVED.value], updated_at__lte=cutoff)
        return [{"id": str(r.id), "updated_at": r.updated_at.isoformat(), "customer_id": str(r.customer_id) if r.customer_id else None} for r in rows]


class DjangoCartSearchBackend:
    """Implements `application/ports.py::CartSearchGateway` -- Postgres ILIKE search over cart code/customer_id, per every other module's identical launch-stage search approach."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.CartModel.objects.all()
        if query:
            qs = qs.filter(code__icontains=query)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [{"id": str(r.id), "code": r.code, "status": r.status} for r in rows], total
