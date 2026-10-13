"""
Chat API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern. Fails closed by default.

**A real, disclosed authorization boundary limitation**: no
`IsAssignedOperator`-style permission exists that checks Domain state
directly at the DRF-permission-class level (e.g. "is this user
*currently* the assigned operator for *this specific* conversation").
Django REST Framework's object-level permission hooks run against the
already-resolved view/object, so that check is performed inside each
view itself (via `ConversationRepository`/`ConversationSelector`
lookups) rather than duplicated here as a second, parallel
authorization mechanism -- avoiding two different code paths that
could silently drift apart.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from common.permissions import HasPermissionCode


class BaseChatPermission(BasePermission):
    """Base class -- subclasses set `permission_code`. Fails closed if no code is set."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class ViewOwnConversations(BaseChatPermission):
    """A user viewing their own conversations (as a participant) -- distinct from viewing a specific conversation's detail, which additionally requires the requester to actually BE a participant of THAT conversation (an object-level check performed inside the view itself, see this module's own docstring)."""

    permission_code = "chat.conversation.view_own"


class CanOpenStoreConversation(BaseChatPermission):
    """
    Deliberately reuses `chat.conversation.view_own` -- already
    granted to every authenticated customer (confirmed: it's the same
    code a store owner already holds, per
    store-dashboard/inquiries/InquiriesWorkspace.tsx's own docstring)
    -- rather than inventing a new permission code that would need a
    new role/permission seed. Messaging a store whose products/profile
    a customer can already see is not a privileged action; this is
    intentionally NOT `ManageConversation` (staff-only participant
    management) -- see `OpenStoreConversation`'s own docstring for why
    this one exception exists.
    """

    permission_code = "chat.conversation.view_own"


class ManageConversation(BaseChatPermission):
    """Covers open/close/reopen/archive/assign/participant-management -- the staff-controlled conversation lifecycle."""

    permission_code = "chat.conversation.manage"


class SendMessage(BaseChatPermission):
    permission_code = "chat.message.send"


class EditMessage(BaseChatPermission):
    """Covers edit/delete -- object-level sender-ownership is enforced by Domain itself (`Message.edit()`/`Message.delete()` both raise `MessageNotOwnedBySender`), never duplicated here."""

    permission_code = "chat.message.edit"


class ViewStatistics(BaseChatPermission):
    permission_code = "chat.statistics.view"
