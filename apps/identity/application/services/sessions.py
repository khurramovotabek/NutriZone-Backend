"""
Session-management application services: ListOwnSessions, RevokeSession.
"""
from __future__ import annotations

import uuid

from apps.identity.application.ports import UserSessionRepository
from apps.identity.domain.events import SessionRevoked
from common.exceptions import PermissionDenied, ResourceNotFound
from core.audit import AuditEventBuilder


class ListOwnSessions:
    def __init__(self, session_repo: UserSessionRepository) -> None:
        self._session_repo = session_repo

    def execute(self, user_id: uuid.UUID):
        return self._session_repo.list_active_for_user(user_id)


class RevokeSession:
    """
    Backs `DELETE /identity/sessions/{id}` (Enterprise REST API
    Blueprint §13.1) -- a user may revoke their own session; staff with
    `identity.session.revoke_any` may revoke anyone's (permission check
    happens at the interfaces/api layer via HasPermissionCode, this
    service enforces the ownership fallback for the self-service case).
    """

    def __init__(self, session_repo: UserSessionRepository, stage_events) -> None:
        self._session_repo = session_repo
        self._stage_events = stage_events

    def execute(
        self,
        requesting_user_id: uuid.UUID,
        target_session_id: uuid.UUID,
        is_staff_override: bool = False,
    ) -> None:
        session = self._session_repo.get_by_id(target_session_id)
        if session is None:
            raise ResourceNotFound("Session not found.")
        if not is_staff_override and session.user_id != requesting_user_id:
            raise PermissionDenied("You may only revoke your own sessions.")

        self._session_repo.revoke(target_session_id)

        revoked_by = requesting_user_id if is_staff_override and requesting_user_id != session.user_id else None
        self._stage_events(
            [("SessionRevoked", SessionRevoked(user_id=session.user_id, session_id=session.id, revoked_by=revoked_by).to_payload())]
        )

        audit = AuditEventBuilder(context_schema="identity", actor_id=str(requesting_user_id))
        audit.updated(
            entity_type="UserSession", entity_id=str(target_session_id),
            before={"is_active": True}, after={"is_active": False},
        )
