"""
`python manage.py stt_server` -- the speech-to-text service (compose service `stt`, docker-compose.prod.yml).

The speech models take ~370 MB per process; loading them in every web worker (2 replicas x 4 workers) would cost
~3 GB and make the first voice message of each worker wait for the load. Here they are loaded once, at start, in one
process; web workers and the Telegram webhook post the recording to it (stt.transcribe -> STT_SERVICE_URL).

POST /transcribe?locale=uz  (raw audio body) -> 200 {text, lang, confidence, seconds} | 4xx/5xx {code}
GET  /health                -> 200 once the models are loaded
At most --parallel recordings are worked on at a time (CPU bound); the rest wait their turn.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from django.core.management.base import BaseCommand

from apps.assistant.infrastructure import stt

logger = logging.getLogger(__name__)
STATUS = {"TOO_BIG": 413, "TOO_LONG": 413, "UNAVAILABLE": 503}


class Command(BaseCommand):
    help = "Speech-to-text service for voice messages (models loaded once)."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=2700)
        parser.add_argument("--parallel", type=int, default=2)

    def handle(self, *args, port, parallel, **opts):
        gate = threading.BoundedSemaphore(parallel)
        ready = threading.Event()

        def warm():
            for lang in ("uz", "ru"):
                if stt.available(lang):
                    stt._model(lang)
            ready.set()
            self.stdout.write("stt: models loaded")

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, status: int, body: dict):
                raw = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if urlparse(self.path).path == "/health":
                    return self._send(200 if ready.is_set() else 503, {"ready": ready.is_set()})
                self._send(404, {"code": "NOT_FOUND"})

            def do_POST(self):
                url = urlparse(self.path)
                if url.path != "/transcribe":
                    return self._send(404, {"code": "NOT_FOUND"})
                size = int(self.headers.get("Content-Length") or 0)
                if size > stt.MAX_BYTES:
                    return self._send(413, {"code": "TOO_BIG"})
                data = self.rfile.read(size) if size else b""
                locale = (parse_qs(url.query).get("locale") or ["uz"])[0]
                with gate:
                    try:
                        r = stt.transcribe_local(data, locale)
                    except stt.SpeechError as exc:
                        return self._send(STATUS.get(exc.code, 422), {"code": exc.code})
                    except Exception:  # noqa: BLE001 -- one bad file must not take the service down
                        logger.exception("stt service failed")
                        return self._send(500, {"code": "BAD_AUDIO"})
                self._send(200, {"text": r.text, "lang": r.lang, "confidence": r.confidence, "seconds": r.seconds})

            def log_message(self, fmt, *args):  # access log off: recordings are private, keep logs quiet
                pass

        threading.Thread(target=warm, daemon=True).start()
        server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        server.daemon_threads = True
        self.stdout.write(f"stt: listening on :{port} (parallel {parallel})")
        server.serve_forever()
