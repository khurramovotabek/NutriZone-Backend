"""
Base managers/querysets shared by every SoftDeleteModel subclass.

Kept minimal and framework-level only, per Django Implementation
Blueprint §5 -- no business filtering lives here.
"""
from __future__ import annotations

from django.db import models


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self) -> "SoftDeleteQuerySet":
        return self.filter(is_deleted=False)

    def dead(self) -> "SoftDeleteQuerySet":
        return self.filter(is_deleted=True)


class ActiveManager(models.Manager):
    """Default manager for SoftDeleteModel: excludes soft-deleted rows."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Unfiltered manager -- used for admin, audit, and data-recovery paths."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()
