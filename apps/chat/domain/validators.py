"""
Chat domain validators -- thin, intention-revealing wrappers over
value object constructors, matching every prior module's
domain/validators.py pattern.
"""
from __future__ import annotations

from apps.chat.domain.enums import AttachmentType
from apps.chat.domain.value_objects import AttachmentMetadata, MessageContent


def MessageContentValidator(value: str) -> MessageContent:  # noqa: N802
    return MessageContent(value)


def AttachmentMetadataValidator(attachment_type: AttachmentType, url: str, filename: str, size_bytes: int) -> AttachmentMetadata:  # noqa: N802
    return AttachmentMetadata(attachment_type=attachment_type, url=url, filename=filename, size_bytes=size_bytes)
