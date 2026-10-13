"""
Reviews Anti-Corruption Layer gateways.

One file, matching the single-file precedent established by Wallet's
and Loyalty's own `infrastructure/gateways.py`.

**Design decision, following the same asymmetric pattern already
established across every prior module**: `NotificationGateway`'s
placeholder is a silent no-op -- a failed "your review was approved!"
notification must never block the actual moderation decision from
being recorded. `MediaStorageGateway` fails loudly -- if the real
media-storage integration is unavailable, silently pretending an
upload succeeded would leave a `ReviewMedia` entity pointing at a URL
that doesn't actually exist, a real data-integrity risk worth
surfacing rather than masking.

**No gateway exists for verified-purchase lookup.** Per Phase 1's
certified boundary, `verified_purchase` is supplied to `Review.
create()` as a plain, externally-computed `bool` -- Infrastructure
does not own the mechanism for computing it (that's the Application
layer's job, in a later phase, asking Ordering's own certified query
service). Adding a gateway interface here, even a placeholder one,
would misrepresent this layer as owning that responsibility.
"""
from __future__ import annotations

import uuid
from typing import Protocol


class NotificationGateway(Protocol):
    def notify_review_event(self, review_id: uuid.UUID, event_type: str, payload: dict) -> None: ...


class NotImplementedNotificationGateway:
    """Default composition-root binding -- a no-op, never a raise, per the design decision documented in this module's docstring."""

    def notify_review_event(self, review_id: uuid.UUID, event_type: str, payload: dict) -> None:
        pass


class MediaStorageGateway(Protocol):
    def confirm_media_url_exists(self, url: str) -> bool: ...


class NotImplementedMediaStorageGateway:
    """Default composition-root binding until a real media-storage integration exists -- fails loudly, per this module's explicit design."""

    def confirm_media_url_exists(self, url: str) -> bool:
        raise NotImplementedError("No media storage integration is registered yet. MediaStorageGateway is a placeholder interface, per this phase's explicit scope.")
