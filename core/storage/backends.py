"""
Media storage abstraction (Django Implementation Blueprint §10).

Selected via a single settings flag (`NUTRIZONE_STORAGE_BACKEND`), never
a code branch scattered through business logic. `get_delivery_url()`
already checks a CDN URL first, falling back to a direct/signed storage
URL -- this is the mechanism that makes the future CDN migration
(Enterprise Database Blueprint §14) a config + backfill change, not a
code change.
"""
from __future__ import annotations

import abc
import os
from pathlib import Path


class MediaStorageBackend(abc.ABC):
    @abc.abstractmethod
    def save(self, path: str, content: bytes) -> str:
        """Persist content, return the storage_path recorded on media_library."""

    @abc.abstractmethod
    def read(self, storage_path: str) -> bytes:
        ...

    @abc.abstractmethod
    def delete(self, storage_path: str) -> None:
        ...

    def get_delivery_url(self, storage_path: str, cdn_url: str | None = None) -> str:
        """CDN URL takes priority once populated (Database Blueprint §14)."""
        if cdn_url:
            return cdn_url
        return self._direct_url(storage_path)

    @abc.abstractmethod
    def _direct_url(self, storage_path: str) -> str:
        ...


class LocalDiskBackend(MediaStorageBackend):
    """Development-only backend, writes under the repository's media/ root."""

    def __init__(self, root: str | os.PathLike[str], base_url: str = "/media/") -> None:
        self.root = Path(root)
        self.base_url = base_url

    def save(self, path: str, content: bytes) -> str:
        full_path = self.root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return path

    def read(self, storage_path: str) -> bytes:
        return (self.root / storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        target = self.root / storage_path
        if target.exists():
            target.unlink()

    def _direct_url(self, storage_path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{storage_path}"


class ObjectStorageBackend(MediaStorageBackend):
    """
    Production backend (S3-compatible object storage).

    Implementation deferred until `content` (Domain Architecture
    Specification §2.17) is actually built -- this class defines the
    contract now so the interface is stable, per this document's scope
    (infrastructure only, no business modules). Concrete S3 client
    wiring happens in the `content` app's implementation.
    """

    def __init__(self, bucket: str, endpoint_url: str | None = None) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url

    def save(self, path: str, content: bytes) -> str:  # pragma: no cover - implemented with `content` app
        raise NotImplementedError("ObjectStorageBackend is wired when the `content` module is implemented.")

    def read(self, storage_path: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    def delete(self, storage_path: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def _direct_url(self, storage_path: str) -> str:  # pragma: no cover
        raise NotImplementedError


def get_storage_backend() -> MediaStorageBackend:
    """Resolves the active backend from Django settings."""
    from django.conf import settings

    backend_name = getattr(settings, "NUTRIZONE_STORAGE_BACKEND", "local")
    if backend_name == "local":
        return LocalDiskBackend(root=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
    if backend_name == "object_storage":
        return ObjectStorageBackend(
            bucket=settings.NUTRIZONE_OBJECT_STORAGE_BUCKET,
            endpoint_url=getattr(settings, "NUTRIZONE_OBJECT_STORAGE_ENDPOINT", None),
        )
    raise ValueError(f"Unknown storage backend: {backend_name}")
