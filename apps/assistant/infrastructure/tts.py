"""
Read-aloud for the assistant: natural neural voices through Microsoft Azure Speech (the provider with ready-made
Uzbek voices -- uz-UZ-MadinaNeural / SardorNeural -- and the same service for Russian and English). Google Cloud
Text-to-Speech has no Uzbek voice, and browsers rarely ship one, which is why this goes through the server.

Settings: AZURE_SPEECH_KEY + AZURE_SPEECH_REGION (e.g. "westeurope"); ASSISTANT_TTS_VOICE_UZ/RU/EN override the
voices. Without a key `enabled()` is False and the site falls back to the browser's own voice for ru/en.
Audio is cached in media storage by a hash of voice + text, so a repeated answer costs nothing.
"""
from __future__ import annotations

import hashlib
import logging
import re
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger("nutrizone.assistant.tts")

VOICES = {"uz": "uz-UZ-MadinaNeural", "ru": "ru-RU-SvetlanaNeural", "en": "en-US-JennyNeural"}
LANG = {"uz": "uz-UZ", "ru": "ru-RU", "en": "en-US"}
MAX_CHARS = 1500
FORMAT = "audio-24khz-48kbitrate-mono-mp3"
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
_MD = re.compile(r"\*\*|__|`|#+\s")
_URL = re.compile(r"https?://\S+")


class TtsError(Exception):
    pass


def enabled() -> bool:
    return bool(getattr(settings, "AZURE_SPEECH_KEY", "") and getattr(settings, "AZURE_SPEECH_REGION", ""))


def voice_for(locale: str) -> str:
    override = getattr(settings, f"ASSISTANT_TTS_VOICE_{locale.upper()}", "") if locale in VOICES else ""
    return override or VOICES.get(locale, VOICES["uz"])


def clean(text: str) -> str:
    """Markdown, emoji and links out; list bullets become sentence breaks -- what a person would actually read out."""
    t = _URL.sub("", text or "")
    t = _EMOJI.sub("", _MD.sub("", t))
    lines = []
    for line in t.splitlines():
        line = line.strip().lstrip("•-–*· ").strip()
        if line:
            lines.append(line if line[-1] in ".!?:;" else line + ".")
    t = " ".join(lines)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_CHARS]


def _ssml(text: str, locale: str, voice: str) -> str:
    return (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{LANG.get(locale, 'uz-UZ')}'>"
            f"<voice name='{voice}'><prosody rate='-4%'>{escape(text)}</prosody></voice></speak>")


def synthesize(text: str, locale: str) -> bytes:
    """MP3 bytes for `text` read in `locale` (cached)."""
    if not enabled():
        raise TtsError("not configured")
    locale = locale if locale in VOICES else "uz"
    spoken = clean(text)
    if not spoken:
        raise TtsError("empty")
    voice = voice_for(locale)
    key = hashlib.sha256(f"{voice}|{spoken}".encode()).hexdigest()
    path = f"tts/{key[:2]}/{key}.mp3"
    if default_storage.exists(path):
        with default_storage.open(path, "rb") as f:
            return f.read()
    import requests

    region = settings.AZURE_SPEECH_REGION
    try:
        res = requests.post(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            data=_ssml(spoken, locale, voice).encode("utf-8"),
            headers={"Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY, "Content-Type": "application/ssml+xml; charset=utf-8",
                     "X-Microsoft-OutputFormat": FORMAT, "User-Agent": "NutriZone"},
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.warning("tts: request failed: %s", exc)
        raise TtsError("unavailable") from exc
    if res.status_code != 200 or not res.content:
        logger.warning("tts: azure answered %s", res.status_code)
        raise TtsError(f"provider {res.status_code}")
    default_storage.save(path, ContentFile(res.content))
    return res.content
