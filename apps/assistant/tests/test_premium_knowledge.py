"""The expert set from migration 0011: each question, asked the way shoppers ask it, reaches its own entry."""
import pytest

from apps.assistant.infrastructure.advisor.engine import answer


@pytest.mark.django_db
@pytest.mark.parametrize("loc,question,expected", [
    ("uz", "glutamin kerakmi", "Glutamin — organizm"),
    ("ru", "нужен ли глютамин", "Глютамин — аминокислота"),
    ("en", "is hmb worth it", "HMB is made from"),
    ("uz", "ashvagandha qanday ichiladi", "Ashvagandha — adaptogen"),
    ("uz", "marafonda nima ichish kerak", "Chidamlilik sportida"),
    ("en", "what to eat before a marathon", "In endurance sport"),
    ("uz", "proteinni qanday tanlash kerak", "bir porsiyadagi oqsil narxi"),
    ("ru", "протеин вместо еды", "Протеиновый коктейль — **источник белка**"),
    ("uz", "mashg'ulotdan keyin darhol protein ichish kerakmi", "anabolik oyna"),
    ("uz", "ikki skup bir vaqtda ichsa bo'ladimi", "afsona"),
    ("uz", "steroid sotasizmi", "sotmaydi"),
    ("en", "are sarms safe", "doesn't sell steroids"),
    ("uz", "a vitamini qancha kerak", "yog'da eriydigan"),
    ("uz", "k2 vitamini nima uchun", "K2 vitamini kalsiyni"),
    ("ru", "йод для щитовидки", "Йод нужен"),
    ("uz", "foliy kislotasi qachon ichiladi", "Foliy kislotasi (B9)"),
    ("en", "coq10 dose", "Coenzyme Q10"),
    ("uz", "c vitaminini ko'p ichsam yaxshimi mashg'ulotda", "moslashuvni susaytirgan"),
    ("ru", "какие анализы сдать", "ферритин"),
    ("ru", "детокс чай работает", "печень, почки"),  # "работает" isn't the shop's opening hours
])
def test_question_reaches_its_entry(loc, question, expected):
    assert expected in answer({}, question, loc)[0]


@pytest.mark.django_db
def test_condition_note_comes_first_then_the_entry_for_that_condition():
    reply = answer({}, "витамины при планировании беременности", "ru")[0]
    assert reply.startswith("⚠️") and "400 мкг" in reply
    reply = answer({}, "homiladorman protein ichsam bo'ladimi", "uz")[0]  # no general "yes, protein is fine" after a pregnancy warning
    assert reply.startswith("⚠️") and "Ha. Protein" not in reply


@pytest.mark.django_db
def test_opening_hours_still_understood_in_russian():
    assert answer({}, "до скольки вы работаете", "ru")[3]["last"] == "hours"


@pytest.mark.django_db
def test_dose_question_with_the_product_in_stock_is_not_a_price_list():
    from apps.assistant.tests.test_teaching import _product

    _product("Zorvex Vitamin D3 2000 IU", 90000)  # with nothing in stock the price branch fell through and hid this
    for text, loc in (("how much vitamin d should I take", "en"), ("сколько витамина д нужно принимать", "ru"), ("d vitamini qancha ichish kerak", "uz")):
        reply = answer({}, text, loc)[0]
        assert "Prices" not in reply and "Цены" not in reply and "Narxlar" not in reply, text
