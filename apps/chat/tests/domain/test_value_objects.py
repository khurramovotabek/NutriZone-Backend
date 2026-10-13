from __future__ import annotations

import pytest

from apps.chat.domain.enums import AttachmentType
from apps.chat.domain.exceptions import EmptyMessageContent, MessageContentTooLong
from apps.chat.domain.value_objects import MAX_CONTENT_LENGTH, AttachmentMetadata, ConversationVersion, MessageContent, MessageVersion
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestMessageContent:
    def test_valid_construction(self):
        assert MessageContent("Hello!").value == "Hello!"

    def test_rejects_empty_string_with_specific_exception(self):
        with pytest.raises(EmptyMessageContent):
            MessageContent("")

    def test_rejects_whitespace_only_with_specific_exception(self):
        with pytest.raises(EmptyMessageContent):
            MessageContent("   ")

    def test_rejects_too_long_with_specific_exception(self):
        with pytest.raises(MessageContentTooLong):
            MessageContent("x" * (MAX_CONTENT_LENGTH + 1))

    def test_exactly_max_length_allowed(self):
        MessageContent("x" * MAX_CONTENT_LENGTH)

    def test_immutability(self):
        content = MessageContent("Hi")
        with pytest.raises(Exception):
            content.value = "Changed"  # type: ignore[misc]


class TestAttachmentMetadata:
    def test_valid_construction(self):
        meta = AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="https://example.com/a.jpg", filename="a.jpg", size_bytes=1024)
        assert meta.size_bytes == 1024

    def test_rejects_empty_url(self):
        with pytest.raises(ValidationFailed):
            AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="", filename="a.jpg", size_bytes=1024)

    def test_rejects_empty_filename(self):
        with pytest.raises(ValidationFailed):
            AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="https://example.com/a.jpg", filename="", size_bytes=1024)

    def test_rejects_non_positive_size(self):
        with pytest.raises(ValidationFailed):
            AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="https://example.com/a.jpg", filename="a.jpg", size_bytes=0)


class TestConversationVersion:
    def test_rejects_zero(self):
        with pytest.raises(ValidationFailed):
            ConversationVersion(0)

    def test_next_increments(self):
        assert ConversationVersion(1).next().value == 2


class TestMessageVersion:
    def test_rejects_zero(self):
        with pytest.raises(ValidationFailed):
            MessageVersion(0)

    def test_next_increments(self):
        assert MessageVersion(1).next().value == 2
