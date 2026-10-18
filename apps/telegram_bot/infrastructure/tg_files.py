"""
Downloads a file a customer sent to the customer bot (a photo for a product request or the support chat):
getFile → https://api.telegram.org/file/bot<token>/<file_path>. Size-capped; never raises past TelegramFileError.
"""
from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger("nutrizone.telegram_bot")

MAX_BYTES = 5 * 1024 * 1024


class TelegramFileError(Exception):
    pass


@dataclass(frozen=True)
class TelegramFile:
    content: bytes
    filename: str
    mime_type: str


def best_photo(message: dict) -> dict | None:
    """The largest size of a sent photo, or an image sent as a file ("document" with an image mime type)."""
    photos = message.get("photo") or []
    if photos:
        return max(photos, key=lambda p: (p.get("file_size") or 0, p.get("width", 0) * p.get("height", 0)))
    doc = message.get("document") or {}
    if (doc.get("mime_type") or "").startswith("image/"):
        return doc
    return None


def download(file_id: str, token: str | None = None) -> TelegramFile:
    import requests

    token = token or getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token or not file_id:
        raise TelegramFileError("no token or file id")
    base = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
    try:
        meta = requests.get(f"{base}/bot{token}/getFile", params={"file_id": file_id}, timeout=10).json()
    except Exception as exc:  # noqa: BLE001
        raise TelegramFileError("getFile failed") from exc
    result = meta.get("result") or {}
    path = result.get("file_path")
    if not meta.get("ok") or not path:
        raise TelegramFileError(f"getFile: {meta.get('description', 'no file_path')}")
    if (result.get("file_size") or 0) > MAX_BYTES:
        raise TelegramFileError("file too large")
    try:
        response = requests.get(f"{base}/file/bot{token}/{path}", timeout=20)
    except Exception as exc:  # noqa: BLE001
        raise TelegramFileError("download failed") from exc
    if response.status_code != 200 or len(response.content) > MAX_BYTES:
        raise TelegramFileError(f"download status {response.status_code}")
    filename = path.rsplit("/", 1)[-1] or "photo.jpg"
    mime = mimetypes.guess_type(filename)[0] or "image/jpeg"
    return TelegramFile(content=response.content, filename=filename, mime_type=mime)
