"""
The free advisor's weak spots found by asking it real shoppers' questions, and the teaching loop that closes the rest:
questions it couldn't answer are collected (AdvisorGap) and closed when the shop teaches them on the dashboard.
"""
import uuid
from decimal import Decimal

import pytest
from django.test import Client

from apps.assistant.infrastructure import gaps
from apps.assistant.infrastructure.advisor import brain, nlu
from apps.assistant.infrastructure.advisor.engine import _turn_sync, answer
from apps.assistant.infrastructure.models import AdvisorGap, AssistantConversation, KnowledgeEntry


class TestUnderstanding:
    @pytest.mark.parametrize("text,intent", [
        ("do'stimni taklif qilsam nima beriladi", "faq_referral"),
        ("как пригласить друга", "faq_referral"),
        ("how much creatine per day", "usage"),
        ("сколько креатина в день", "usage"),
        ("menga protein taklif qiling", "recommend"),  # "taklif" alone still means "suggest"
    ])
    def test_intents(self, text, intent):
        assert nlu.parse(text).intent == intent

    def test_sex_budget_and_level_are_not_body_facts(self):
        facts = nlu.extract_facts(nlu.normalize("ayolman, 300 ming so'mgacha, yangi boshladim, 70 kg"))
        assert facts["sex"] == "f" and facts["budget"] == 300_000 and facts["activity"] == "low"
        assert nlu.body_facts(facts) == {"weight": 70}

    def test_sleep_is_a_topic_not_a_complaint(self):
        assert nlu.parse("uyqum yomon").concept == "sleep"

    def test_yes_no_questions(self):
        assert brain.asks("gainer ichsam semiramanmi") and brain.asks("можно ли креатин") and not brain.asks("gainer")


def _product(name, price, brand=None, stock=10):
    from apps.pricing.infrastructure import models as pricing
    from apps.products.infrastructure import models as p
    from apps.stores.infrastructure import models as st

    product = p.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand)
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
    v = p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True)
    pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "D", "currency": "UZS", "status": "active"})
    pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=v.id, base_price_amount=Decimal(price))
    store = st.Store.objects.create(kind="warehouse", name=f"W{uuid.uuid4().hex[:4]}", slug=f"w-{uuid.uuid4().hex[:6]}")
    st.StoreProductStock.objects.create(store=store, product_variant=v, quantity=stock)
    return product


def _brand(name):
    from apps.products.infrastructure import models as p

    b = p.Brand.objects.create()
    p.BrandTranslation.objects.create(brand=b, locale_code="uz", name=name, slug=f"b-{uuid.uuid4().hex[:6]}")
    return b


def _entry(title, questions, keywords, uz):
    return KnowledgeEntry.objects.create(topic="usage", title=title, questions=questions, keywords=keywords, answer_uz=uz)


@pytest.fixture(autouse=True)
def _fresh_brain_index():
    brain._CACHE["at"] = 0  # brands / categories created by the test must be seen
    yield
    brain._CACHE["at"] = 0


@pytest.mark.django_db
class TestAnswers:
    def test_referral_terms_come_from_the_dashboard(self):
        from apps.loyalty.infrastructure.models import LoyaltySettings

        LoyaltySettings.objects.update_or_create(pk=1, defaults={"referrer_reward": 7000, "referee_reward": 3000})
        reply = answer({}, "do'stimni taklif qilsam nima beriladi", "uz")[0]
        assert "+7 000" in reply and "+3 000" in reply and "bo'yingiz" not in reply

    def test_budget_limits_the_pick_instead_of_asking_height(self):
        cheap = _product("Zorvex Whey Protein Lite", 250000)
        _product("Zorvex Whey Protein Pro", 600000)
        reply, ids, _chips, _meta = answer({}, "300 ming so'mgacha protein", "uz")
        assert ids == [str(cheap.id)] and "300 000" in reply and "bo'yingiz" not in reply

    def test_women_get_an_answer_and_products(self):
        _product("Zorvex Whey Protein", 450000)
        for text, loc in (("ayollar uchun protein bormi", "uz"), ("можно ли протеин женщинам", "ru")):
            reply, ids, _chips, _meta = answer({}, text, loc)
            assert ids and ("ayollar" in reply.lower() or "женщин" in reply.lower()) and "bo'yingiz" not in reply and "рост" not in reply

    def test_teen_protein_question_is_answered_safely(self):
        reply = answer({}, "16 yoshman protein ichsam bo'ladimi", "uz")[0]
        assert "18 yoshgacha" in reply and "Protein" in reply and "bo'yingiz" not in reply

    def test_bad_sleep_is_not_a_complaint(self):
        reply = answer({}, "uyqum yomon nima tavsiya qilasiz", "uz")[0]
        assert "uzr" not in reply.lower() and "magniy" in reply

    def test_dose_question_is_not_a_price_question(self):
        _product("Zorvex Creatine Monohydrate", 150000)
        reply = answer({}, "how much creatine per day", "en")[0]
        assert "Prices" not in reply and "3–5 g" in reply

    def test_two_brands_side_by_side(self):
        a = _product("Zorvex Gold Whey", 900000, brand=_brand("Zorvex"))
        b = _product("Kalmar Whey", 700000, brand=_brand("Kalmar"))
        reply, ids, _chips, meta = answer({}, "Zorvex whey yoki Kalmar whey qaysi biri yaxshi", "uz")
        assert meta["last"] == "compare" and ids == [str(a.id), str(b.id)] and "200 000 so'm arzonroq" in reply

    def test_milk_or_water_is_not_a_product_comparison(self):
        _product("Zorvex Creatine Monohydrate", 150000)
        assert answer({}, "kreatinni suv bilan ichsa bo'ladimi yoki sut bilan", "uz")[2] is not None
        assert answer({}, "kreatinni suv bilan ichsa bo'ladimi yoki sut bilan", "uz")[3]["last"] != "compare"

    def test_an_entry_about_another_kind_does_not_answer(self):
        KnowledgeEntry.objects.all().delete()  # only this test's two entries compete
        _entry("Mashg'ulot qilmasam protein ichsa bo'ladimi", "mashg'ulot qilmasam protein ichsam bo'ladimi\nprotein semirtiradimi", "protein, semirish",
               "PROTEIN-ANSWER")
        _entry("Geyner kimga kerak", "geyner kimga\ngainer", "geyner, gainer, massa", "GAINER-ANSWER")
        assert answer({}, "gainer ichsam semiramanmi", "uz")[0] == "GAINER-ANSWER"


@pytest.mark.django_db
class TestTeachingLoop:
    def _conv(self):
        return AssistantConversation.objects.create(locale="uz", client_key="k" * 20)

    def test_unanswered_questions_are_counted_once_per_wording(self):
        conv = self._conv()
        _turn_sync(conv.id, "qwzx plorbt vendaxi qanaqa ishlaydi")
        _turn_sync(conv.id, "Qwzx plorbt vendaxi qanaqa ishlaydi?")
        gap = AdvisorGap.objects.get()
        assert (gap.count, gap.reason, gap.status) == (2, "unclear", "open") and gap.answer

    def test_answered_questions_leave_no_gap(self):
        _turn_sync(self._conv().id, "salom")
        assert not AdvisorGap.objects.exists()

    def test_thumbs_down_records_the_question(self):
        from apps.assistant.interfaces.views import _feedback

        conv = self._conv()
        _turn_sync(conv.id, "salom")
        assert _feedback(conv, 1, "down")
        gap = AdvisorGap.objects.get()
        assert (gap.text, gap.reason) == ("salom", "disliked")

    def test_teaching_closes_matching_gaps(self):
        gaps.record("kurer necha kunda keladi", "uz", "unclear")
        gaps.record("parol qanday tiklanadi", "uz", "unclear")
        entry = _entry("Yetkazish muddati", "kurer necha kunda keladi\nqachon yetkaziladi", "kurer, muddat", "1–2 kun ichida.")
        assert gaps.resolve(entry) == 1
        assert AdvisorGap.objects.get(text="kurer necha kunda keladi").status == "taught"
        assert AdvisorGap.objects.get(text="parol qanday tiklanadi").status == "open"


@pytest.mark.django_db
def test_dashboard_teach_flow():
    from django.contrib.auth.models import User as StaffUser

    user = StaffUser.objects.create_superuser(username=f"t_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    c = Client()
    c.force_login(user)
    gaps.record("sovg'a sertifikati bormi", "uz", "not_found", "Hech narsa topilmadi")
    gap = AdvisorGap.objects.get()
    page = c.get("/django-admin/assistant/advisorgap/")
    assert page.status_code == 200 and "sovg&#x27;a sertifikati bormi" in page.content.decode()
    assert c.get("/django-admin/assistant/advisorgap/?nz=taught").status_code == 200
    add = f"/django-admin/assistant/knowledgeentry/add/?gap={gap.pk}"
    form = c.get(add + "&questions=sovg%27a+sertifikati+bormi&title=Sovg%27a+sertifikati")
    assert form.status_code == 200 and "sovg&#x27;a sertifikati bormi" in form.content.decode()
    r = c.post(add, {"topic": "faq", "title": "Sovg'a sertifikati", "questions": "sovg'a sertifikati bormi", "keywords": "sertifikat, sovg'a",
                     "answer_uz": "Hozircha sovg'a sertifikati yo'q.", "answer_ru": "", "answer_en": "", "priority": "50", "is_active": "on"})
    assert r.status_code == 302
    gap.refresh_from_db()
    assert gap.status == "taught" and gap.knowledge.title == "Sovg'a sertifikati"
    assert answer({}, "sovg'a sertifikati bormi", "uz")[0] == "Hozircha sovg'a sertifikati yo'q."
