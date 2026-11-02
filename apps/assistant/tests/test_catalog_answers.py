"""The free advisor answers from what the shop entered on the product, brand and category cards -- nothing invented."""
import uuid
from decimal import Decimal

import pytest

from apps.assistant.infrastructure.advisor import brain
from apps.assistant.infrastructure.advisor.engine import _turn_sync, answer
from apps.assistant.infrastructure.models import AdvisorGap, AssistantConversation

FACTS = "1 porsiya (31 g) uchun:\n\nEnergiya qiymati: 120 kkal\n\nYog'lar: 1,5 g\n\nUglevodlar: 3 g\n\nshu jumladan shakar: 1 g\n\nOqsil: 24 g\n\nOqsil manbasi: zardob izolyati"


def _country(code, name):
    from apps.geo.infrastructure import models as geo

    c = geo.Country.objects.filter(code=code).first() or geo.Country.objects.create(code=code, icon="🇺🇸")
    geo.CountryTranslation.objects.update_or_create(country=c, locale_code="uz", defaults={"name": name})
    return c


def _brand(name, description="", country=None):
    from apps.products.infrastructure import models as p

    b = p.Brand.objects.create(country=country)
    p.BrandTranslation.objects.create(brand=b, locale_code="uz", name=name, description=description, slug=f"b-{uuid.uuid4().hex[:6]}")
    return b


def _flavour(name):
    from apps.products.infrastructure import models as p

    f = p.Flavour.objects.create(slug=f"f-{uuid.uuid4().hex[:8]}", color_hex="#ffffff")
    p.FlavourTranslation.objects.create(flavour=f, locale_code="uz", name=name)
    return f


def _product(name, brand=None, category=None, price=1_200_000, card=True):
    from apps.pricing.infrastructure import models as pricing
    from apps.products.infrastructure import models as p
    from apps.stores.infrastructure import models as st

    extra = {"supplement_facts_text_uz": FACTS, "directions_text_uz": "1 qoshiq (31 g) kukunni 200 ml suv yoki sut bilan aralashtiring. Mashg'ulotdan keyin iching.",
             "warnings_text_uz": "Tarkibida sut va soya bor — allergiyasi borlar iste'mol qilmasin.", "nutrition_serving_size_grams": 31,
             "nutrition_servings_per_container": 74, "nutrition_calories": 120} if card else {}
    product = p.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand, category=category, **extra)
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}",
                                        description="Dunyoda eng ko'p sotiladigan zardob oqsillaridan biri. Asosiy ingredient — izolyat." if card else "")
    pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "D", "currency": "UZS", "status": "active"})
    store = st.Store.objects.create(kind="warehouse", name=f"W{uuid.uuid4().hex[:4]}", slug=f"w-{uuid.uuid4().hex[:6]}")
    flavours = [_flavour("Shokolad"), _flavour("Vanil")] if card else [None]
    for i, (fl, kg) in enumerate(zip(flavours, (2.27, 0.9), strict=False)):
        v = p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=i == 0, flavour=fl,
                                            weight_value=kg, weight_unit="kg")
        if fl:
            p.ProductFlavour.objects.get_or_create(product=product, flavour=fl)
        pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=v.id, base_price_amount=Decimal(price if i == 0 else price // 2))
        st.StoreProductStock.objects.create(store=store, product_variant=v, quantity=5)
    return product


@pytest.fixture(autouse=True)
def _fresh_brain_index():
    brain._CACHE["at"] = 0
    yield
    brain._CACHE["at"] = 0


@pytest.fixture
def gold():
    return _product("Zorvex Gold Standard Whey", brand=_brand("Zorvex Nutrition", "Zorvex — 1986-yilda tashkil topgan brend.", _country("US", "AQSH")))


@pytest.mark.django_db
class TestProductCard:
    @pytest.mark.parametrize("question,expected", [
        ("zorvex gold standard tarkibi qanday", ["Oqsil: 24 g", "Energiya qiymati: 120 kkal"]),
        ("zorvex gold standard bir porsiyada necha gramm oqsil bor", ["24 g oqsil", "77%"]),
        ("zorvex gold standard necha porsiya", ["74 porsiya", "~37 kunga", "16 216 so'm"]),  # 1 200 000 / 74
        ("zorvex gold standard qanday ichiladi", ["200 ml suv yoki sut"]),
        ("zorvex gold standard qanday ta'mlari bor", ["2 xil ta'm", "Shokolad", "Vanil"]),
        ("zorvex gold standard hajmlari", ["2.27 kg", "0.9 kg"]),
        ("zorvex gold standard allergiya bormi", ["sut va soya"]),
        ("zorvex gold standard qaysi davlatniki", ["AQSH"]),
        ("zorvex gold standard haqida", ["eng ko'p sotiladigan", "24 g oqsil/porsiya", "74 porsiya"]),
    ])
    def test_answers_from_the_card(self, gold, question, expected):
        reply, ids, _chips, meta = answer({}, question, "uz")
        assert meta["last"] == "catalog" and ids == [str(gold.id)], reply
        for bit in expected:
            assert bit in reply, (bit, reply)

    def test_follow_up_is_about_the_product_just_shown(self, gold):
        _reply, ids, _chips, meta = answer({}, "zorvex gold standard bormi", "uz")
        assert ids == [str(gold.id)] and meta["focus"] == str(gold.id)
        reply, ids, _chips, meta = answer(meta, "uning tarkibi qanday?", "uz")
        assert "Oqsil: 24 g" in reply and ids == [str(gold.id)]

    def test_a_kind_question_after_a_product_is_still_about_the_kind(self, gold):
        _reply, _ids, _chips, meta = answer({}, "zorvex gold standard bormi", "uz")
        reply, _ids, _chips, meta = answer(meta, "kreatin qanday ichiladi", "uz")
        assert meta["last"] != "catalog" and "200 ml suv yoki sut" not in reply

    def test_a_missing_field_is_said_plainly_and_recorded(self):
        _product("Kalmar Plain Whey", card=False)
        conv = AssistantConversation.objects.create(locale="uz", client_key="k" * 20)
        reply = _turn_sync(conv.id, "kalmar plain whey tarkibi qanday")["reply"]
        assert "kiritilmagan" in reply and AdvisorGap.objects.get().reason == "not_found"

    def test_comparison_and_price_questions_keep_their_answers(self, gold):
        assert answer({}, "zorvex gold standard narxi", "uz")[3]["last"] == "price"
        assert answer({}, "zorvex gold standard bormi", "uz")[3]["last"] != "catalog"


@pytest.mark.django_db
class TestBrandAndCategory:
    def test_brand_story_country_and_best_sellers(self, gold):
        for text in ("zorvex qaysi davlatniki", "zorvex nutrition haqida", "zorvex brendi haqida"):
            reply, ids, _chips, meta = answer({}, text, "uz")
            assert meta["last"] == "catalog" and "1986" in reply and "AQSH" in reply and ids == [str(gold.id)], text

    def test_category_description_and_sections(self):
        from apps.products.infrastructure import models as p

        cat = p.Category.objects.create()
        p.CategoryTranslation.objects.create(category=cat, locale_code="uz", name="Geynerlar", slug=f"c-{uuid.uuid4().hex[:6]}",
                                             description="Geyner — oqsil va uglevod aralashmasi, vazn qiyin oshadiganlar uchun.")
        product = _product("Kalmar Mass Gainer", category=cat)
        reply, ids, _chips, meta = answer({}, "geynerlar bo'limi haqida", "uz")
        assert meta["last"] == "catalog" and "vazn qiyin oshadiganlar" in reply and ids == [str(product.id)]
