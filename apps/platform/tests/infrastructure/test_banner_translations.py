"""Homepage banners are served in the requested storefront language, falling back to the Uzbek text."""
from __future__ import annotations

import pytest
from django.test import Client

from apps.platform.infrastructure.models import Banner

pytestmark = pytest.mark.django_db


def _texts(locale: str) -> dict:
    body = Client().get(f"/api/v1/settings/banners?locale={locale}").json()
    return {b["id"]: b for b in body["data"]}


def test_translated_texts_with_uzbek_fallback():
    banner = Banner.objects.create(title="Sport ozuqalari", subtitle="Original mahsulotlar", cta_text="Xarid qilish", cta_url="/products",
                                   title_en="Sports nutrition", cta_text_en="Shop now", title_ru="Спортпит")
    bid = str(banner.id)

    en, ru, uz = _texts("en")[bid], _texts("ru")[bid], _texts("uz")[bid]

    assert (en["title"], en["subtitle"], en["cta_text"]) == ("Sports nutrition", "Original mahsulotlar", "Shop now")
    assert (ru["title"], ru["cta_text"]) == ("Спортпит", "Xarid qilish")
    assert (uz["title"], uz["cta_text"]) == ("Sport ozuqalari", "Xarid qilish")
