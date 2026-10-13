from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.chat.infrastructure import models as orm
from apps.chat.infrastructure.health import (
    check_chat_cache,
    check_chat_outbox_backlog,
    check_chat_repository,
    check_composition_integrity,
    check_message_content_integrity,
    check_orphaned_participants,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_chat_repository_healthy(self):
        ok, detail = check_chat_repository()
        assert ok is True

    def test_check_chat_outbox_backlog_reports_count(self):
        ok, detail = check_chat_outbox_backlog()
        assert ok is True
        assert "pending" in detail

    def test_check_orphaned_participants_healthy_by_default(self):
        ok, detail = check_orphaned_participants()
        assert ok is True

    def test_check_message_content_integrity_healthy_by_default(self):
        ok, detail = check_message_content_integrity()
        assert ok is True

    def test_check_message_content_integrity_flags_seeded_bad_row(self):
        """Seeds a deliberately invalid TEXT message with NULL content (bypassing the aggregate's own EmptyMessageContent check) and verifies the health check actually catches it, not just runs without error."""
        orm.MessageModel.objects.create(conversation_id=uuid.uuid4(), sender_id=uuid.uuid4(), message_type="text", content=None, created_at=datetime.utcnow())
        ok, detail = check_message_content_integrity()
        assert ok is False

    def test_check_composition_integrity_healthy(self):
        ok, detail = check_composition_integrity()
        assert ok is True

    def test_check_chat_cache_round_trips(self):
        ok, detail = check_chat_cache()
        assert ok is True
