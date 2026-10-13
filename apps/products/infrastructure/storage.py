"""
Concrete `StorageGateway` (application/ports.py) for this module.

Deliberately thin: `core.storage.get_storage_backend()` (Foundation
phase) already provides a fully-implemented, environment-configured
`MediaStorageBackend` (local disk in development, object storage in
production) -- this file's only job is satisfying `application/
ports.py::StorageGateway`'s Protocol shape for Products' own
composition root without Products reaching into `core.storage`
directly from `application/` (which would violate "application depends
only on ports," Django Implementation Blueprint §4). Every other
module needing storage (Identity's avatar upload, Foundation
Hardening's Media Pipeline itself) uses the exact same underlying
`core.storage` backend -- there is deliberately no
Products-specific storage behavior here.
"""
from __future__ import annotations

from core.storage import get_storage_backend


class ProductStorageGateway:
    def __init__(self) -> None:
        self._backend = get_storage_backend()

    def save(self, path: str, content: bytes) -> str:
        return self._backend.save(path, content)
