"""
Media Pipeline data shapes.

Deliberately plain dataclasses, not Django models or domain entities --
`core.media` has zero coupling to any concrete `content`/`products`/
`reviews` model (Django Implementation Blueprint §5, Validation Report
Hardening §1: "Media Pipeline has zero coupling to a concrete content
app model"). Every bounded context that uploads media (Products,
Identity avatars, Reviews, Stores, Platform/Content admin) constructs
its own `MediaUploadRequest`, calls the shared `MediaPipeline`, and
maps the returned `ProcessedMedia` onto its own aggregate/entity --
never the other way around.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.media.enums import MediaType


@dataclass(frozen=True, slots=True)
class MediaUploadRequest:
    """One inbound upload, before any validation has run."""

    filename: str
    content: bytes
    mime_type: str
    media_type: MediaType


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    """
    Facts about the stored content. `checksum_sha256` is what makes
    storage content-addressed (see `paths.py::build_storage_path`) --
    two uploads with identical bytes always resolve to the same path,
    giving deduplication by construction. `width_px`/`height_px` are
    only ever populated for image uploads that ran through an
    `ImageOptimizer`; every other media type leaves them `None`.
    """

    size_bytes: int
    checksum_sha256: str
    width_px: int | None = None
    height_px: int | None = None


@dataclass(frozen=True, slots=True)
class ProcessedMedia:
    """
    The result of a successful `MediaPipeline.process()` call.

    `storage_path` always points at the persisted, optimized original
    (original format, not WebP). `has_webp_variant` tells the caller
    a WebP copy was generated *and stored* alongside it, at the
    deterministic path `build_storage_path(media_type, metadata.
    checksum_sha256, "webp")` -- callers that need that exact path
    (e.g. to record it on their own row) recompute it via
    `build_storage_path` rather than this dataclass carrying a
    redundant field, since it is fully determined by `media_type` +
    `checksum_sha256` (see `apps.identity.application.services.
    profile.UploadAvatar` for the concrete example). `thumbnail_paths`
    is empty for any non-image upload.
    """

    storage_path: str
    media_type: MediaType
    mime_type: str
    metadata: MediaMetadata
    has_webp_variant: bool = False
    thumbnail_paths: dict[str, str] = field(default_factory=dict)
