from __future__ import annotations

import uuid

import pytest

from apps.chat.infrastructure.gateways import NotImplementedMediaStorageGateway, NotImplementedNotificationGateway

pytestmark = pytest.mark.unit


class TestGateways:
    def test_notification_gateway_placeholder_is_a_silent_noop(self):
        NotImplementedNotificationGateway().notify_chat_event(uuid.uuid4(), "MessageSent", {})  # must not raise

    def test_media_storage_gateway_placeholder_raises(self):
        with pytest.raises(NotImplementedError):
            NotImplementedMediaStorageGateway().confirm_media_url_exists("https://example.com/a.jpg")
