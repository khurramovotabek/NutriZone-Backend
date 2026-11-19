"""Product feeds (Google Merchant RSS, Yandex YML): valid XML, sale price, no emoji, numeric YML ids."""
from unittest import mock
from xml.etree import ElementTree as ET

import pytest
from django.core.cache import cache
from django.test import Client

from apps.products.infrastructure import product_feed as feed

pytestmark = pytest.mark.django_db
G = "{http://base.google.com/ns/1.0}"

ITEM = {"id": "ON-WHEY-2LB", "group": "a3540d3f-dd63-4386-b0f5-95e27cedeab6", "title": "Optimum Nutrition Gold Standard & Whey <2 lb>",
        "description": "Zardob proteini", "link": "https://nutrizone.uz/products/on-whey", "image": "https://api.nutrizone.uz/media/x.jpg", "images": [],
        "price": 1349000, "sale_price": 1150000, "currency": "UZS", "in_stock": True, "brand": "Optimum Nutrition", "gtin": "748927028669",
        "mpn": "ON-WHEY-2LB", "category": "Sport ozuqalari > Proteinlar", "category_id": ""}


def test_plain_strips_markup_and_emoji():
    assert feed.plain("<p>💪 Kreatin&nbsp;<b>monogidrat</b> 🧬</p> **kuch**") == "Kreatin monogidrat kuch"


def test_google_feed():
    with mock.patch.object(feed, "items", return_value=[ITEM, {**ITEM, "id": "X1", "sale_price": None, "price": 90000, "gtin": None, "in_stock": False}]):
        root = ET.fromstring(feed.google_xml("ru").encode())
    items = root.findall("./channel/item")
    assert len(items) == 2
    first, second = items
    assert first.find(f"{G}price").text == "1349000 UZS" and first.find(f"{G}sale_price").text == "1150000 UZS"
    assert first.find(f"{G}title").text == ITEM["title"] and first.find(f"{G}gtin").text == "748927028669"
    assert second.find(f"{G}availability").text == "out_of_stock" and second.find(f"{G}sale_price") is None
    assert second.find(f"{G}mpn").text == "ON-WHEY-2LB"
    assert "Спортивное питание" in root.find("./channel/description").text


def test_yandex_feed():
    with mock.patch.object(feed, "items", return_value=[ITEM]):
        root = ET.fromstring(feed.yandex_yml("ru").encode())
    offer = root.find("./shop/offers/offer")
    assert offer.get("id") == "ONWHEY2LB" and offer.find("price").text == "1150000" and offer.find("oldprice").text == "1349000"
    assert offer.find("vendor").text == "Optimum Nutrition" and offer.find("barcode").text == "748927028669"


def test_endpoint_serves_xml():
    cache.delete_many([f"feeds:{k}:{lang}:v1" for k in ("google", "yandex") for lang in feed.LOCALES])
    c = Client()
    r = c.get("/api/v1/products/feeds/google.xml?locale=uz")
    assert r.status_code == 200 and r["Content-Type"].startswith("application/xml")
    ET.fromstring(r.content)
    assert c.get("/api/v1/products/feeds/yandex.xml").status_code == 200
    assert c.get("/api/v1/products/feeds/other.xml").status_code == 404
