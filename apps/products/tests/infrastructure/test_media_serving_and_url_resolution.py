"""
Real, closed regression tests:

1. config/urls/__init__.py previously had no static() media-serving
   pattern at all -- MEDIA_ROOT/MEDIA_URL were correctly configured
   (config/settings/components/storage.py), and files were genuinely
   written to disk there, but no URL route ever served them. Every
   uploaded image 404'd in both the Dashboard and the customer
   frontend regardless of a correct upload.

2. ProductDetailSelector's own _product_card() returned
   primary_image_path as a bare relative path (e.g.
   "image/72/63/....jpg"), never combined with a host or MEDIA_URL --
   the frontend's <img src={...}> resolved this against its own
   origin (the Next.js host), not the Django backend that actually
   serves /media/, so the image request went to the wrong server.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.conf import settings
from django.test import Client, override_settings
from PIL import Image

from apps.products.infrastructure import models as products_orm

pytestmark = pytest.mark.django_db


def _real_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color="teal").save(buf, format="JPEG")
    return buf.getvalue()


class TestMediaServingIsWired:
    def test_debug_mode_urlpatterns_include_a_real_media_serving_route(self):
        """Regression for the real, closed gap: config/urls/__init__.py previously had no static() media-serving pattern at all -- MEDIA_ROOT/MEDIA_URL were correctly configured and files were genuinely written there, but no URL route ever served them, so every image request 404'd regardless of a correct upload."""
        import importlib

        import config.urls

        try:
            with override_settings(DEBUG=True):
                importlib.reload(config.urls)
                media_patterns = [p for p in config.urls.urlpatterns if str(getattr(p, "pattern", "")).lstrip("^").startswith(settings.MEDIA_URL.lstrip("/"))]
                assert len(media_patterns) > 0, "No urlpattern serves MEDIA_URL even with DEBUG=True"
        finally:
            importlib.reload(config.urls)

    def test_production_mode_does_not_add_the_debug_only_media_route(self):
        """DEBUG=False (production) must not rely on Django itself to serve media -- that is a real web server/CDN's job."""
        import importlib

        import config.urls

        try:
            with override_settings(DEBUG=False):
                importlib.reload(config.urls)
                media_patterns = [p for p in config.urls.urlpatterns if str(getattr(p, "pattern", "")).lstrip("^").startswith(settings.MEDIA_URL.lstrip("/"))]
                assert len(media_patterns) == 0
        finally:
            importlib.reload(config.urls)


class TestProductImageUrlResolution:
    def test_primary_image_path_is_a_full_url_not_a_bare_relative_path(self, settings):
        """Regression for the real, closed gap: previously returned the bare storage_path, which a frontend <img src> would resolve against its own (wrong) origin."""
        settings.PUBLIC_BASE_URL = "https://nutrizone.uz"
        from apps.products.infrastructure.selectors import CatalogSelector

        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published")
        products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Test Product", slug=f"test-{uuid.uuid4().hex[:8]}")
        products_orm.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="image/ab/cd/real-file.jpg", media_role="primary")

        results, _total = CatalogSelector().list(category_id=None, page=1, page_size=10)
        matching = next((r for r in results if r["id"] == str(product.id)), None)

        assert matching is not None
        assert matching["primary_image_path"] == "https://nutrizone.uz/media/image/ab/cd/real-file.jpg"

    def test_no_image_still_returns_none_not_a_broken_url(self, settings):
        settings.PUBLIC_BASE_URL = "https://nutrizone.uz"
        from apps.products.infrastructure.selectors import CatalogSelector

        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published")
        products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Image Product", slug=f"noimg-{uuid.uuid4().hex[:8]}")

        results, _total = CatalogSelector().list(category_id=None, page=1, page_size=10)
        matching = next((r for r in results if r["id"] == str(product.id)), None)

        assert matching is not None
        assert matching["primary_image_path"] is None
