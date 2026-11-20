"""Product page extras: "Birga arzonroq" bundle (page + cart), trust block, price history + price-drop alerts, Q&A, Server holati."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.products.tests.stock_helpers import put_stock


def _product(name, price, *, category=None, stock=10, brand=None):
    from apps.pricing.infrastructure import models as pricing
    from apps.products.infrastructure import models as p

    product = p.Product.objects.create(id=uuid.uuid4(), status="published", category=category, brand=brand)
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
    v = p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True, weight_value=1, weight_unit="kg")
    pl, _ = pricing.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "D", "currency": "UZS", "status": "active"})
    pricing.PriceListEntryModel.objects.create(price_list=pl, product_variant_id=v.id, base_price_amount=Decimal(price))
    if stock:
        put_stock(v.id, stock)
    return product, v


def _slug(product):
    return product.translations.first().slug


def _client(user) -> APIClient:
    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken()
    token["user_id"] = str(user.id)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def _customer(name="Ali Valiyev"):
    from apps.identity.infrastructure import models as identity

    return identity.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name=name)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestBundle:
    def test_staff_pick_is_offered_with_its_discount(self):
        from apps.products.infrastructure import bundles
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.pdp_extras import extras

        whey, _ = _product("Whey", 800_000)
        shaker, sv = _product("Shaker", 60_000)
        orm.ProductBundle.objects.create(product=whey, companion=shaker, discount_percent=Decimal("10"))
        offer = bundles.offer_for(whey.id)
        assert offer == {"companion_product_id": str(shaker.id), "companion_variant_id": str(sv.id), "percent": "10.00", "source": "curated"}
        b = extras(whey.id, locale="uz")["bundle"]
        assert (b["price"], b["bundle_price"], b["saving"], b["percent"]) == ("60000", "54000", "6000", "10")

    def test_out_of_stock_companion_is_not_offered(self):
        from apps.products.infrastructure import bundles
        from apps.products.infrastructure import models as orm

        whey, _ = _product("Whey", 800_000)
        shaker, _ = _product("Shaker", 60_000, stock=0)
        orm.ProductBundle.objects.create(product=whey, companion=shaker, discount_percent=10)
        orm.BundleSettings.objects.update_or_create(pk=1, defaults={"auto_enabled": False})
        assert bundles.offer_for(whey.id) is None

    def test_cart_discount_counts_each_pair_once(self):
        from apps.products.infrastructure import bundles
        from apps.products.infrastructure import models as orm

        whey, wv = _product("Whey", 800_000)
        shaker, sv = _product("Shaker", 60_000)
        orm.ProductBundle.objects.create(product=whey, companion=shaker, discount_percent=10)
        # 1 whey + 3 shakers: only one shaker has a partner
        total, applied = bundles.cart_discount([(wv.id, Decimal("800000"), 1), (sv.id, Decimal("60000"), 3)])
        assert total == Decimal("6000") and applied[0]["units"] == 1
        # 2 + 2: both pairs
        total, _ = bundles.cart_discount([(wv.id, Decimal("800000"), 2), (sv.id, Decimal("60000"), 2)])
        assert total == Decimal("12000")
        # companion alone: nothing
        assert bundles.cart_discount([(sv.id, Decimal("60000"), 2)])[0] == 0

    def test_auto_bundle_respects_margin_guard(self, monkeypatch):
        from apps.products.infrastructure import bundles

        _p, v = _product("Shaker", 60_000)
        monkeypatch.setattr("apps.stores.infrastructure.count_service.cost_info", lambda ids: {v.id: (Decimal("58000"), "receipt")})
        assert bundles._margin_ok(v.id, Decimal("60000"), Decimal("5"), Decimal("5")) is False  # 57 000 < 60 900
        monkeypatch.setattr("apps.stores.infrastructure.count_service.cost_info", lambda ids: {v.id: (Decimal("30000"), "receipt")})
        assert bundles._margin_ok(v.id, Decimal("60000"), Decimal("5"), Decimal("5")) is True


@pytest.mark.django_db
class TestTrustAndHistory:
    def test_official_flag_and_nearest_unexpired_batch(self):
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.pdp_extras import extras
        from apps.stores.infrastructure.models import StockBatch, StoreProductStock

        brand = orm.Brand.objects.create(is_official_distributor=True)
        product, v = _product("Creatine", 200_000, brand=brand)
        store = StoreProductStock.objects.get(product_variant_id=v.id).store
        today = timezone.localdate()
        StockBatch.objects.create(store=store, product_variant=v, batch_number="OLD", expiry_date=today - dt.timedelta(days=3), quantity=4)
        StockBatch.objects.create(store=store, product_variant=v, batch_number="EMPTY", expiry_date=today + dt.timedelta(days=30), quantity=0)
        StockBatch.objects.create(store=store, product_variant=v, batch_number="B1", expiry_date=today + dt.timedelta(days=400), quantity=6)
        trust = extras(product.id)["trust"]
        assert trust["official_distributor"] is True
        assert trust["expiry"] == {str(v.id): (today + dt.timedelta(days=400)).isoformat()}

    def test_price_history_points_and_lowest_flag(self):
        from apps.pricing.infrastructure import models as pricing
        from apps.products.infrastructure.pdp_extras import extras

        product, v = _product("Whey", 700_000)
        pl = pricing.PriceListModel.objects.get(code="DEFAULT-UZS")
        now = timezone.now()
        for days, old, new in ((60, None, 800_000), (20, 800_000, 700_000)):
            pricing.PriceHistoryEntryModel.objects.create(price_list=pl, product_variant_id=v.id, price_type="base", old_amount=old, new_amount=new, reason="manual", changed_at=now - dt.timedelta(days=days))
        h = extras(product.id)["price_history"][str(v.id)]
        assert [p[1] for p in h["points"]] == ["800000", "700000", "700000"]
        assert (h["min"], h["max"], h["current"], h["lowest_90d"]) == ("700000", "800000", "700000", True)


@pytest.mark.django_db
class TestPriceWatch:
    def test_drop_notifies_once_per_drop(self, django_capture_on_commit_callbacks):
        from apps.notifications.infrastructure.models import NotificationModel
        from apps.pricing.infrastructure import price_watch
        from apps.pricing.infrastructure.models import PriceListEntryModel

        _p, v = _product("Whey", 800_000)
        user = _customer()
        price_watch.watch(user.id, v.id)
        entry = PriceListEntryModel.objects.get(product_variant_id=v.id)
        with django_capture_on_commit_callbacks(execute=True):
            entry.base_price_amount = Decimal("720000")
            entry.save()
        with django_capture_on_commit_callbacks(execute=True):
            entry.save()  # same price again: no second message
        with django_capture_on_commit_callbacks(execute=True):
            entry.base_price_amount = Decimal("750000")
            entry.save()  # went up: nothing
        rows = NotificationModel.objects.filter(recipient_id=user.id, kind="price_drop")
        assert rows.count() == 1
        assert "−10%" in rows.first().title

    def test_api_watch_unwatch(self):
        product, v = _product("Whey", 800_000)
        user = _customer()
        c = _client(user)
        assert c.post(f"/api/v1/products/price-watch/{v.id}").status_code == 201
        assert c.get(f"/api/v1/products/{_slug(product)}/extras").json()["data"]["watching"] == [str(v.id)]
        assert c.delete(f"/api/v1/products/price-watch/{v.id}").status_code == 200
        assert APIClient().post(f"/api/v1/products/price-watch/{v.id}").status_code == 401


@pytest.mark.django_db
class TestQuestions:
    def test_ask_answer_publish_and_notify(self, django_capture_on_commit_callbacks):
        from apps.notifications.infrastructure.models import NotificationModel
        from apps.reviews.infrastructure import questions

        product, _v = _product("Whey", 800_000)
        user = _customer()
        c = _client(user)
        r = c.post(f"/api/v1/products/{_slug(product)}/questions", {"question": "Bu protein laktozasizmi?"}, format="json")
        assert r.status_code == 201
        public = APIClient().get(f"/api/v1/products/{_slug(product)}/questions").json()["data"]
        assert public["total"] == 0  # not answered yet
        assert c.get(f"/api/v1/products/{_slug(product)}/questions").json()["data"]["mine"][0]["question"] == "Bu protein laktozasizmi?"
        with django_capture_on_commit_callbacks(execute=True):
            assert questions.answer(r.json()["data"]["id"], "Ha, laktozasiz.", "Admin") == "added"
        public = APIClient().get(f"/api/v1/products/{_slug(product)}/questions").json()["data"]
        assert public["total"] == 1 and public["items"][0]["author"] == "Ali V." and public["items"][0]["answer"] == "Ha, laktozasiz."
        assert NotificationModel.objects.filter(recipient_id=user.id, kind="question_answered").count() == 1
        with django_capture_on_commit_callbacks(execute=True):
            assert questions.answer(r.json()["data"]["id"], "Ha, laktozasiz. Rahmat!", "Admin") == "edited"
        assert NotificationModel.objects.filter(recipient_id=user.id, kind="question_answered").count() == 1

    def test_validation_and_guest(self):
        product, _v = _product("Whey", 800_000)
        c = _client(_customer())
        assert c.post(f"/api/v1/products/{_slug(product)}/questions", {"question": "ha?"}, format="json").status_code == 422
        assert APIClient().post(f"/api/v1/products/{_slug(product)}/questions", {"question": "Bu protein laktozasizmi?"}, format="json").status_code == 401
        assert APIClient().get("/api/v1/products/no-such-slug/questions").status_code == 404


@pytest.mark.django_db
class TestDashboardPages:
    @pytest.fixture
    def admin(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(user)
        return client

    def test_server_status_renders_and_partial(self, admin, monkeypatch):
        monkeypatch.setattr("apps.platform.infrastructure.server_status.workers", lambda: {"key": "celery", "title": "Celery", "icon": "fa-gears", "status": "ok", "latency": 3, "error": None, "facts": [("Ishchilar", 2)]})
        r = admin.get("/django-admin/server-status/")
        assert r.status_code == 200
        html = r.content.decode()
        assert "nzs-gauges" in html and "nzs-svc" in html and "nz-glass-page" in html and "Server holati" in html
        part = admin.get("/django-admin/server-status/?partial=1").content.decode()
        assert "<html" not in part and "nzs-hero" in part

    def test_server_status_needs_staff(self):
        r = Client().get("/django-admin/server-status/")
        assert r.status_code == 302

    def test_bundle_and_question_admin_pages(self, admin):
        from apps.reviews.infrastructure.models import ProductQuestionModel

        product, _v = _product("Whey", 800_000)
        q = ProductQuestionModel.objects.create(product_id=product.id, customer_id=_customer().id, question="Necha porsiya?")
        assert admin.get("/django-admin/products/productbundle/").status_code == 200
        assert admin.get("/django-admin/products/productbundle/add/").status_code == 200
        assert admin.get("/django-admin/products/bundlesettings/", follow=True).status_code == 200
        assert admin.get("/django-admin/reviews/productquestionmodel/").status_code == 200
        r = admin.post(f"/django-admin/reviews/productquestionmodel/{q.pk}/change/", {"answer": "74 porsiya.", "status": "answered"})
        assert r.status_code == 302
        q.refresh_from_db()
        assert (q.status, q.answer) == ("answered", "74 porsiya.")
