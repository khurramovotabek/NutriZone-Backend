from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone as django_timezone

from apps.platform.infrastructure.models import IdempotencyRecord, IdempotencyRecordStatus
from apps.platform.infrastructure.tasks import cleanup_expired_idempotency_records


@pytest.mark.django_db
class TestCleanupExpiredIdempotencyRecords:
    def test_deletes_only_expired_records(self):
        now = django_timezone.now()
        expired = IdempotencyRecord.objects.create(
            created_by=uuid.uuid4(), operation_scope="test.op", key="expired-key",
            request_fingerprint="fp", status=IdempotencyRecordStatus.COMPLETED, expires_at=now - timedelta(hours=1),
        )
        active = IdempotencyRecord.objects.create(
            created_by=uuid.uuid4(), operation_scope="test.op", key="active-key",
            request_fingerprint="fp", status=IdempotencyRecordStatus.COMPLETED, expires_at=now + timedelta(hours=1),
        )

        result = cleanup_expired_idempotency_records()

        assert result["deleted"] == 1
        assert not IdempotencyRecord.objects.filter(id=expired.id).exists()
        assert IdempotencyRecord.objects.filter(id=active.id).exists()

    def test_safe_to_run_with_nothing_to_clean(self):
        result = cleanup_expired_idempotency_records()
        assert result["deleted"] == 0
