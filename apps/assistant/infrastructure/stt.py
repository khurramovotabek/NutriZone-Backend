"""
Speech-to-text for voice messages -- the storefront assistant's microphone button and voice notes sent to the
Telegram bot. Free and offline: Vosk small models (Uzbek, Russian, English; ~50 MB each, downloaded into the image
by docker/django/Dockerfile, see VOSK_MODELS below), any browser / Telegram audio (webm-opus, ogg-opus, mp4-aac,
wav, mp3) decoded with PyAV -- no API key, nothing leaves the server.

* `transcribe(data, loc)` -> Transcript(text, lang, confidence) or raises SpeechError (a short, user-facing code).
* The model of the shopper's language runs first; when it is unsure (low word confidence) or hears nothing, the
  other of Uzbek / Russian gets a try and the more confident one wins -- people here switch languages freely.
* Models load lazily, once per process, behind a lock; a missing model just makes `available()` False and the
  microphone button hides itself (status endpoint), so a server without the models keeps working.
"""

from __future__ import annotations

import io
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# language -> model folder name inside settings.VOSK_MODEL_DIR (the Dockerfile downloads exactly these)
VOSK_MODELS = {"uz": "vosk-model-small-uz-0.22", "ru": "vosk-model-small-ru-0.22", "en": "vosk-model-small-en-us-0.15"}
RATE = 16000
MAX_SECONDS = 60          # a voice question, not a podcast
MAX_BYTES = 3 * 1024 * 1024
UNSURE = 0.62             # mean word confidence under this -> also try the other language
SWITCH_MARGIN = 0.15      # ...which then has to be this much more confident to replace the shopper's language

# The small Uzbek model has no word for the products themselves (kreatin, geyner, izolyat, omega...), so it writes
# something that merely sounds alike. The Russian model knows them: it listens again in keyword mode (only these
# words + [unk]) and every keyword it hears confidently replaces the Uzbek words spoken at that moment.
KEYWORDS = {
    "креатин": "kreatin", "протеин": "protein", "протеина": "protein", "гейнер": "geyner", "изолят": "izolyat", "концентрат": "konsentrat",
    "омега": "omega", "коллаген": "kollagen", "казеин": "kazein", "карнитин": "karnitin", "аминокислоты": "aminokislota",
    "витамин": "vitamin", "магний": "magniy", "цинк": "rux", "глютамин": "glutamin", "батончик": "batonchik",
}
KEYWORD_CONF = 0.8

_models: dict = {}
_lock = threading.Lock()


class SpeechError(Exception):
    """code: EMPTY (no speech heard) / TOO_LONG / TOO_BIG / BAD_AUDIO / UNAVAILABLE."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Transcript:
    text: str
    lang: str
    confidence: float
    seconds: float


def _dir(lang: str) -> Path:
    return Path(getattr(settings, "VOSK_MODEL_DIR", "/opt/vosk")) / VOSK_MODELS[lang]


def available(lang: str | None = None) -> bool:
    if not getattr(settings, "ASSISTANT_VOICE_ENABLED", True):
        return False
    try:
        import vosk  # noqa: F401
    except ImportError:
        return False
    langs = [lang] if lang in VOSK_MODELS else ["uz"]
    return all((_dir(x) / "conf").is_dir() or (_dir(x) / "am").is_dir() for x in langs)


def _model(lang: str):
    m = _models.get(lang)
    if m is not None:
        return m
    with _lock:
        if lang not in _models:
            import vosk

            vosk.SetLogLevel(-1)
            _models[lang] = vosk.Model(str(_dir(lang)))
            logger.info("stt: loaded %s model", lang)
        return _models[lang]


def decode(data: bytes) -> bytes:
    """Any container/codec -> 16 kHz mono signed 16-bit PCM."""
    if not data:
        raise SpeechError("EMPTY")
    if len(data) > MAX_BYTES:
        raise SpeechError("TOO_BIG")
    import av

    out = bytearray()
    try:
        with av.open(io.BytesIO(data)) as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                raise SpeechError("BAD_AUDIO")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
            for frame in container.decode(stream):
                for f in resampler.resample(frame):
                    out += bytes(f.planes[0])[: f.samples * 2]
                if len(out) > MAX_SECONDS * RATE * 2:
                    raise SpeechError("TOO_LONG")
            for f in resampler.resample(None):
                out += bytes(f.planes[0])[: f.samples * 2]
    except SpeechError:
        raise
    except Exception as exc:  # noqa: BLE001 - a broken / unknown file is the customer's audio, not our bug
        logger.info("stt: could not decode audio: %s", exc)
        raise SpeechError("BAD_AUDIO") from exc
    return bytes(out)


def _recognise(pcm: bytes, lang: str, grammar: list[str] | None = None) -> tuple[str, float, list[dict]]:
    """(text, mean word confidence, words with start / end / conf)."""
    import vosk

    rec = vosk.KaldiRecognizer(_model(lang), RATE, json.dumps(grammar, ensure_ascii=False)) if grammar else vosk.KaldiRecognizer(_model(lang), RATE)
    rec.SetWords(True)
    words: list[dict] = []

    def take(raw: str):
        words.extend(w for w in json.loads(raw or "{}").get("result", []) if w.get("word"))

    step = RATE  # half a second of 16-bit samples
    for i in range(0, len(pcm), step):
        if rec.AcceptWaveform(pcm[i:i + step]):
            take(rec.Result())
    take(rec.FinalResult())
    real = [w for w in words if w["word"] != "[unk]"]
    text = " ".join(w["word"] for w in real).strip()
    return text, (sum(w.get("conf", 0.0) for w in real) / len(real) if real else 0.0), real


def _with_keywords(pcm: bytes, words: list[dict]) -> str:
    """The Uzbek transcript with the product words the Russian model heard put back in at their moment."""
    if not available("ru"):
        return " ".join(w["word"] for w in words)
    _t, _c, spotted = _recognise(pcm, "ru", list(KEYWORDS) + ["[unk]"])
    out = [dict(w) for w in words]
    for k in sorted((k for k in spotted if k.get("conf", 0) >= KEYWORD_CONF), key=lambda k: k["start"]):
        latin = KEYWORDS.get(k["word"])
        if not latin:
            continue
        # the Uzbek words said at that moment (most of their length inside the keyword) that the keyword may replace:
        # unsure ones, or ones that start with the same sound ("kabina" for kreatin) -- never a confident other word
        hit = [i for i, w in enumerate(out)
               if min(w["end"], k["end"]) - max(w["start"], k["start"]) > 0.5 * (w["end"] - w["start"])
               and (w.get("conf", 1) < 0.95 or w["word"][:1] == latin[:1])]
        if hit:
            out[hit[0]] = {**out[hit[0]], "word": latin}
            for i in reversed(hit[1:]):
                del out[i]
    return " ".join(w["word"] for w in out)


def _tidy(text: str, lang: str) -> str:
    """Vosk writes lower case without punctuation; a capital first letter reads like a typed question."""
    text = " ".join(text.split())
    if lang == "uz":  # the Uzbek model spells o' / g' with a plain apostrophe or a backtick
        text = text.replace("`", "'").replace("‘", "'").replace("’", "'")
    return text[:1].upper() + text[1:]


def transcribe(data: bytes, loc: str = "uz") -> Transcript:
    if not available():
        raise SpeechError("UNAVAILABLE")
    pcm = decode(data)
    seconds = len(pcm) / (RATE * 2)
    if seconds < 0.4:
        raise SpeechError("EMPTY")
    first = loc if loc in VOSK_MODELS and available(loc) else "uz"
    text, conf, words = _recognise(pcm, first)
    lang = first
    if conf < UNSURE or not text:
        other = "ru" if first != "ru" else "uz"
        if available(other):
            t2, c2, w2 = _recognise(pcm, other)
            # the other language must be clearly better: any model "hears" its own words in foreign speech with a
            # fair confidence, so leaving the shopper's own language needs a real margin and a real sentence
            if t2 and (not text or (c2 > conf + SWITCH_MARGIN and c2 >= 0.75 and len(w2) >= 2)):
                text, conf, words, lang = t2, c2, w2, other
    if lang == "uz" and words:
        text = _with_keywords(pcm, words)
    if not text.strip():
        raise SpeechError("EMPTY")
    return Transcript(text=_tidy(text, lang), lang=lang, confidence=round(conf, 3), seconds=round(seconds, 1))
