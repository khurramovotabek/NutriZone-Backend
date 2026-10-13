"""
Chat Anti-Corruption Layer gateways.

**Only 2 gateways exist, deliberately, matching this phase's own
explicit "do not create gateways merely because Chat theoretically
could use them" instruction**: `NotificationGateway` and
`MediaStorageGateway` -- the identical two-gateway shape already
established by Reviews' own Phase 2, for the identical justified
reasons (a real notification concern, a real attachment-storage
concern). No presence gateway, no WebSocket/channel-layer gateway
exists here -- presence is Redis-backed state
(`infrastructure/presence.py`), a plain read/write, not a
synchronous external-system integration; real-time delivery is
Channels' own `channel_layer.group_send`, called directly from
`interfaces/api/v1/views.py` (matching every other module's own
convention of calling `core.*` platform primitives directly rather
than gatewaying them).

Design decision, matching the identical asymmetric pattern already
established across every prior module: `NotificationGateway`'s
placeholder is a silent no-op; `MediaStorageGateway` used to fail
loudly (no real attachment-storage concern existed yet). It now has a
real implementation: a client-supplied `attachment_url` on
`POST .../messages` is otherwise an arbitrary, unverified string (the
serializer is a plain `URLField`) -- this confirms it actually names a
real, existing file this deployment's own media pipeline produced,
never a client-supplied external URL, closing that real gap. Reuses
`core.storage.backends.get_storage_backend()`, the same storage
resolution every media upload in this codebase already goes through
-- never a second storage mechanism.
"""
from __future__ import annotations

import uuid
from typing import Protocol


class NotificationGateway(Protocol):
    def notify_chat_event(self, conversation_id: uuid.UUID, event_type: str, payload: dict) -> None: ...


class NotImplementedNotificationGateway:
    def notify_chat_event(self, conversation_id: uuid.UUID, event_type: str, payload: dict) -> None:
        pass


class MediaStorageGateway(Protocol):
    def confirm_media_url_exists(self, url: str) -> bool: ...


class NotImplementedMediaStorageGateway:
    def confirm_media_url_exists(self, url: str) -> bool:
        raise NotImplementedError("No media storage integration is registered yet. MediaStorageGateway is a placeholder interface, per this phase's explicit scope.")


#: Stickers (Chat Phase 4) are fixed, original SVG assets shipped in the
#: *frontend's* own `/public/stickers/`, not this deployment's media
#: storage -- there is nothing in `core.storage` to `.read()`. This is a
#: closed allow-list (not a prefix match), so a client can never smuggle
#: an arbitrary path under `/stickers/` past this check.
STICKER_SLUGS = frozenset(
    {
        "thumbs-up", "heart", "fire", "party", "laugh", "ok",
        "check", "sweat-smile", "cool", "shaka", "open-hands", "eyes", "recycle", "raised-hands", "fist",
    }
)


class RealMediaStorageGateway:
    def confirm_media_url_exists(self, url: str) -> bool:
        if self._is_known_sticker(url):
            return True

        storage_path = self._to_storage_path(url)
        if storage_path is None:
            return False

        from core.storage.backends import get_storage_backend

        backend = get_storage_backend()
        try:
            backend.read(storage_path)
        except Exception:  # noqa: BLE001 -- any failure (missing file, backend error) means "cannot confirm", not a crash for the caller
            return False
        return True

    @staticmethod
    def _is_known_sticker(url: str) -> bool:
        from django.conf import settings

        frontend_url = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
        if not frontend_url or not url.startswith(f"{frontend_url}/stickers/"):
            return False
        filename = url[len(f"{frontend_url}/stickers/"):]
        return filename.removesuffix(".svg") in STICKER_SLUGS and filename.endswith(".svg")

    @staticmethod
    def _to_storage_path(url: str) -> str | None:
        """Reverses the exact URL shape `core.storage.backends.LocalDiskBackend._direct_url` (and this project's own `f"{PUBLIC_BASE_URL}{MEDIA_URL}{storage_path}"` absolute-URL convention, e.g. banners'/products' own media URL construction) produces -- never guesses a different shape."""
        from django.conf import settings

        media_url = settings.MEDIA_URL
        public_base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")

        for prefix in (f"{public_base}{media_url}", media_url):
            if prefix and url.startswith(prefix):
                return url[len(prefix):].lstrip("/")
        return None
