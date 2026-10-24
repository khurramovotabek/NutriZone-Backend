"""The free local advisor: understanding, needs, answers by intent, learning from votes."""
import uuid
from decimal import Decimal

import pytest

from apps.assistant.infrastructure.advisor import needs, nlu
from apps.assistant.infrastructure.advisor.engine import answer


class TestNlu:
    @pytest.mark.parametrize("text,facts", [
        ("180 sm, 82 kg, 25 yosh", {"height": 180, "weight": 82, "age": 25}),
        ("рост 172 вес 68,5 мне 31 год, женщина", {"height": 172, "weight": 68.5, "age": 31, "sex": "f"}),
        ("I'm 1.85 m, 90 kg, 40 years old male, train 5 times a week", {"height": 185, "weight": 90, "age": 40, "sex": "m", "activity": "high"}),
        ("byudjet 500 ming, laktozani ko'tara olmayman", {"budget": 500000, "lactose_free": True}),
    ])
    def test_facts(self, text, facts):
        assert nlu.extract_facts(nlu.normalize(text)) == facts

    @pytest.mark.parametrize("text,intent,goal", [
        ("ozish uchun nima tavsiya qilasiz", "recommend", "weight_loss"),
        ("хочу набрать массу", "recommend", "muscle"),
        ("kreatin qanday ichiladi", "usage", None),
        ("yetkazib berish bormi", "faq_delivery", None),
        ("где ваш магазин", "faq_stores", None),
        ("салом", "greet", None),
        ("whey isolate", "search", None),
    ])
    def test_intents(self, text, intent, goal):
        p = nlu.parse(text)
        assert (p.intent, p.goal) == (intent, goal)


def test_needs_mifflin():
    n = needs.compute({"height": 180, "weight": 80, "age": 25, "goal": "muscle", "activity": "medium"})
    assert (n.protein_low, n.protein_high, n.bmi) == (144, 176, 24.7)
    assert 2900 < n.calories < 3100
    assert needs.missing({"height": 180}) == ["weight", "age", "goal"]


@pytest.mark.django_db
class TestAnswers:
    def _product(self, name, price):
        from apps.pricing.infrastructure import models as pricing
        from apps.products.infrastructure import models as p

        product = p.Product.objects.create(id=uuid.uuid4(), status="published")
        p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
        v = p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True)
        pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "D", "currency": "UZS", "status": "active"})
        pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=v.id, base_price_amount=Decimal(price))
        from apps.stores.infrastructure import models as st

        store = st.Store.objects.create(kind="warehouse", name=f"W{uuid.uuid4().hex[:4]}", slug=f"w-{uuid.uuid4().hex[:6]}")
        st.StoreProductStock.objects.create(store=store, product_variant=v, quantity=10)
        return product

    def test_asks_for_missing_profile_then_recommends_a_stack(self):
        self._product("Zorvex Whey Protein", 450000)
        self._product("Zorvex Creatine Monohydrate", 150000)
        reply, ids, _chips, meta = answer({}, "massa olmoqchiman", "uz")
        assert len(ids) == 2 and "bo'yingiz" in reply and meta["profile"]["goal"] == "muscle"  # the goal's stack is shown while we ask
        reply, ids, chips, meta = answer(meta, "178 sm 75 kg 24 yosh", "uz")
        assert "Kunlik ehtiyoj" in reply and "Protein" in reply and "Kreatin" in reply and len(ids) == 2
        assert meta["last"] == "recommend" and chips

    def test_faq_and_greeting(self):
        assert "Assalomu" in answer({}, "salom", "uz")[0]
        assert "Доставка" in answer({}, "как доставка?", "ru")[0]

    def test_votes_teach_the_ranking(self):
        from apps.assistant.infrastructure.advisor.reco import learned_scores, record_feedback, record_shown

        pid = uuid.uuid4()
        record_shown([pid, pid])
        record_feedback([pid], "up", None)
        record_feedback([pid], "down", "up")  # vote changed
        s = learned_scores([pid])[str(pid)]
        assert s < 0


@pytest.mark.django_db
class TestAccountProfile:
    """A signed-in customer's profile answers the advisor's questions; what they tell the chat fills empty fields."""

    def _user(self, **fields):
        from apps.identity.infrastructure.models import User

        return User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10**7:07d}", status="active", **fields)

    def test_profile_prefills_and_is_not_overwritten(self):
        import datetime

        from apps.assistant.infrastructure.advisor.engine import _turn_sync
        from apps.assistant.infrastructure.models import AssistantConversation

        user = self._user(height_cm=180, weight_kg=80, goal="muscle_gain", birthday=datetime.date(2000, 1, 1))
        conv = AssistantConversation.objects.create(customer_id=user.id, locale="uz")
        reply = _turn_sync(conv.id, "menga tavsiya bering")["reply"]
        assert "bo'yingiz" not in reply and "Kunlik ehtiyoj" in reply and "180 sm" in reply
        _turn_sync(conv.id, "vaznim 90 kg")
        user.refresh_from_db()
        assert user.weight_kg == 80  # the customer's own value stays

    def test_chat_facts_fill_empty_profile(self):
        from apps.assistant.infrastructure.advisor.engine import _turn_sync
        from apps.assistant.infrastructure.models import AssistantConversation

        user = self._user()
        conv = AssistantConversation.objects.create(customer_id=user.id, locale="uz")
        _turn_sync(conv.id, "178 sm 75 kg 24 yosh, ozmoqchiman")
        user.refresh_from_db()
        assert user.height_cm == 178 and user.weight_kg == 75 and user.goal == "fat_loss"


def test_status_is_enabled_without_a_key(client, settings):
    settings.ANTHROPIC_API_KEY = ""
    assert client.get("/api/v1/assistant/status").json()["data"]["enabled"] is True
