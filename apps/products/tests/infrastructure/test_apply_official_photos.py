"""apply_official_photos: the listed product's main photo is replaced by the bundled official pack shot, once; the gallery stays."""
from __future__ import annotations

import io
import json
import uuid

import pytest
from django.core.management import call_command

from apps.products.infrastructure import models as p_models
from apps.products.management.commands.apply_official_photos import PHOTO_DIR

pytestmark = pytest.mark.django_db


def test_main_photo_is_replaced_gallery_kept_and_rerun_is_a_no_op(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    slug, entry = next(iter(json.loads((PHOTO_DIR / "manifest.json").read_text(encoding="utf-8")).items()))
    product = p_models.Product.objects.create(id=uuid.UUID(entry["product_id"]), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Serious Mass", slug=slug)
    for role in ("primary", "gallery"):
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path=f"image/old/{role}.jpg", media_role=role)
    p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="video/old.mp4", media_role="video")

    call_command("apply_official_photos", stdout=io.StringIO(), stderr=io.StringIO())

    images = list(p_models.ProductMedia.objects.filter(product=product, media_role="primary"))
    assert len(images) == 1 and "old" not in images[0].storage_path
    assert p_models.ProductMedia.objects.get(product=product, media_role="gallery").storage_path == "image/old/gallery.jpg"
    assert p_models.ProductMedia.objects.filter(product=product, media_role="video").count() == 1

    out = io.StringIO()
    call_command("apply_official_photos", stdout=out, stderr=io.StringIO())
    assert "0 applied, 1 already official" in out.getvalue()
    assert p_models.ProductMedia.objects.get(product=product, media_role="primary").pk == images[0].pk
