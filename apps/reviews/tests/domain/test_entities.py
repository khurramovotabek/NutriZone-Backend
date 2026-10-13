from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.reviews.domain.entities import ReviewMedia
from apps.reviews.domain.enums import ReviewMediaType
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestReviewMedia:
    def test_valid_construction(self):
        media = ReviewMedia(id=uuid.uuid4(), media_type=ReviewMediaType.IMAGE, url="https://example.com/photo.jpg", uploaded_at=datetime.utcnow())
        assert media.media_type == ReviewMediaType.IMAGE

    def test_rejects_empty_url(self):
        with pytest.raises(ValidationFailed):
            ReviewMedia(id=uuid.uuid4(), media_type=ReviewMediaType.IMAGE, url="", uploaded_at=datetime.utcnow())

    def test_video_type(self):
        media = ReviewMedia(id=uuid.uuid4(), media_type=ReviewMediaType.VIDEO, url="https://example.com/clip.mp4", uploaded_at=datetime.utcnow())
        assert media.media_type == ReviewMediaType.VIDEO
