"""`manage.py seed_reference_data`: countries with flags, Uzbekistan's regions + cities, package types -- uz/ru/en, idempotent."""
import pytest
from django.core.management import call_command

from apps.geo.infrastructure import models as geo
from apps.geo.infrastructure import reference_data as ref
from apps.products.infrastructure import models as products

pytestmark = pytest.mark.django_db


def test_seed_is_complete_trilingual_and_idempotent():
    call_command("seed_reference_data")
    call_command("seed_reference_data")  # a second run never duplicates

    assert geo.Country.objects.filter(code__in=[c[0] for c in ref.COUNTRIES]).count() == len(ref.COUNTRIES)
    uz = geo.Country.objects.get(code="UZ")
    assert uz.icon == "🇺🇿" and uz.timezone == "Asia/Tashkent"
    assert {t.locale_code: t.name for t in uz.translations.all()} == {"uz": "O'zbekiston", "ru": "Узбекистан", "en": "Uzbekistan"}
    assert str(uz) == "🇺🇿 O'zbekiston"

    assert geo.Region.objects.filter(country=uz).count() == 14
    n_cities = sum(len(v[3]) for v in ref.UZ_REGIONS.values())
    assert geo.City.objects.filter(region__country=uz).count() == n_cities
    for city in geo.City.objects.filter(region__country=uz).prefetch_related("translations"):
        assert {t.locale_code for t in city.translations.all()} == {"uz", "ru", "en"}
        assert city.center_latitude is not None and city.center_longitude is not None

    # the Telegram checkout finds Tashkent by these codes
    assert geo.City.objects.get(code="TGCITY1").region.code == "TGCITYR"
    assert geo.City.objects.get(code="SA-SAMAR").region.code == "UZ-SA"

    assert products.Package.objects.filter(slug__in=[p[0] for p in ref.PACKAGES]).count() == len(ref.PACKAGES)
    jar = products.Package.objects.get(slug="jar")
    assert {t.locale_code: t.name for t in jar.translations.all()} == {"uz": "Banka", "ru": "Банка", "en": "Jar"}
