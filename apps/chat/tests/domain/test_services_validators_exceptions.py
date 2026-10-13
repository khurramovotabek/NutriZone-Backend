from __future__ import annotations

import ast

import pytest

import apps.chat.domain.exceptions as exceptions_module
from apps.chat.domain import exceptions as exc
from apps.chat.domain.enums import AttachmentType, ConversationType, ParticipantRole
from apps.chat.domain.services import MessageEditPolicy, ParticipantPolicy
from apps.chat.domain.validators import AttachmentMetadataValidator, MessageContentValidator
from common.exceptions import DomainException

pytestmark = pytest.mark.unit


class TestMessageEditPolicy:
    """Hand-traced during Phase 1 (TEXT+SENT/EDITED editable, all else not); now made executable."""

    @pytest.mark.parametrize("status", ["sent", "edited"])
    def test_text_message_editable_statuses(self, status):
        assert MessageEditPolicy.can_edit("text", status) is True

    def test_text_message_deleted_not_editable(self):
        assert MessageEditPolicy.can_edit("text", "deleted") is False

    @pytest.mark.parametrize("status", ["sent", "edited", "deleted"])
    def test_attachment_message_never_editable(self, status):
        assert MessageEditPolicy.can_edit("attachment", status) is False

    @pytest.mark.parametrize("status", ["sent", "edited", "deleted"])
    def test_system_message_never_editable(self, status):
        assert MessageEditPolicy.can_edit("system", status) is False


class TestParticipantPolicy:
    """Hand-traced during Phase 1 (CUSTOMER blocked in INTERNAL_SUPPORT, OPERATOR allowed everywhere); now made executable against all real enum combinations."""

    def test_customer_blocked_in_internal_support(self):
        assert ParticipantPolicy.is_role_valid_for_conversation_type(ParticipantRole.CUSTOMER, ConversationType.INTERNAL_SUPPORT) is False

    def test_operator_allowed_in_internal_support(self):
        assert ParticipantPolicy.is_role_valid_for_conversation_type(ParticipantRole.OPERATOR, ConversationType.INTERNAL_SUPPORT) is True

    @pytest.mark.parametrize("conversation_type", [ConversationType.CUSTOMER_SALES, ConversationType.CUSTOMER_SUPPORT])
    def test_customer_allowed_in_customer_facing_types(self, conversation_type):
        assert ParticipantPolicy.is_role_valid_for_conversation_type(ParticipantRole.CUSTOMER, conversation_type) is True

    @pytest.mark.parametrize("conversation_type", [ConversationType.CUSTOMER_SALES, ConversationType.CUSTOMER_SUPPORT])
    def test_operator_allowed_in_customer_facing_types(self, conversation_type):
        assert ParticipantPolicy.is_role_valid_for_conversation_type(ParticipantRole.OPERATOR, conversation_type) is True


class TestValidators:
    def test_message_content_validator(self):
        assert MessageContentValidator("Hello").value == "Hello"

    def test_attachment_metadata_validator(self):
        meta = AttachmentMetadataValidator(AttachmentType.FILE, "https://example.com/f.pdf", "f.pdf", 2048)
        assert meta.size_bytes == 2048


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.InvalidConversationTransition, exc.ParticipantAlreadyExists, exc.ParticipantNotFound,
        exc.InvalidParticipantRole, exc.EmptyMessageContent, exc.MessageContentTooLong, exc.AttachmentRequired,
        exc.MessageEditNotAllowed, exc.MessageAlreadyDeleted, exc.MessageNotOwnedBySender,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_programmatically_verify_exactly_12_exceptions():
    """AST-parses exceptions.py directly, per this build's established pattern of verifying programmatically rather than trusting a hardcoded count."""
    tree = ast.parse(open(exceptions_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 12, f"Expected exactly 12 Chat domain exceptions (UnknownSticker with stickers, InvalidCardReference with product / order cards), found {len(class_names)}: {class_names}"
