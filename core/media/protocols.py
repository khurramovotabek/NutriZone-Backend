"""
Structural (`Protocol`) collaborator interfaces for `MediaPipeline`.

Every stage of the pipeline talks to one of these instead of a
concrete class, so each is independently swappable at the composition
root without touching `MediaPipeline` itself (Validation Report
Hardening §2: "all stages present as swappable Protocol collaborators").
`StorageWriter` is intentionally structural rather than nominal --
`core.storage.backends.MediaStorageBackend.save()` already matches
this shape byte-for-byte, so no adapter class is needed to bridge the
two (confirmed by inspection in the same validation report, §1).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VirusScanner(Protocol):
    def scan(self, content: bytes) -> bool:
        """Returns True if `content` is clean, False if it should be rejected."""
        ...


@runtime_checkable
class ImageOptimizer(Protocol):
    def optimize(self, content: bytes) -> bytes:
        """Re-encodes `content` in its own format, stripped/compressed."""
        ...

    def to_webp(self, content: bytes) -> bytes:
        """Produces a WebP-encoded copy of (optimized) image content."""
        ...

    def generate_thumbnails(self, content: bytes, sizes: dict[str, int]) -> dict[str, bytes]:
        """`sizes` maps a thumbnail name (e.g. "small") to its max pixel dimension; returns the same names mapped to encoded thumbnail bytes."""
        ...

    def read_dimensions(self, content: bytes) -> tuple[int, int]:
        """Returns (width_px, height_px)."""
        ...


@runtime_checkable
class StorageWriter(Protocol):
    def save(self, path: str, content: bytes) -> str:
        """Persists `content` at `path`, returns the (possibly backend-normalized) stored path."""
        ...
