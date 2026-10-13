"""
Content-addressed storage path construction.
"""
from __future__ import annotations

from core.media.enums import MediaType


def build_storage_path(media_type: MediaType, content_hash: str, extension: str) -> str:
    """
    Deterministic, content-addressed storage path: two uploads with
    identical bytes (identical `content_hash`) always resolve to the
    same path, giving deduplication by construction -- no separate
    dedup lookup is ever needed. The `content_hash[:2]/content_hash[2:4]`
    two-level fan-out keeps any single directory from accumulating an
    unbounded number of entries as the media library grows.

    `extension` may itself carry a variant discriminator (e.g. a
    thumbnail's `"small.webp"`) so that a content-addressed original
    and its derived WebP/thumbnail variants share the same hash
    prefix while remaining distinct files.
    """
    ext = extension.lstrip(".")
    return f"{media_type.value}/{content_hash[:2]}/{content_hash[2:4]}/{content_hash}.{ext}"
