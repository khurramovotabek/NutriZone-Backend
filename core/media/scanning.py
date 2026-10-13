"""
Virus-scan collaborators.
"""
from __future__ import annotations


class NoOpVirusScanner:
    """
    Foundation-phase default `VirusScanner` -- always reports uploaded
    content as clean. This is a deliberate, explicitly-flagged
    placeholder, not a security control: a real scanner (a ClamAV
    daemon over its `INSTREAM` protocol, a cloud AV API, ...) plugs in
    later by implementing the same `scan(content: bytes) -> bool`
    contract and swapping this out at each composition root (e.g.
    `apps.products.infrastructure.composition.build_media_pipeline`)
    -- no change to `MediaPipeline` itself is required.
    """

    def scan(self, content: bytes) -> bool:
        return True
