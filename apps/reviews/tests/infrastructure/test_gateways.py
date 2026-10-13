from __future__ import annotations

import uuid

import pytest

from apps.reviews.infrastructure.gateways import NotImplementedMediaStorageGateway, NotImplementedNotificationGateway

pytestmark = pytest.mark.unit


class TestGateways:
    def test_notification_gateway_placeholder_is_a_silent_noop(self):
        """Verifies the deliberate asymmetry documented in Phase 2: Notification never raises, unlike MediaStorageGateway."""
        NotImplementedNotificationGateway().notify_review_event(uuid.uuid4(), "ReviewPublished", {})  # must not raise

    def test_media_storage_gateway_placeholder_raises(self):
        with pytest.raises(NotImplementedError):
            NotImplementedMediaStorageGateway().confirm_media_url_exists("https://example.com/a.jpg")
