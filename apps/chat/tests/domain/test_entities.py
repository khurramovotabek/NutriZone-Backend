from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.chat.domain.entities import Participant
from apps.chat.domain.enums import ParticipantRole

pytestmark = pytest.mark.unit


class TestParticipant:
    def test_valid_construction(self):
        participant = Participant(id=uuid.uuid4(), user_id=uuid.uuid4(), role=ParticipantRole.CUSTOMER, joined_at=datetime.utcnow())
        assert participant.role == ParticipantRole.CUSTOMER

    def test_is_active_true_by_default(self):
        participant = Participant(id=uuid.uuid4(), user_id=uuid.uuid4(), role=ParticipantRole.OPERATOR, joined_at=datetime.utcnow())
        assert participant.is_active is True

    def test_is_active_false_when_removed(self):
        participant = Participant(id=uuid.uuid4(), user_id=uuid.uuid4(), role=ParticipantRole.OPERATOR, joined_at=datetime.utcnow(), removed_at=datetime.utcnow())
        assert participant.is_active is False
