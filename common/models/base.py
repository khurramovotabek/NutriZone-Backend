"""
Base model mixins.

Every model in every bounded-context app composes from exactly one of the
three mixins below, per Django Implementation Blueprint §5 and the model
category rules in the Universal Module Implementation Contract §3.

    BaseModel        -> Entity / Reference / Lookup / Configuration tables
    SoftDeleteModel   -> BaseModel + soft-delete (the default for
                          business-record-facing tables)
    AppendOnlyModel   -> Ledger / History / Audit / Snapshot tables:
                          insert-only, structurally forbidden to update
                          or (soft- or hard-) delete once written.

No business model classes live here. This module contains only the
reusable, framework-level shape defined in the Enterprise Database
Blueprint §3 (Global Base Entity Standard).
"""
from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models.managers import ActiveManager, AllObjectsManager


class TimestampedMixin(models.Model):
    """created_at / updated_at, present on every table without exception."""

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class ActorTrackedMixin(models.Model):
    """
    created_by / updated_by.

    Nullable by design (Database Blueprint §3): system/seed-inserted rows
    and unauthenticated-flow writes (e.g. a guest cart) legitimately have
    no actor. Population is handled by common/middleware/audit_context.py
    at the request boundary -- application-layer code should not set these
    fields manually except in tests/fixtures/management commands.
    """

    created_by = models.UUIDField(null=True, blank=True, editable=False)
    updated_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True


class OptimisticLockMixin(models.Model):
    """
    version -- optimistic locking token (Database Blueprint §10).

    This is the *default* concurrency-control mechanism for ordinary
    entities. It is explicitly NOT sufficient for Inventory stock
    mutation or Wallet ledger writes, which require pessimistic
    row-level locking instead (see the module docstring and the
    Database Blueprint §10 Locking Strategy table) -- pessimistic
    locking is applied at the repository/application-service layer via
    `select_for_update()`, not encoded here.
    """

    version = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and not kwargs.get("force_insert"):
            self.version = (self.version or 0) + 1
        super().save(*args, **kwargs)


class SoftDeleteMixin(models.Model):
    """
    is_deleted / deleted_at / deleted_by.

    `.delete()` on a SoftDeleteModel subclass ALWAYS performs a soft
    delete. A genuine hard delete requires the explicit `.hard_delete()`
    call below -- this asymmetry is deliberate (Database Blueprint §12):
    hard deletion must always be a conscious, distinct action, never the
    accidental default.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def delete(self, *args: Any, using: str | None = None, actor_id: uuid.UUID | None = None, **kwargs: Any) -> tuple[int, dict[str, int]]:
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = actor_id
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])
        return (1, {self._meta.label: 1})

    def hard_delete(self, *args: Any, using: str | None = None, **kwargs: Any) -> tuple[int, dict[str, int]]:
        return super().delete(*args, using=using, **kwargs)  # type: ignore[misc]


class BaseModel(TimestampedMixin, ActorTrackedMixin, OptimisticLockMixin, models.Model):
    """
    The universal base entity (Database Blueprint §3), minus soft delete.

    Use directly for Lookup/Reference/Configuration tables that are
    genuinely hard-deleted (no soft-delete history value). Most
    business-record-facing tables should use SoftDeleteModel instead.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    objects = AllObjectsManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<{self.__class__.__name__} id={self.id}>"


class SoftDeleteModel(BaseModel, SoftDeleteMixin):
    """
    Entity / Reference table default (MIC §3).

    `objects` is soft-delete-aware and filters `is_deleted=False` by
    default; `all_objects` exposes the unfiltered queryset for admin /
    audit / data-recovery use cases where deleted rows must be visible.
    """

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AppendOnlyModel(models.Model):
    """
    Ledger / History / Audit / Snapshot table base (MIC §3).

    Structurally insert-only: `id` + `created_at` + `created_by` only --
    no `updated_at`, no `version`, no soft-delete fields, because those
    columns would be permanently-null dead weight on a table that is
    never updated (Database Blueprint §3).

    This is the Python-level half of the invariant the Database Blueprint
    enforces at the DB level via `trg_<table>_no_update` /
    `trg_<table>_no_delete` triggers (Database Blueprint §4.8) -- calling
    `.save()` on an existing row or `.delete()` at all raises here, so a
    violation is caught in application code before it ever reaches the
    database trigger.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    created_by = models.UUIDField(null=True, blank=True, editable=False)

    objects = AllObjectsManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and self.__class__.objects.filter(pk=self.pk).exists():
            raise AppendOnlyViolation(
                f"{self.__class__.__name__} is append-only: "
                f"row {self.pk} already exists and may not be updated."
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AppendOnlyViolation(
            f"{self.__class__.__name__} is append-only: rows may never be deleted."
        )


class AppendOnlyViolation(RuntimeError):
    """Raised when code attempts to update or delete an append-only row."""
