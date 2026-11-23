"""Video rows on the product media inline: problems are form errors (not a 500
from the domain inside save_formset), the role follows the file type and an
empty duration becomes 45 s."""
from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.products.infrastructure.admin import ProductMediaInlineForm
from core.media.enums import MediaType
from core.media.pipeline import MAX_VIDEO_SIZE_BYTES, max_size_for

pytestmark = pytest.mark.django_db


def _form(role, upload, duration=""):
    return ProductMediaInlineForm(data={"media_role": role, "sort_order": "0", "duration_seconds": duration}, files={"file_upload": upload})


def test_video_without_duration_defaults_to_45_seconds():
    form = _form("video", SimpleUploadedFile("clip.mp4", b"x" * 100, content_type="video/mp4"))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["duration_seconds"] == 45
    assert form.instance.duration_seconds == 45


def test_video_file_with_gallery_role_becomes_video():
    form = _form("gallery", SimpleUploadedFile("clip.mov", b"x" * 100, content_type="application/octet-stream"))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["media_role"] == "video"
    assert form.cleaned_data["file_upload"].content_type == "video/quicktime"


def test_explicit_duration_kept():
    form = _form("video", SimpleUploadedFile("clip.mp4", b"x" * 100, content_type="video/mp4"), duration="30")
    assert form.is_valid(), form.errors
    assert form.cleaned_data["duration_seconds"] == 30


def test_oversized_video_is_a_form_error():
    big = SimpleUploadedFile("big.mp4", b"x", content_type="video/mp4")
    big.size = MAX_VIDEO_SIZE_BYTES + 1
    form = _form("video", big)
    assert not form.is_valid()
    assert "MB" in str(form.errors)


def test_unknown_video_format_is_a_form_error():
    form = _form("video", SimpleUploadedFile("clip.avi", b"x" * 100, content_type="video/x-msvideo"))
    assert not form.is_valid()


def test_video_limit_larger_than_image_limit():
    assert max_size_for(MediaType.VIDEO) == 50 * 1024 * 1024
    assert max_size_for(MediaType.IMAGE) == 25 * 1024 * 1024
