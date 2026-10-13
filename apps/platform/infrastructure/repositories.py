"""
apps/platform/infrastructure/repositories.py

Database Blueprint §4.18. No ORM exception leaks past this layer
(matches Identity audit's own §17 requirement, applied here from the
first commit rather than retrofitted).
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError

from apps.platform.domain.aggregates import FeatureFlag
from apps.platform.infrastructure import models as orm
from common.exceptions import ConflictError


class DjangoFeatureFlagRepository:
    def get_by_id(self, flag_id: uuid.UUID) -> FeatureFlag | None:
        row = orm.FeatureFlagModel.objects.filter(id=flag_id).first()
        return self._to_domain(row) if row else None

    def get_by_key(self, key: str) -> FeatureFlag | None:
        row = orm.FeatureFlagModel.objects.filter(key=key).first()
        return self._to_domain(row) if row else None

    def list_all(self) -> list[FeatureFlag]:
        return [self._to_domain(row) for row in orm.FeatureFlagModel.objects.all()]

    def save(self, flag: FeatureFlag) -> FeatureFlag:
        try:
            row, _ = orm.FeatureFlagModel.objects.update_or_create(
                id=flag.id,
                defaults={
                    "key": flag.key, "is_globally_enabled": flag.is_globally_enabled,
                    "rollout_percentage": flag.rollout_percentage, "rollout_scope": flag.rollout_scope,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A feature flag with this key already exists.") from exc
        return self._to_domain(row)

    @staticmethod
    def _to_domain(row: orm.FeatureFlagModel) -> FeatureFlag:
        return FeatureFlag(id=row.id, key=row.key, is_globally_enabled=row.is_globally_enabled, rollout_percentage=row.rollout_percentage, rollout_scope=row.rollout_scope)
