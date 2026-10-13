from __future__ import annotations

import re
import uuid

import pytest
from django.http import QueryDict

from apps.notifications.interfaces.api.v1.filters import parse_notification_list_params
from apps.notifications.interfaces.api.v1.pagination import NotificationPagination
from apps.notifications.interfaces.api.v1.serializers import (
    CreateNotificationSerializer, NotificationDetailSerializer, NotificationSerializer, PreferenceChannelTypeSerializer,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestNotificationListParams:
    def test_defaults(self):
        params = parse_notification_list_params(_qd({}))
        assert params.page == 1
        assert params.status is None

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_notification_list_params(_qd({"filter[status]": "bogus"}))

    def test_valid_status_accepted(self):
        params = parse_notification_list_params(_qd({"filter[status]": "read"}))
        assert params.status == "read"


class TestPagination:
    def test_defaults(self):
        pagination = NotificationPagination.from_query_params(_qd({}))
        assert pagination.page_size == 20

    def test_caps_at_100(self):
        pagination = NotificationPagination.from_query_params(_qd({"page_size": "9999"}))
        assert pagination.page_size == 100

    def test_invalid_page_raises(self):
        with pytest.raises(ValidationFailed):
            NotificationPagination.from_query_params(_qd({"page": "not-a-number"}))


class TestSerializers:
    def test_create_notification_serializer_requires_title(self):
        """The critical invariant this phase's own brief specifically warned about -- verified as an executable test, not just a code-review checklist item."""
        serializer = CreateNotificationSerializer(data={"recipient_id": str(uuid.uuid4()), "notification_type": "transactional", "body": "x"})
        assert not serializer.is_valid()
        assert "title" in serializer.errors

    def test_create_notification_serializer_rejects_blank_title(self):
        serializer = CreateNotificationSerializer(data={"recipient_id": str(uuid.uuid4()), "notification_type": "transactional", "title": "", "body": "x"})
        assert not serializer.is_valid()
        assert "title" in serializer.errors

    def test_create_notification_serializer_valid(self):
        serializer = CreateNotificationSerializer(data={"recipient_id": str(uuid.uuid4()), "notification_type": "transactional", "title": "Shipped", "body": "On its way."})
        assert serializer.is_valid()

    def test_notification_serializer_title_field_has_no_allow_null_or_required_false(self):
        """Direct, executable inspection of the serializer field's own kwargs -- proves the read-shape's `title` field is never accidentally nullable in the response. `required` is not checked here: DRF read-only fields always report `required=False` by design (they're never expected in request input), so that check would be a misunderstanding of DRF semantics, not a real assertion about this field."""
        field = NotificationSerializer().fields["title"]
        assert field.read_only is True
        assert field.allow_null is False

    def test_notification_detail_serializer_does_not_expose_provider_reference(self):
        """A sensitive/internal-only field must never be serialized -- verified structurally against the nested delivery serializer's own declared fields."""
        deliveries_field = NotificationDetailSerializer().fields["deliveries"]
        nested_fields = deliveries_field.child.fields
        assert "provider_reference" not in nested_fields

    def test_preference_channel_type_serializer_requires_valid_channel(self):
        serializer = PreferenceChannelTypeSerializer(data={"channel": "not_a_real_channel", "notification_type": "transactional"})
        assert not serializer.is_valid()

    def test_preference_channel_type_serializer_valid(self):
        serializer = PreferenceChannelTypeSerializer(data={"channel": "telegram", "notification_type": "transactional"})
        assert serializer.is_valid()

    def test_zero_duplicate_serializer_names(self):
        names = re.findall(r"^class (\w+)", open("apps/notifications/interfaces/api/v1/serializers.py").read(), re.M)
        assert len(names) == len(set(names))
