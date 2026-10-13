"""
Cart repository.

Concrete implementation of application/ports.py's `CartRepository`
Protocol -- maps ORM rows to the single `Cart` domain aggregate only,
never leaks ORM objects outside this module, matching the pattern
established by every prior module.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError

from apps.cart.domain.aggregates import Cart
from apps.cart.domain.entities import (
    CartAuditEntry, CartItem, CartSnapshot, InventoryReservationReference, PriceReference,
    ShippingEstimateReference, TaxEstimateReference,
)
from apps.cart.domain.enums import CartItemStatus, CartLockReason, CartSource, CartStatus, CartType
from apps.cart.domain.value_objects import (
    CartCode, CartToken, CartVersion, ChannelCode, CurrencyCode, EstimatedAmount, GiftMessage, CartNote,
    Money, Quantity, RegionCode, SnapshotToken,
)
from apps.cart.infrastructure import models as orm
from common.exceptions import ConflictError


class DjangoCartRepository:
    def get_by_id(self, cart_id: uuid.UUID) -> Cart | None:
        row = orm.CartModel.objects.filter(id=cart_id).prefetch_related(
            "items__price_reference", "items__reservation_reference", "snapshots", "audit_entries"
        ).first()
        return self._to_domain(row) if row else None

    def get_by_code(self, code: str) -> Cart | None:
        """Added during Phase 3 (Interfaces) -- see application/ports.py::CartRepository.get_by_code's docstring."""
        row = orm.CartModel.objects.filter(code=code).prefetch_related(
            "items__price_reference", "items__reservation_reference", "snapshots", "audit_entries"
        ).first()
        return self._to_domain(row) if row else None

    def get_by_token(self, token: str) -> Cart | None:
        row = orm.CartModel.objects.filter(token=token).prefetch_related(
            "items__price_reference", "items__reservation_reference", "snapshots", "audit_entries"
        ).first()
        return self._to_domain(row) if row else None

    def get_active_for_customer(self, customer_id: uuid.UUID) -> Cart | None:
        row = orm.CartModel.objects.filter(customer_id=customer_id, status=CartStatus.ACTIVE.value).prefetch_related(
            "items__price_reference", "items__reservation_reference", "snapshots", "audit_entries"
        ).first()
        return self._to_domain(row) if row else None

    def save(self, cart: Cart) -> Cart:
        try:
            row, _ = orm.CartModel.objects.update_or_create(
                id=cart.id,
                defaults={
                    "code": cart.code.value, "token": cart.token.value, "version": cart.version.value, "currency": cart.currency.value,
                    "cart_type": cart.cart_type.value, "source": cart.source.value, "status": cart.status.value,
                    "region": cart.region.value if cart.region else None, "channel": cart.channel.value if cart.channel else None,
                    "customer_id": cart.customer_id, "coupon_ids": [str(c) for c in cart.coupon_ids], "promotion_ids": [str(p) for p in cart.promotion_ids],
                    "note": cart.note.text if cart.note else None, "gift_message": cart.gift_message.text if cart.gift_message else None,
                    "expires_at": cart.expires_at, "lock_reason": cart.lock_reason.value if cart.lock_reason else None,
                    "shipping_estimate_id": cart.shipping_estimate.shipping_estimate_id if cart.shipping_estimate else None,
                    "shipping_estimated_amount": cart.shipping_estimate.estimated_amount.amount.amount if cart.shipping_estimate else None,
                    "shipping_estimated_currency": cart.shipping_estimate.estimated_amount.amount.currency if cart.shipping_estimate else None,
                    "shipping_estimate_is_final": cart.shipping_estimate.estimated_amount.is_final if cart.shipping_estimate else False,
                    "shipping_estimated_at": cart.shipping_estimate.estimated_at if cart.shipping_estimate else None,
                    "tax_estimate_id": cart.tax_estimate.tax_estimate_id if cart.tax_estimate else None,
                    "tax_estimated_amount": cart.tax_estimate.estimated_amount.amount.amount if cart.tax_estimate else None,
                    "tax_estimated_currency": cart.tax_estimate.estimated_amount.amount.currency if cart.tax_estimate else None,
                    "tax_estimate_is_final": cart.tax_estimate.estimated_amount.is_final if cart.tax_estimate else False,
                    "tax_estimated_at": cart.tax_estimate.estimated_at if cart.tax_estimate else None,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A cart with conflicting unique fields already exists.") from exc

        existing_item_ids = set(row.items.values_list("id", flat=True))
        for item in cart.items.values():
            item_row, _ = orm.CartItemModel.objects.update_or_create(
                id=item.id,
                defaults={"cart": row, "product_variant_id": item.product_variant_id, "quantity": item.quantity.value, "status": item.status.value, "note": item.note.text if item.note else None, "added_at": item.added_at},
            )
            if item.price_reference is not None:
                orm.PriceSnapshotReferenceModel.objects.update_or_create(
                    item=item_row, defaults={"price_snapshot_id": item.price_reference.price_snapshot_id, "unit_amount": item.price_reference.unit_amount.amount, "currency": item.price_reference.unit_amount.currency, "applied_at": item.price_reference.applied_at},
                )
            else:
                orm.PriceSnapshotReferenceModel.objects.filter(item=item_row).delete()

            if item.reservation_reference is not None:
                orm.AttachedReservationModel.objects.update_or_create(
                    item=item_row, defaults={"reservation_id": item.reservation_reference.reservation_id, "reserved_at": item.reservation_reference.reserved_at, "expires_at": item.reservation_reference.expires_at},
                )
            else:
                orm.AttachedReservationModel.objects.filter(item=item_row).delete()

        stale_item_ids = existing_item_ids - set(cart.items.keys())
        if stale_item_ids:
            orm.CartItemModel.objects.filter(id__in=stale_item_ids).delete()

        existing_snapshot_ids = set(row.snapshots.values_list("id", flat=True))
        for snapshot in cart.snapshots.values():
            if snapshot.id not in existing_snapshot_ids:
                orm.CartSnapshotModel.objects.create(id=snapshot.id, cart=row, token=snapshot.token.value, version_at_capture=snapshot.version_at_capture, captured_at=snapshot.captured_at, items_snapshot=list(snapshot.items_snapshot))
        stale_snapshot_ids = existing_snapshot_ids - set(cart.snapshots.keys())
        if stale_snapshot_ids:
            orm.CartSnapshotModel.objects.filter(id__in=stale_snapshot_ids).delete()

        existing_audit_ids = set(row.audit_entries.values_list("id", flat=True))
        for entry in cart.audit_log:
            if entry.id not in existing_audit_ids:
                orm.CartAuditEntryModel.objects.create(id=entry.id, cart=row, action=entry.action, actor_id=entry.actor_id, occurred_at=entry.occurred_at, details=entry.details)

        return cart

    def delete(self, cart_id: uuid.UUID) -> None:
        row = orm.CartModel.objects.filter(id=cart_id).first()
        if row:
            row.delete()

    def list_for_customer(self, customer_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Cart], int]:
        qs = orm.CartModel.objects.filter(customer_id=customer_id)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self.get_by_id(r.id) for r in rows], total

    def list_expiring_before(self, at: datetime) -> list[Cart]:
        rows = orm.CartModel.objects.filter(status__in=[CartStatus.ACTIVE.value, CartStatus.SAVED.value], expires_at__isnull=False, expires_at__lte=at)
        return [self.get_by_id(r.id) for r in rows]

    def list_for_admin(self, status: str | None, cart_type: str | None, page: int, page_size: int) -> tuple[list[Cart], int]:
        qs = orm.CartModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        if cart_type:
            qs = qs.filter(cart_type=cart_type)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self.get_by_id(r.id) for r in rows], total

    def _to_domain(self, row: orm.CartModel) -> Cart:
        items: dict[uuid.UUID, CartItem] = {}
        for item_row in row.items.all():
            price_reference = None
            price_ref_row = getattr(item_row, "price_reference", None)
            if price_ref_row is not None:
                price_reference = PriceReference(price_snapshot_id=price_ref_row.price_snapshot_id, unit_amount=Money(amount=price_ref_row.unit_amount, currency=price_ref_row.currency), applied_at=price_ref_row.applied_at)

            reservation_reference = None
            reservation_row = getattr(item_row, "reservation_reference", None)
            if reservation_row is not None:
                reservation_reference = InventoryReservationReference(reservation_id=reservation_row.reservation_id, reserved_at=reservation_row.reserved_at, expires_at=reservation_row.expires_at)

            items[item_row.id] = CartItem(
                id=item_row.id, product_variant_id=item_row.product_variant_id, quantity=Quantity(item_row.quantity), status=CartItemStatus(item_row.status),
                price_reference=price_reference, reservation_reference=reservation_reference, note=CartNote(item_row.note) if item_row.note else None, added_at=item_row.added_at,
            )

        snapshots = {
            s.id: CartSnapshot(id=s.id, token=SnapshotToken(s.token), version_at_capture=s.version_at_capture, captured_at=s.captured_at, items_snapshot=tuple(s.items_snapshot))
            for s in row.snapshots.all()
        }
        audit_log = [CartAuditEntry(id=a.id, action=a.action, actor_id=a.actor_id, occurred_at=a.occurred_at, details=a.details) for a in row.audit_entries.all()]

        shipping_estimate = None
        if row.shipping_estimate_id is not None:
            shipping_estimate = ShippingEstimateReference(
                shipping_estimate_id=row.shipping_estimate_id,
                estimated_amount=EstimatedAmount(amount=Money(amount=row.shipping_estimated_amount, currency=row.shipping_estimated_currency), is_final=row.shipping_estimate_is_final),
                estimated_at=row.shipping_estimated_at,
            )
        tax_estimate = None
        if row.tax_estimate_id is not None:
            tax_estimate = TaxEstimateReference(
                tax_estimate_id=row.tax_estimate_id,
                estimated_amount=EstimatedAmount(amount=Money(amount=row.tax_estimated_amount, currency=row.tax_estimated_currency), is_final=row.tax_estimate_is_final),
                estimated_at=row.tax_estimated_at,
            )

        return Cart(
            id=row.id, code=CartCode(row.code), token=CartToken(row.token), currency=CurrencyCode(row.currency),
            cart_type=CartType(row.cart_type), source=CartSource(row.source), status=CartStatus(row.status),
            version=CartVersion(row.version), region=RegionCode(row.region) if row.region else None,
            channel=ChannelCode(row.channel) if row.channel else None, customer_id=row.customer_id,
            items=items, coupon_ids=set(uuid.UUID(c) for c in row.coupon_ids), promotion_ids=set(uuid.UUID(p) for p in row.promotion_ids),
            shipping_estimate=shipping_estimate, tax_estimate=tax_estimate,
            note=CartNote(row.note) if row.note else None, gift_message=GiftMessage(row.gift_message) if row.gift_message else None,
            expires_at=row.expires_at, lock_reason=CartLockReason(row.lock_reason) if row.lock_reason else None,
            snapshots=snapshots, audit_log=audit_log,
        )
