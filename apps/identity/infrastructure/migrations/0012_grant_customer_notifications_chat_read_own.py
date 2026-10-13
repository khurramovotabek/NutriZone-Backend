"""
Extends the same fix pattern (migrations 0010, 0011) to Notifications
and Chat -- both real, live-verified customers received 403
PERMISSION_DENIED for the identical reason as Wallet/Loyalty/Reviews
before them: the "customer" role was never granted the relevant
permission code after these domains were built.

Grants, confirmed directly from the real permission class source:

- notifications.notification.view_own (ViewOwnNotifications --
  NotificationListCreateView's GET, NotificationDetailView; recipient
  is always request.user.id, never a client-supplied parameter)
- chat.conversation.view_own (ViewOwnConversations --
  ConversationListCreateView's GET, ConversationMessageListView's GET;
  each scoped to the requester's own participancy)
- chat.message.send (SendMessage -- ConversationMessageListView's
  POST; confirmed via direct source read to be a genuinely
  implemented capability, not an honest 501 like this and other
  domains' other create/mutate endpoints, so this grant enables real,
  working functionality, not a dead end)

Deliberately does NOT grant notifications.notification.manage_own
(MarkNotificationSeenView/MarkNotificationReadView are both honest
501s regardless, so granting it would enable no real capability),
nor any Chat admin/moderation permission (ManageConversation,
ViewStatistics, EditMessage), nor conversation-opening (POST on
ConversationListCreateView is also an honest 501).
"""
from __future__ import annotations

import uuid

from django.db import migrations

CUSTOMER_ROLE_CODE = "customer"

NEW_CUSTOMER_PERMISSION_CODES = [
    "notifications.notification.view_own",
    "chat.conversation.view_own",
    "chat.message.send",
]


def grant_notifications_chat_read_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    Permission = apps.get_model("identity", "Permission")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return  # Fails open on missing seed data, matching 0002/0010/0011's own established convention.

    for code in NEW_CUSTOMER_PERMISSION_CODES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"id": uuid.uuid4(), "description": code})
        RolePermission.objects.get_or_create(role=role, permission=permission, defaults={"id": uuid.uuid4()})


def revoke_notifications_chat_read_own(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    RolePermission = apps.get_model("identity", "RolePermission")

    role = Role.objects.filter(code=CUSTOMER_ROLE_CODE).first()
    if role is None:
        return

    RolePermission.objects.filter(role=role, permission__code__in=NEW_CUSTOMER_PERMISSION_CODES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0011_grant_customer_reviews_read_own"),
    ]

    operations = [
        migrations.RunPython(grant_notifications_chat_read_own, revoke_notifications_chat_read_own),
    ]
