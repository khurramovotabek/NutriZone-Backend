"""
AI assistant HTTP API (/api/v1/assistant/...), called by the storefront's same-origin proxy (src/app/api/assistant).

    GET  status                                   {"enabled": bool}
    POST chat                {message, conversation_id?, locale}  -> text/event-stream of engine events
    GET  conversations/<id>                       the visible transcript (owner only)
    POST conversations/<id>/feedback {index, value: "up"|"down"|null}

Who owns a conversation: the browser's anonymous id (X-Assistant-Client, a random cookie value the proxy sets; only
its sha256 is stored) and, when the customer is signed in, their account (Authorization: Bearer, optional). Limits:
message length, questions per conversation, per-browser and per-IP rate windows -- the API costs money per call.

The chat view is async (ASGI): the stream is produced by an async generator, so a slow answer never holds a worker
thread; CSRF doesn't apply (no cookie auth -- the proxy calls server-to-server).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseNotAllowed, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.assistant.infrastructure import engine

logger = logging.getLogger("nutrizone.assistant")
MAX_MESSAGE = 800
LOCALES = ("uz", "ru", "en")


def _json(data: dict, status: int = 200) -> JsonResponse:
    return JsonResponse({"success": status < 400, **({"data": data} if status < 400 else {"error": data})}, status=status)


def _client_key(request) -> str | None:
    raw = (request.headers.get("X-Assistant-Client") or "").strip()
    if not 16 <= len(raw) <= 128:
        return None
    return hashlib.sha256(raw.encode()).hexdigest()


def _ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else "") or request.META.get("REMOTE_ADDR", "") or "?"


def _customer_id(request):
    """The signed-in customer (optional -- the assistant works for guests too); None on any auth problem."""
    if not request.headers.get("Authorization", "").startswith("Bearer "):
        return None
    try:
        from rest_framework.request import Request

        from apps.identity.infrastructure.authentication import JWTIdentityAuthentication

        result = JWTIdentityAuthentication().authenticate(Request(request))
        return result[0].id if result else None
    except Exception:  # noqa: BLE001 - an expired token just means "guest"
        return None


def _hit(key: str, limit: int, window: int) -> bool:
    """Counts one call in a fixed window; False when the limit is reached."""
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        count = 1
    return count <= limit


def _allowed(client_key: str, ip: str) -> bool:
    per10 = settings.ASSISTANT_RATE_PER_10_MIN
    per_day = settings.ASSISTANT_RATE_PER_DAY
    return (_hit(f"assistant:c10:{client_key}", per10, 600) and _hit(f"assistant:cday:{client_key}", per_day, 86400)
            and _hit(f"assistant:ip10:{ip}", per10 * 3, 600) and _hit(f"assistant:ipday:{ip}", per_day * 3, 86400))


def _owned(conversation_id, client_key: str, customer_id):
    from apps.assistant.infrastructure.models import AssistantConversation

    try:
        cid = uuid.UUID(str(conversation_id))
    except (TypeError, ValueError):
        return None
    conv = AssistantConversation.objects.filter(pk=cid).first()
    if conv is None:
        return None
    if conv.client_key == client_key or (customer_id and conv.customer_id == customer_id):
        return conv
    return None


def _open_conversation(conversation_id, client_key: str, customer_id, locale: str):
    """The caller's conversation (resumed) or a new one; (conv, error_code)."""
    from apps.assistant.infrastructure.models import AssistantConversation

    if conversation_id:
        conv = _owned(conversation_id, client_key, customer_id)
        if conv is not None:
            if conv.turns >= settings.ASSISTANT_MAX_TURNS:
                return None, "CONVERSATION_FULL"
            changed = []
            if customer_id and not conv.customer_id:
                conv.customer_id = customer_id
                changed.append("customer_id")
            if conv.locale != locale:
                conv.locale = locale
                changed.append("locale")
            if changed:
                conv.save(update_fields=changed)
            return conv, None
    return AssistantConversation.objects.create(client_key=client_key, customer_id=customer_id, locale=locale), None


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n".encode()


def _chat_input(request):
    """(body, message, client_key, None) or (…, error response)."""
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return {}, "", None, _json({"code": "BAD_REQUEST", "message": "JSON body expected."}, 400)
    message = str(body.get("message") or "").strip() if isinstance(body, dict) else ""
    if not message:
        return {}, "", None, _json({"code": "EMPTY", "message": "Write a question."}, 400)
    if len(message) > MAX_MESSAGE:
        return {}, "", None, _json({"code": "TOO_LONG", "message": f"Keep it under {MAX_MESSAGE} characters."}, 400)
    client_key = _client_key(request)
    if client_key is None:
        return {}, "", None, _json({"code": "NO_CLIENT", "message": "Missing client id."}, 400)
    return body, message, client_key, None


async def status_view(request):
    from apps.assistant.infrastructure import tts

    return _json({"enabled": engine.is_configured(), "tts": tts.enabled()})


@csrf_exempt
async def tts_view(request):
    """POST {text, locale} -> audio/mpeg: an answer read aloud by a natural voice (Uzbek included)."""
    from django.http import HttpResponse

    from apps.assistant.infrastructure import tts

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not tts.enabled():
        return _json({"code": "DISABLED", "message": "Read-aloud is not configured."}, 503)
    client_key = _client_key(request)
    if not client_key:
        return _json({"code": "NO_CLIENT", "message": "Missing client id."}, 400)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return _json({"code": "BAD_JSON", "message": "Malformed body."}, 400)
    text = str(body.get("text") or "")[:4000]
    locale = body.get("locale") if body.get("locale") in LOCALES else "uz"
    if not text.strip():
        return _json({"code": "EMPTY", "message": "Nothing to read."}, 400)
    limit = getattr(settings, "ASSISTANT_TTS_RATE_PER_10_MIN", 40)
    if not await sync_to_async(_hit)(f"ai:tts:{client_key}", limit, 600) or not await sync_to_async(_hit)(f"ai:tts:ip:{_ip(request)}", limit * 3, 600):
        return _json({"code": "RATE_LIMITED", "message": "Too many requests -- try again later."}, 429)
    try:
        audio = await sync_to_async(tts.synthesize)(text, locale)
    except tts.TtsError:
        return _json({"code": "UNAVAILABLE", "message": "Read-aloud is unavailable right now."}, 503)
    response = HttpResponse(audio, content_type="audio/mpeg")
    response["Cache-Control"] = "private, max-age=86400"
    return response


@csrf_exempt
async def chat_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not engine.is_configured():
        return _json({"code": "DISABLED", "message": "The assistant is not configured."}, 503)
    body, message, client_key, problem = _chat_input(request)
    if problem is not None:
        return problem
    locale = body.get("locale") if body.get("locale") in LOCALES else "uz"
    if not await sync_to_async(_allowed)(client_key, _ip(request)):
        return _json({"code": "RATE_LIMITED", "message": "Too many questions -- try again a bit later."}, 429)
    customer_id = await sync_to_async(_customer_id)(request)
    conv, error = await sync_to_async(_open_conversation)(body.get("conversation_id"), client_key, customer_id, locale)
    if error:
        return _json({"code": error, "message": "This conversation is full -- start a new one."}, 409)

    async def events():
        yield _sse({"type": "start", "conversation_id": str(conv.id)})
        try:
            async for event in engine.run_turn(conv.id, message):
                yield _sse(event)
        except Exception:  # noqa: BLE001 - the stream must end with an answer the UI understands
            logger.exception("assistant: turn failed for %s", conv.id)
            yield _sse({"type": "error", "code": "FAILED", "message": engine.ERROR_TEXT.get(locale, engine.ERROR_TEXT["uz"])})

    response = StreamingHttpResponse(events(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"  # nginx: pass chunks through immediately
    return response


async def conversation_view(request, conversation_id):
    client_key = _client_key(request)
    customer_id = await sync_to_async(_customer_id)(request)
    conv = await sync_to_async(_owned)(conversation_id, client_key or "", customer_id)
    if conv is None:
        return _json({"code": "NOT_FOUND", "message": "No such conversation."}, 404)
    return _json({"id": str(conv.id), "turns": conv.turns, "max_turns": settings.ASSISTANT_MAX_TURNS, "messages": conv.transcript})


def _feedback(conv, index, value) -> bool:
    from django.db import transaction

    from apps.assistant.infrastructure.models import AssistantConversation

    with transaction.atomic():
        conv = AssistantConversation.objects.select_for_update().get(pk=conv.pk)
        transcript = list(conv.transcript)
        if not isinstance(index, int) or not 0 <= index < len(transcript) or transcript[index].get("role") != "assistant":
            return False
        old = transcript[index].get("feedback")
        transcript[index] = {**transcript[index], "feedback": value}
        conv.transcript = transcript
        from apps.assistant.infrastructure.advisor.reco import record_feedback

        record_feedback([c.get("id") for c in transcript[index].get("products") or [] if c.get("id")], value, old)  # the advisor learns from votes
        conv.feedback_up = max(0, conv.feedback_up + (value == "up") - (old == "up"))
        conv.feedback_down = max(0, conv.feedback_down + (value == "down") - (old == "down"))
        conv.save(update_fields=["transcript", "feedback_up", "feedback_down"])
    return True


@csrf_exempt
async def feedback_view(request, conversation_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return _json({"code": "BAD_REQUEST", "message": "JSON body expected."}, 400)
    value = body.get("value")
    if value not in ("up", "down", None):
        return _json({"code": "BAD_REQUEST", "message": "value must be up, down or null."}, 400)
    client_key = _client_key(request)
    customer_id = await sync_to_async(_customer_id)(request)
    conv = await sync_to_async(_owned)(conversation_id, client_key or "", customer_id)
    if conv is None:
        return _json({"code": "NOT_FOUND", "message": "No such conversation."}, 404)
    if not await sync_to_async(_feedback)(conv, body.get("index"), value):
        return _json({"code": "BAD_REQUEST", "message": "No such answer."}, 400)
    return _json({"ok": True})
