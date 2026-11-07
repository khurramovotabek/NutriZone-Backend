"""Delivery prices: Tashkent city by distance up to the cap (Yandex), the regions by parcel weight from the base (BTS)."""
from decimal import Decimal

import pytest

from apps.ordering.infrastructure import delivery_pricing as dp
from apps.ordering.infrastructure.models import DeliverySettings

pytestmark = pytest.mark.django_db


def _cfg(**kw):
    cfg = DeliverySettings.load()
    for k, v in kw.items():
        setattr(cfg, k, v)
    cfg.save()
    return DeliverySettings.load()


def test_defaults_match_the_owners_prices():
    cfg = DeliverySettings.load()
    assert cfg.tashkent_fee == Decimal("30000") and cfg.tashkent_carrier == "Yandex Dostavka"
    assert cfg.regions_fee == Decimal("30000") and cfg.regions_base_kg == Decimal("1") and cfg.regions_carrier == "BTS"


def test_zone_by_region_code():
    assert dp.zone_for_region_code("TGCITYR") == dp.TASHKENT
    assert dp.zone_for_region_code("UZ-TO") == dp.REGIONS  # Tashkent region goes by BTS
    assert dp.zone_for_region_code(None) == dp.REGIONS


def test_tashkent_grows_with_distance_and_never_passes_the_cap():
    cfg = _cfg(tashkent_min_fee=Decimal("15000"), tashkent_per_km=Decimal("1500"), tashkent_fee=Decimal("30000"))
    assert dp.tashkent_fee(cfg, 0.5) == Decimal("16000")  # 15 000 + 750 -> rounded up to a whole thousand
    assert dp.tashkent_fee(cfg, 6) == Decimal("24000")
    assert dp.tashkent_fee(cfg, 40) == Decimal("30000")  # capped: "30 000 so'mgacha"
    assert dp.tashkent_fee(cfg, None) == Decimal("30000")  # no map point -> the cap


def test_regions_base_up_to_one_kg_then_per_started_kg():
    cfg = _cfg(regions_fee=Decimal("30000"), regions_base_kg=Decimal("1"), regions_extra_per_kg=Decimal("10000"))
    assert dp.regions_fee(cfg, 0.4) == Decimal("30000")
    assert dp.regions_fee(cfg, 1.0) == Decimal("30000")
    assert dp.regions_fee(cfg, 1.2) == Decimal("40000")  # 1 started extra kg
    assert dp.regions_fee(cfg, 3.0) == Decimal("50000")


def test_free_threshold_makes_delivery_free():
    _cfg(free_from=Decimal("500000"))
    assert dp.quote(dp.REGIONS, Decimal("600000"), weight_kg=5).fee == 0
    q = dp.quote(dp.REGIONS, Decimal("100000"), weight_kg=0.5)
    assert q.fee == Decimal("30000") and q.carrier == "BTS"


def test_parcel_weight_uses_labelled_weight_unknown_items_and_packaging():
    from apps.products.infrastructure.models import Brand, Category, Product, ProductVariant

    cat = Category.objects.create(slug="t-cat") if hasattr(Category, "slug") else Category.objects.create()
    brand = Brand.objects.create(slug="t-brand") if hasattr(Brand, "slug") else Brand.objects.create()
    product = Product.objects.create(category=cat, brand=brand)
    whey = ProductVariant.objects.create(product=product, sku="T-WHEY", weight_value=908, weight_unit="g")
    caps = ProductVariant.objects.create(product=product, sku="T-CAPS", weight_value=60, weight_unit="capsule")
    cfg = _cfg(unknown_item_kg=Decimal("0.5"), packaging_kg=Decimal("0.1"))
    assert dp.parcel_weight_kg([(whey.id, 2), (caps.id, 1)], cfg) == pytest.approx(0.1 + 2 * 0.908 + 0.5)


def test_a_region_rate_overrides_the_general_tariff():
    from apps.geo.infrastructure.models import Country, Region
    from apps.ordering.infrastructure.models import RegionDeliveryRate

    cfg = _cfg(regions_fee=Decimal("30000"), regions_base_kg=Decimal("1"), regions_extra_per_kg=Decimal("10000"))
    country = Country.objects.first() or Country.objects.create(code="UZ")
    far = Region.objects.create(country=country, code="UZ-QRT")
    RegionDeliveryRate.objects.create(settings=cfg, region=far, base_fee=Decimal("45000"), extra_per_kg=None)
    assert dp.regions_fee(cfg, 0.5, far.id) == Decimal("45000")
    assert dp.regions_fee(cfg, 2.5, far.id) == Decimal("65000")  # 2 started extra kg x the general 10 000
    assert dp.regions_fee(cfg, 0.5, None) == Decimal("30000")


def test_dashboard_page_previews_and_saves_the_prices(admin_client):
    from django.forms.models import model_to_dict

    assert admin_client.get("/django-admin/ordering/deliverysettings/").url.endswith("/deliverysettings/1/change/")
    page = admin_client.get("/django-admin/ordering/deliverysettings/1/change/").content.decode()
    assert "30 000 so&#x27;mgacha" in page and "1 kg gacha" in page  # Tashkent "up to", regions per kg (not "1.00 kg")

    data = {k: ("" if v is None else v) for k, v in model_to_dict(DeliverySettings.load()).items() if k != "id"}
    data.update({"tashkent_fee": "35000", "free_from": "1000000", "region_rates-TOTAL_FORMS": "0", "region_rates-INITIAL_FORMS": "0",
                 "region_rates-MIN_NUM_FORMS": "0", "region_rates-MAX_NUM_FORMS": "1000", "_save": "1"})
    r = admin_client.post("/django-admin/ordering/deliverysettings/1/change/", data)
    assert r.status_code == 302, r.content.decode()[:500]
    cfg = DeliverySettings.load()
    assert cfg.tashkent_fee == Decimal("35000") and cfg.free_from == Decimal("1000000")
    assert dp.quote(dp.TASHKENT, Decimal("1000000")).fee == 0  # free from the threshold
