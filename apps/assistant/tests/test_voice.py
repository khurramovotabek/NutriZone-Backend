"""Voice messages: offline speech-to-text (stt.py), the widget endpoint and the Telegram voice note."""

from __future__ import annotations

from unittest import mock

import pytest
from django.test import Client

from apps.assistant.infrastructure import stt

pytestmark = pytest.mark.django_db

H = {"HTTP_X_ASSISTANT_CLIENT": "v" * 20}


def _w(word, start, end, conf=0.6):
    return {"word": word, "start": start, "end": end, "conf": conf}


class TestKeywords:
    """The Uzbek model lacks product words; the Russian keyword pass puts them back at their moment."""

    def _merge(self, uz_words, spotted):
        with mock.patch.object(stt, "available", return_value=True), mock.patch.object(stt, "_recognise", return_value=("", 1.0, spotted)):
            return stt._with_keywords(b"", uz_words)

    def test_unsure_word_is_replaced_by_the_product(self):
        out = self._merge([_w("kabina", 0.1, 0.6, 0.39), _w("qanday", 0.7, 1.1, 0.95), _w("ichish", 1.2, 1.5, 0.9)], [_w("креатин", 0.0, 0.65, 1.0)])
        assert out == "kreatin qanday ichish"

    def test_a_confident_different_word_is_kept(self):
        out = self._merge([_w("shousi", 1.1, 1.6, 1.0), _w("kerak", 1.9, 2.2, 1.0)], [_w("коллаген", 1.1, 1.6, 0.9)])
        assert out == "shousi kerak"

    def test_weak_keywords_are_ignored(self):
        assert self._merge([_w("kabina", 0.1, 0.6, 0.3)], [_w("креатин", 0.0, 0.6, 0.5)]) == "kabina"


class TestDecode:
    def test_empty_and_garbage_audio(self):
        with pytest.raises(stt.SpeechError) as e:
            stt.decode(b"")
        assert e.value.code == "EMPTY"
        with pytest.raises(stt.SpeechError) as e:
            stt.decode(b"not audio at all" * 50)
        assert e.value.code == "BAD_AUDIO"

    def test_too_big(self):
        with pytest.raises(stt.SpeechError) as e:
            stt.decode(b"x" * (stt.MAX_BYTES + 1))
        assert e.value.code == "TOO_BIG"


class TestEndpoint:
    def test_writes_down_a_voice_question(self):
        heard = stt.Transcript(text="Kreatin qanday ichiladi", lang="uz", confidence=0.8, seconds=2.1)
        with mock.patch.object(stt, "available", return_value=True), mock.patch.object(stt, "transcribe", return_value=heard) as tr:
            r = Client().post("/api/v1/assistant/stt?locale=uz", b"OggS....", content_type="audio/ogg", **H)
        assert r.status_code == 200
        assert r.json()["data"] == {"text": "Kreatin qanday ichiladi", "lang": "uz", "seconds": 2.1, "confidence": 0.8}
        assert tr.call_args.args == (b"OggS....", "uz")

    def test_nothing_heard_is_a_friendly_error_in_the_shoppers_language(self):
        with mock.patch.object(stt, "available", return_value=True), mock.patch.object(stt, "transcribe", side_effect=stt.SpeechError("EMPTY")):
            r = Client().post("/api/v1/assistant/stt?locale=ru", b"x", content_type="audio/webm", **H)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "EMPTY" and "микрофон" in r.json()["error"]["message"]

    def test_unavailable_without_models_and_status_says_so(self):
        with mock.patch.object(stt, "available", return_value=False):
            assert Client().post("/api/v1/assistant/stt", b"x", content_type="audio/webm", **H).status_code == 503
            assert Client().get("/api/v1/assistant/status").json()["data"]["voice"] is False

    def test_needs_a_client_id(self):
        with mock.patch.object(stt, "available", return_value=True):
            assert Client().post("/api/v1/assistant/stt", b"x", content_type="audio/webm").status_code == 400


class TestTelegramVoice:
    def test_voice_note_is_shown_and_answered_like_text(self):
        from apps.telegram_bot.interfaces import callback_router as cr

        user = mock.Mock(id=1)
        msg = {"chat": {"id": 5, "type": "private"}, "from": {"id": 7}, "voice": {"file_id": "F", "duration": 3}}
        heard = stt.Transcript(text="Geyner qanday ichiladi", lang="uz", confidence=0.7, seconds=3)
        with mock.patch("apps.telegram_bot.interfaces.onboarding_state.get_state", return_value=None), \
                mock.patch("apps.telegram_bot.interfaces.chat_state.get_active_conversation", return_value=None), \
                mock.patch.object(cr, "_resolve_user", return_value=user), mock.patch.object(cr, "_lang", return_value="uz"), \
                mock.patch.object(stt, "available", return_value=True), \
                mock.patch("apps.telegram_bot.infrastructure.tg_files.download", return_value=mock.Mock(content=b"OggS")), \
                mock.patch.object(stt, "transcribe", return_value=heard), \
                mock.patch.object(cr, "_send") as send, mock.patch.object(cr, "search_text") as search:
            assert cr.voice_question(msg) is True
        assert "Geyner qanday ichiladi" in send.call_args.args[1]
        search.assert_called_once_with(5, 7, "Geyner qanday ichiladi")

    def test_too_long_note_is_refused_politely(self):
        from apps.telegram_bot.interfaces import callback_router as cr

        msg = {"chat": {"id": 5, "type": "private"}, "from": {"id": 7}, "voice": {"file_id": "F", "duration": 400}}
        with mock.patch("apps.telegram_bot.interfaces.onboarding_state.get_state", return_value=None), \
                mock.patch("apps.telegram_bot.interfaces.chat_state.get_active_conversation", return_value=None), \
                mock.patch.object(cr, "_resolve_user", return_value=mock.Mock(id=1)), mock.patch.object(cr, "_lang", return_value="ru"), \
                mock.patch.object(stt, "available", return_value=True), mock.patch.object(cr, "_send") as send, \
                mock.patch.object(cr, "search_text") as search:
            assert cr.voice_question(msg) is True
        assert "минуты" in send.call_args.args[1]
        search.assert_not_called()

    def test_skipped_during_a_live_operator_chat(self):
        from apps.telegram_bot.interfaces import callback_router as cr

        msg = {"chat": {"id": 5, "type": "private"}, "from": {"id": 7}, "voice": {"file_id": "F", "duration": 3}}
        with mock.patch("apps.telegram_bot.interfaces.onboarding_state.get_state", return_value=None), \
                mock.patch("apps.telegram_bot.interfaces.chat_state.get_active_conversation", return_value="c1"):
            assert cr.voice_question(msg) is False


@pytest.mark.skipif(not stt.available("uz"), reason="Vosk models not installed in this environment")
def test_real_models_read_a_clean_recording():
    """End to end with the real models on a generated tone: a beep is not speech, so nothing is 'heard'."""
    import io
    import math
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
    with pytest.raises(stt.SpeechError) as e:
        stt.transcribe(buf.getvalue(), "uz")
    assert e.value.code == "EMPTY"


class TestSpeechService:
    """Production: web workers post recordings to the one process that holds the models (stt_server)."""

    def test_uses_the_service_and_never_loads_models_here(self, settings):
        settings.STT_SERVICE_URL = "http://stt:2700"
        fake = mock.Mock(status_code=200, json=lambda: {"text": "Omega kerak", "lang": "uz", "confidence": 0.9, "seconds": 1.5})
        with mock.patch("requests.post", return_value=fake) as post, mock.patch.object(stt, "transcribe_local") as local:
            r = stt.transcribe(b"OggS", "uz")
        assert (r.text, r.lang, r.confidence) == ("Omega kerak", "uz", 0.9)
        assert post.call_args.args[0] == "http://stt:2700/transcribe" and post.call_args.kwargs["params"] == {"locale": "uz"}
        local.assert_not_called()

    def test_service_error_codes_come_through(self, settings):
        settings.STT_SERVICE_URL = "http://stt:2700"
        with mock.patch("requests.post", return_value=mock.Mock(status_code=422, json=lambda: {"code": "EMPTY"})):
            with pytest.raises(stt.SpeechError) as e:
                stt.transcribe(b"OggS", "uz")
        assert e.value.code == "EMPTY"

    def test_unreachable_service_falls_back_to_this_process(self, settings):
        import requests

        settings.STT_SERVICE_URL = "http://stt:2700"
        heard = stt.Transcript(text="Kreatin", lang="uz", confidence=0.7, seconds=1)
        with mock.patch("requests.post", side_effect=requests.ConnectionError), mock.patch.object(stt, "transcribe_local", return_value=heard) as local:
            assert stt.transcribe(b"OggS", "uz") is heard
        local.assert_called_once()
