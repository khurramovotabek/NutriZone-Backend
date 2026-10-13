from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone as django_timezone

from apps.chat.infrastructure.repositories import DjangoConversationRepository
from apps.chat.infrastructure.tasks import flag_stale_conversations, rebuild_chat_statistics, relay_outbox_events
from apps.chat.tests.factories import make_conversation

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCeleryTasks:
    def test_flag_stale_conversations_runs_without_error(self):
        assert isinstance(flag_stale_conversations(), int)

    def test_flag_stale_conversations_counts_seeded_stale_conversation(self):
        """Seeds a deliberately stale OPEN conversation and verifies the task actually counts it, not just runs without error."""
        conversation = make_conversation()
        repo = DjangoConversationRepository()
        repo.save(conversation)
        conversation.record_activity(django_timezone.now() - timedelta(days=30))
        repo.save(conversation)
        count = flag_stale_conversations()
        assert count >= 1

    def test_flag_stale_conversations_never_mutates_a_conversation(self):
        """Verifies the disclosed read-only design documented in Phase 2: this task must never change a Conversation's status, only report on it."""
        conversation = make_conversation()
        repo = DjangoConversationRepository()
        repo.save(conversation)
        flag_stale_conversations()
        fetched = repo.get_by_id(conversation.id)
        assert fetched.status.value == "open"

    def test_rebuild_chat_statistics_runs_without_error(self):
        assert rebuild_chat_statistics() == "ok"

    def test_relay_outbox_events_runs_without_error(self):
        result = relay_outbox_events()
        assert isinstance(result, dict)
