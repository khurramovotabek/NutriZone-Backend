"""
AI assistant: tool loop (search -> show cards -> answer) with an injected fake Claude client, append-only history,
refusal / API-error handling, the tools' own validation, and the HTTP layer (SSE stream, ownership, limits, feedback).
The real API is never called.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.test import Client

from apps.assistant.infrastructure import engine, tools
from apps.assistant.infrastructure.models import AssistantConversation

pytestmark = [pytest.mark.django_db]
CLIENT_ID = "browser-" + "x" * 24


def _product(name="Gold Standard Whey", goals=("muscle",), stock=10):
    from apps.products.infrastructure import models as orm
    from apps.products.tests.stock_helpers import put_stock

    category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True)
    product = orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category, goals=list(goals))
    orm.ProductTranslation.objects.create(product=product, locale_code="uz", name=name, slug=f"p-{uuid.uuid4().hex[:8]}")
    variant = orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=True)
    if stock:
        put_stock(variant.id, stock)
    return product


# ---------------------------------------------------------------- a fake AsyncAnthropic


def _block(**kw):
    data = dict(kw)
    return SimpleNamespace(**data, to_dict=lambda: data)


def _message(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason, usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=50, cache_creation_input_tokens=0))


class _Stream:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for b in self.message.content:
                if b.type == "text":
                    for part in (b.text[: len(b.text) // 2], b.text[len(b.text) // 2:]):
                        yield SimpleNamespace(type="text", text=part)
        return gen()

    async def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs, default=str)))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return _Stream(step)


def _run(conv, text, client):
    async def go():
        return [e async for e in engine.run_turn(conv.id, text, client=client)]
    return async_to_sync(go)()


def _conv(locale="uz"):
    return AssistantConversation.objects.create(client_key="k" * 64, locale=locale)


class TestEngine:
    def test_search_show_answer_loop_and_append_only_history(self):
        p = _product()
        conv = _conv()
        fake = FakeClient([
            _message([_block(type="tool_use", id="t1", name="search_products", input={"goal": "muscle"})], "tool_use"),
            _message([_block(type="tool_use", id="t2", name="show_products", input={"product_ids": [str(p.id)]})], "tool_use"),
            _message([_block(type="text", text="**Gold Standard Whey** mushak uchun eng yaxshi tanlov.")]),
        ])
        events = _run(conv, "Mushak uchun nima olay?", fake)
        kinds = [e["type"] for e in events]
        assert kinds[0] == "status" and "products" in kinds and kinds[-1] == "done"
        assert next(e for e in events if e["type"] == "products")["items"][0]["id"] == str(p.id)
        assert "".join(e["delta"] for e in events if e["type"] == "text").startswith("**Gold Standard Whey**")
        # the tool result reached the model as JSON, with the product
        tool_result = fake.calls[1]["messages"][-1]["content"][0]
        assert tool_result["tool_use_id"] == "t1" and str(p.id) in tool_result["content"]
        assert fake.calls[0]["fallbacks"] == "default" and fake.calls[0]["betas"] == [engine.FALLBACK_BETA]
        conv.refresh_from_db()
        assert [m["role"] for m in conv.history] == ["user", "assistant", "user", "assistant", "user", "assistant"]
        assert conv.turns == 1 and conv.products_shown == 1 and conv.input_tokens == 300 and conv.cache_read_tokens == 150
        assert conv.transcript[1]["products"][0]["id"] == str(p.id)

        # the next turn sends the stored history unchanged, then the new question
        fake2 = FakeClient([_message([_block(type="text", text="Kuniga 1 porsiya.")])])
        _run(conv, "Qanday ichaman?", fake2)
        sent = fake2.calls[0]["messages"]
        assert sent[:6] == json.loads(json.dumps(conv.history, default=str)) and sent[6] == {"role": "user", "content": "Qanday ichaman?"}
        conv.refresh_from_db()
        assert conv.turns == 2 and len(conv.history) == 8

    def test_refusal_is_not_saved(self):
        conv = _conv("ru")
        events = _run(conv, "...", FakeClient([_message([], "refusal")]))
        assert events[-1]["saved"] is False and "не могу" in events[0]["delta"]
        conv.refresh_from_db()
        assert conv.history == [] and conv.turns == 0 and conv.errors == 1

    def test_api_failure_gives_a_friendly_error_and_saves_nothing(self):
        import anthropic
        import httpx2

        conv = _conv("en")
        err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
        events = _run(conv, "hi", FakeClient([err]))
        assert events == [{"type": "error", "code": "BUSY", "message": engine.ERROR_TEXT["en"]}]
        conv.refresh_from_db()
        assert conv.history == [] and conv.errors == 1


class TestTools:
    def test_validation_errors_go_back_to_the_model(self):
        assert tools.run("search_products", {"goal": "magic"}, "uz")[1] is True
        assert tools.run("search_products", {"limit": 99}, "uz")[1] is True
        assert tools.run("get_product_details", {"product_id": "nope"}, "uz")[1] is True
        assert tools.run("unknown", {}, "uz")[1] is True
        assert tools.run("show_products", {"product_ids": [str(uuid.uuid4())]}, "uz")[1] is True

    def test_show_products_skips_bad_ids_and_cards_carry_cart_data(self):
        p = _product(stock=3)
        result, is_error = tools.run("show_products", {"product_ids": ["junk", str(p.id), str(p.id)]}, "uz")
        assert not is_error and len(result["cards"]) == 1
        card = result["cards"][0]
        assert card["variant_id"] and card["in_stock"] is True and card["name"] == "Gold Standard Whey"
        assert "cards" not in json.loads(tools.as_text(result))

    def test_goal_browse_finds_tagged_in_stock_products(self):
        from apps.products.infrastructure import smart_search

        smart_search.invalidate_index()
        p = _product(goals=("weight_loss",))
        _product(name="Out of stock", goals=("weight_loss",), stock=0)
        result, is_error = tools.run("search_products", {"goal": "weight_loss"}, "uz")
        assert not is_error and [x["id"] for x in result["products"]] == [str(p.id)]


class TestHttp:
    @pytest.fixture(autouse=True)
    def _configured(self, settings, monkeypatch):
        settings.ANTHROPIC_API_KEY = "test-key"
        settings.ASSISTANT_ENABLED = True
        settings.ASSISTANT_RATE_PER_10_MIN = 3
        # rate-limit counters in a private cache: the test settings share the dev Redis (also the Celery broker)
        from django.core.cache.backends.locmem import LocMemCache

        from apps.assistant.interfaces import views

        monkeypatch.setattr(views, "cache", LocMemCache(f"assistant-tests-{uuid.uuid4().hex}", {}))

    def _post(self, client, body, cid=CLIENT_ID):
        return client.post("/api/v1/assistant/chat", json.dumps(body), content_type="application/json", HTTP_X_ASSISTANT_CLIENT=cid)

    def _stream(self, response):
        async def collect():
            return b"".join([chunk async for chunk in response.streaming_content])
        raw = async_to_sync(collect)().decode()
        return [json.loads(line[6:]) for line in raw.split("\n") if line.startswith("data: ")]

    def test_stream_conversation_ownership_and_feedback(self, monkeypatch):
        async def fake_turn(conversation_id, text, client=None):
            await engine.sync_to_async(engine._save)(conversation_id, [{"role": "user", "content": text}, {"role": "assistant", "content": [{"type": "text", "text": "Salom!"}]}],
                                                      text, "Salom!", [], {"input": 1, "output": 1, "cache_read": 0, "cache_write": 0})
            yield {"type": "text", "delta": "Salom!"}
            yield {"type": "done", "conversation_id": str(conversation_id), "turns": 1, "saved": True}

        monkeypatch.setattr(engine, "run_turn", fake_turn)
        c = Client()
        events = self._stream(self._post(c, {"message": "Salom", "locale": "uz"}))
        assert [e["type"] for e in events] == ["start", "text", "done"]
        cid = events[0]["conversation_id"]
        r = c.get(f"/api/v1/assistant/conversations/{cid}", HTTP_X_ASSISTANT_CLIENT=CLIENT_ID)
        assert r.status_code == 200 and r.json()["data"]["messages"][1]["text"] == "Salom!"
        assert c.get(f"/api/v1/assistant/conversations/{cid}", HTTP_X_ASSISTANT_CLIENT="someone-else-" + "y" * 20).status_code == 404
        r = c.post(f"/api/v1/assistant/conversations/{cid}/feedback", json.dumps({"index": 1, "value": "up"}), content_type="application/json", HTTP_X_ASSISTANT_CLIENT=CLIENT_ID)
        assert r.status_code == 200 and AssistantConversation.objects.get(pk=cid).feedback_up == 1
        # resuming the same conversation
        events = self._stream(self._post(c, {"message": "Yana", "conversation_id": cid}))
        assert events[0]["conversation_id"] == cid

    def test_limits(self):
        c = Client()
        assert self._post(c, {"message": ""}).status_code == 400
        assert self._post(c, {"message": "x" * 900}).status_code == 400
        assert self._post(c, {"message": "salom"}, cid="short").status_code == 400

    def test_rate_limit(self, monkeypatch):
        async def fake_turn(conversation_id, text, client=None):
            yield {"type": "done", "conversation_id": str(conversation_id), "turns": 0, "saved": False}

        monkeypatch.setattr(engine, "run_turn", fake_turn)
        c = Client()
        codes = [self._post(c, {"message": "salom"}).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]

    def test_disabled_only_when_switched_off(self, settings):
        settings.ASSISTANT_ENABLED = False
        c = Client()
        assert c.get("/api/v1/assistant/status").json()["data"]["enabled"] is False
        assert self._post(c, {"message": "salom"}).status_code == 503

    def test_without_a_key_the_free_advisor_answers(self, settings):
        settings.ANTHROPIC_API_KEY = ""
        c = Client()
        assert c.get("/api/v1/assistant/status").json()["data"]["enabled"] is True
        events = self._stream(self._post(c, {"message": "salom"}))
        types = [e["type"] for e in events]
        assert types[0] == "start" and "chips" in types and types[-1] == "done"
        assert "Assalomu" in "".join(e.get("delta", "") for e in events)
