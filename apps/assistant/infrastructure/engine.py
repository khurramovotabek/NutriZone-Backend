"""
One customer turn of the AI assistant, streamed: the customer's message goes to Claude with the catalogue tools; text
streams back as it is written; tool calls run against the shop's own data; product cards are emitted when the model
calls show_products; the finished exchange is appended to the conversation.

Async all the way (the API call never blocks a server thread -- the app runs under ASGI/uvicorn); the short database
work (tools, loading/saving the conversation) goes through sync_to_async.

Events (dicts, serialized as SSE by the view):
    {"type": "status", "stage": "searching" | "reading" | "showing" | "stores"}
    {"type": "text", "delta": "..."}
    {"type": "products", "items": [card, ...]}
    {"type": "done", "conversation_id": "...", "turns": n}
    {"type": "error", "code": "...", "message": "..."}   (nothing is saved for a failed turn)

History rules (Claude Opus 5.5 binds thinking blocks to the conversation): the assistant's content blocks are stored
exactly as returned (thinking, text, tool_use, fallback blocks) and earlier turns are never edited; a failed or refused
turn is simply not appended.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from apps.assistant.infrastructure import prompt, tools

logger = logging.getLogger("nutrizone.assistant")

MAX_ROUNDS = 6  # model calls per customer turn (tool round trips)
MAX_TOKENS = 4000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
STAGE = {"search_products": "searching", "get_product_details": "reading", "show_products": "showing", "get_store_info": "stores"}
ERROR_TEXT = {
    "uz": "Kechirasiz, hozir javob bera olmadim. Birozdan keyin qayta urinib ko'ring yoki do'kon bilan bog'laning.",
    "ru": "Извините, сейчас не получилось ответить. Попробуйте чуть позже или свяжитесь с магазином.",
    "en": "Sorry, I couldn't answer right now. Please try again in a moment or contact the shop.",
}
REFUSAL_TEXT = {
    "uz": "Bu savolga javob bera olmayman. Mahsulot tanlash, qo'llash yoki buyurtma bo'yicha yordam beraman.",
    "ru": "На этот вопрос я ответить не могу. Помогу с выбором продуктов, их применением или заказом.",
    "en": "I can't help with that one. I'm happy to help with choosing products, how to use them or your order.",
}


def is_configured() -> bool:
    """The widget is on whenever the assistant is enabled: without an Anthropic key the free local advisor answers."""
    return bool(settings.ASSISTANT_ENABLED)


def uses_claude() -> bool:
    return bool(settings.ANTHROPIC_API_KEY) and getattr(settings, "ASSISTANT_PROVIDER", "auto") != "local"


def make_client():
    import anthropic

    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=90.0, max_retries=2)


def _usage_add(totals: dict, usage) -> None:
    if usage is None:
        return
    totals["input"] += getattr(usage, "input_tokens", 0) or 0
    totals["output"] += getattr(usage, "output_tokens", 0) or 0
    totals["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
    totals["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0


def _load(conversation_id):
    from apps.assistant.infrastructure.models import AssistantConversation

    return AssistantConversation.objects.get(pk=conversation_id)


def _save(conversation_id, new_messages: list, user_text: str, answer: str, cards: list, totals: dict) -> int:
    """Appends one finished exchange (append-only) and the visible transcript lines; returns the turn count."""
    from django.db import transaction
    from django.db.models import F

    from apps.assistant.infrastructure.models import AssistantConversation

    with transaction.atomic():
        conv = AssistantConversation.objects.select_for_update().get(pk=conversation_id)
        now = timezone.now().isoformat()
        conv.history = list(conv.history) + new_messages
        conv.transcript = list(conv.transcript) + [
            {"role": "user", "text": user_text, "at": now},
            {"role": "assistant", "text": answer, "products": cards, "at": now, "feedback": None},
        ]
        conv.turns = F("turns") + 1
        conv.input_tokens = F("input_tokens") + totals["input"]
        conv.output_tokens = F("output_tokens") + totals["output"]
        conv.cache_read_tokens = F("cache_read_tokens") + totals["cache_read"]
        conv.cache_write_tokens = F("cache_write_tokens") + totals["cache_write"]
        conv.products_shown = F("products_shown") + len(cards)
        conv.last_message = user_text[:300]
        conv.save()
        conv.refresh_from_db(fields=["turns"])
        return conv.turns


def _count_error(conversation_id) -> None:
    from django.db.models import F

    from apps.assistant.infrastructure.models import AssistantConversation

    AssistantConversation.objects.filter(pk=conversation_id).update(errors=F("errors") + 1)


async def _run_tools(tool_uses, locale: str, cards: list) -> tuple[list[dict], list[dict]]:
    """Runs one assistant turn's tool calls; returns the UI events and the tool_result blocks (one user message)."""
    events, results = [], []
    for block in tool_uses:
        events.append({"type": "status", "stage": STAGE.get(block.name, "searching")})
        result, is_error = await sync_to_async(tools.run)(block.name, block.input, locale)
        if block.name == "show_products" and not is_error:
            known = {x["id"] for x in cards}
            new = [c for c in result.get("cards", []) if c["id"] not in known]
            cards.extend(new)
            if new:
                events.append({"type": "products", "items": new})
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": tools.as_text(result), **({"is_error": True} if is_error else {})})
    return events, results


def _block_dicts(message) -> list[dict]:
    """The assistant turn exactly as returned, as plain JSON for the history (and the next request)."""
    return [block.to_dict() for block in message.content]


async def run_turn(conversation_id, user_text: str, client=None) -> AsyncIterator[dict]:
    """Streams one answer: Claude when a key is configured (or a test client is injected), else the free local advisor."""
    if client is None and not uses_claude():
        from apps.assistant.infrastructure.advisor import engine as local

        async for event in local.run_turn(conversation_id, user_text):
            yield event
        return
    async for event in _claude_turn(conversation_id, user_text, client):
        yield event


async def _claude_turn(conversation_id, user_text: str, client=None) -> AsyncIterator[dict]:
    """Streams one Claude answer. `client` is injectable (tests); defaults to the configured AsyncAnthropic."""
    import anthropic

    conv = await sync_to_async(_load)(conversation_id)
    locale = conv.locale if conv.locale in ERROR_TEXT else "uz"
    client = client or make_client()
    turn: list[dict] = [{"role": "user", "content": user_text}]
    answer_parts: list[str] = []
    cards: list[dict] = []
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    try:
        for _round in range(MAX_ROUNDS):
            async with client.beta.messages.stream(
                model=settings.ASSISTANT_MODEL,
                max_tokens=MAX_TOKENS,
                system=prompt.system_blocks(locale),
                tools=tools.TOOLS,
                messages=list(conv.history) + turn,
                output_config={"effort": settings.ASSISTANT_EFFORT},
                cache_control={"type": "ephemeral"},  # also caches the growing conversation between rounds / turns
                betas=[FALLBACK_BETA],
                fallbacks="default",  # a safety decline is retried server-side on Anthropic's recommended model
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        answer_parts.append(event.text)
                        yield {"type": "text", "delta": event.text}
                message = await stream.get_final_message()
            _usage_add(totals, message.usage)

            if message.stop_reason == "refusal":
                text = REFUSAL_TEXT[locale]
                yield {"type": "text", "delta": ("\n\n" if answer_parts else "") + text}
                await sync_to_async(_count_error)(conversation_id)
                yield {"type": "done", "conversation_id": str(conversation_id), "turns": conv.turns, "saved": False}
                return  # a declined turn is not appended

            turn.append({"role": "assistant", "content": _block_dicts(message)})
            tool_uses = [b for b in message.content if b.type == "tool_use"]
            if message.stop_reason != "tool_use" or not tool_uses:
                break  # end_turn (or max_tokens: keep what was written)

            events, results = await _run_tools(tool_uses, locale, cards)
            for ev in events:
                yield ev
            turn.append({"role": "user", "content": results})  # all results of one assistant turn in ONE user message
            if answer_parts and not answer_parts[-1].endswith(("\n", " ")):
                answer_parts.append("\n\n")
                yield {"type": "text", "delta": "\n\n"}
        else:
            logger.warning("assistant: %s hit the %s-round limit", conversation_id, MAX_ROUNDS)

        # (if the round limit stopped right after tool results, the history ends on a user turn -- valid: the API
        # merges it with the customer's next message)
        answer = "".join(answer_parts).strip()
        turns = await sync_to_async(_save)(conversation_id, turn, user_text, answer, cards, totals)
        yield {"type": "done", "conversation_id": str(conversation_id), "turns": turns, "saved": True}
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
        logger.warning("assistant: temporary API failure for %s: %s", conversation_id, exc)
        await sync_to_async(_count_error)(conversation_id)
        yield {"type": "error", "code": "BUSY", "message": ERROR_TEXT[locale]}
    except anthropic.APIStatusError as exc:
        logger.error("assistant: API error %s for %s: %s (request %s)", exc.status_code, conversation_id, exc.message, getattr(exc, "request_id", ""))
        await sync_to_async(_count_error)(conversation_id)
        yield {"type": "error", "code": "UNAVAILABLE", "message": ERROR_TEXT[locale]}
