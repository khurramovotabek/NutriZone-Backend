"""
Chat Application Services -- Conversation lifecycle.

`Conversation.open()` (domain factory) already existed, fully built
and correct, including its own explicit business rule that a support
conversation may legitimately start with only the initiating customer
(no operator required at creation time). This orchestrates it; it
does not reinvent it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from django.db import transaction

from apps.chat.application.services._shared import ChatServiceContext
from apps.chat.application.ports import ConversationRepository
from apps.chat.domain.aggregates import Conversation
from apps.chat.domain.enums import ConversationType, ParticipantRole


class OpenConversation:
    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, opened_by: uuid.UUID, conversation_type: ConversationType, opener_role: ParticipantRole) -> Conversation:
        conversation, event = Conversation.open(
            conversation_id=uuid.uuid4(), conversation_type=conversation_type, opened_by=opened_by,
            opener_role=opener_role, at=datetime.now(timezone.utc),
        )

        # The state-change write and its outbox event must commit
        # together atomically (MIC §7) -- a real, live-verified bug
        # found here (and identically across every other service in
        # this file): stage_events() asserts an active atomic block
        # must already be open, but none of these methods had one at
        # all, so every real call crashed with a 500.
        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ConversationOpened", event.to_payload())])

        self._ctx.audit().created(entity_type="Conversation", entity_id=str(saved.id), after={"conversation_type": conversation_type.value, "opened_by": str(opened_by)})
        self._ctx.metric("chat_conversations_opened_total")
        return saved


class OpenStoreConversation:
    """
    The one, safe, customer-initiated exception to "adding a
    participant is a staff-only action" (`AddParticipant` above,
    gated by `chat.conversation.manage`): a customer messaging a
    store whose products/profile they can already see is not a
    privileged action, so this does not reuse `AddParticipant`'s
    permission at all -- it has its own, deliberately open one
    (`CanOpenStoreConversation`, permissions.py). Finds an existing
    OPEN `CUSTOMER_SALES` conversation between this exact
    (customer, store-owner) pair first, so repeat visits continue one
    real thread instead of spawning a new one every time -- reuses
    `ConversationRepository.list_for_user` (already certified,
    already used by the read side) rather than adding new repository
    surface for this.
    """

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, customer_id: uuid.UUID, store_owner_id: uuid.UUID, store_id: uuid.UUID | None = None) -> Conversation:
        existing, _total = self._conversation_repo.list_for_user(user_id=customer_id, status="open", page=1, page_size=200)
        for candidate in existing:
            if candidate.conversation_type != ConversationType.CUSTOMER_SALES:
                continue
            participant_ids = {p.user_id for p in candidate.participants.values() if p.is_active}
            if customer_id in participant_ids and store_owner_id in participant_ids:
                # Self-healing backfill: a conversation opened before `store_id`
                # existed on this aggregate has none recorded -- once we know it
                # (the caller always resolves it fresh from the store_id URL
                # segment), persist it now so every later read benefits too.
                if candidate.store_id is None and store_id is not None:
                    candidate.store_id = store_id
                    self._conversation_repo.save(candidate)
                return candidate

        conversation, opened_event = Conversation.open(
            conversation_id=uuid.uuid4(), conversation_type=ConversationType.CUSTOMER_SALES, opened_by=customer_id,
            opener_role=ParticipantRole.CUSTOMER, at=datetime.now(timezone.utc), store_id=store_id,
        )
        added_event = conversation.add_participant(user_id=store_owner_id, role=ParticipantRole.OPERATOR, at=datetime.now(timezone.utc))

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ConversationOpened", opened_event.to_payload()), ("ParticipantAdded", added_event.to_payload())])

        self._ctx.audit().created(entity_type="Conversation", entity_id=str(saved.id), after={"conversation_type": "customer_sales", "customer_id": str(customer_id), "store_owner_id": str(store_owner_id)})
        self._ctx.metric("chat_conversations_opened_total")
        return saved


class AddParticipant:
    """
    Role validation (`ParticipantPolicy.is_role_valid_for_conversation_type`)
    and duplicate-active-participant rejection
    (`ParticipantAlreadyExists`) both already exist inside
    `Conversation.add_participant()` -- not duplicated here. This
    service's own job is exactly what `SendMessage`/`OpenConversation`
    do: load, invoke the domain method, persist, stage the event.
    """

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID, user_id: uuid.UUID, role: ParticipantRole) -> Conversation:
        from common.exceptions import ResourceNotFound

        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")

        event = conversation.add_participant(user_id=user_id, role=role, at=datetime.now(timezone.utc))

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ParticipantAdded", event.to_payload())])

        self._ctx.audit().created(entity_type="Participant", entity_id=str(event.participant_id), after={"conversation_id": str(conversation_id), "user_id": str(user_id), "role": role.value})
        self._ctx.metric("chat_participants_added_total")
        return saved


class RemoveParticipant:
    """`ParticipantNotFound` (not an active participant) already exists inside `Conversation.remove_participant()` -- not duplicated here."""

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> Conversation:
        from common.exceptions import ResourceNotFound

        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")

        event = conversation.remove_participant(user_id=user_id, at=datetime.now(timezone.utc))

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ParticipantRemoved", event.to_payload())])

        self._ctx.audit().updated(entity_type="Participant", entity_id=str(event.participant_id), before={}, after={"removed": True, "conversation_id": str(conversation_id)})
        self._ctx.metric("chat_participants_removed_total")
        return saved


class AssignOperator:
    """Reassignment is explicitly supported, not an error case -- Conversation.assign_operator()'s own established behavior, unchanged."""

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID, operator_user_id: uuid.UUID) -> Conversation:
        from common.exceptions import ResourceNotFound

        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")

        event = conversation.assign_operator(operator_user_id)

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ConversationAssigned", event.to_payload())])

        self._ctx.audit().updated(entity_type="Conversation", entity_id=str(conversation_id), before={}, after={"assigned_operator_id": str(operator_user_id)})
        self._ctx.metric("chat_conversations_assigned_total")
        return saved


class CloseConversation:
    """InvalidConversationTransition (only OPEN conversations can close) already exists inside Conversation.close() -- not duplicated here."""

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID) -> Conversation:
        from common.exceptions import ResourceNotFound

        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")

        event = conversation.close()

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ConversationClosedEvent", event.to_payload())])

        self._ctx.audit().updated(entity_type="Conversation", entity_id=str(conversation_id), before={}, after={"status": "closed"})
        self._ctx.metric("chat_conversations_closed_total")
        return saved


class ReopenConversation:
    """InvalidConversationTransition (only CLOSED conversations can reopen; ARCHIVED is terminal) already exists inside Conversation.reopen() -- not duplicated here."""

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID) -> Conversation:
        from common.exceptions import ResourceNotFound

        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")

        event = conversation.reopen()

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ConversationReopened", event.to_payload())])

        self._ctx.audit().updated(entity_type="Conversation", entity_id=str(conversation_id), before={}, after={"status": "open"})
        self._ctx.metric("chat_conversations_reopened_total")
        return saved


class ArchiveConversation:
    """InvalidConversationTransition (already-archived rejection) already exists inside Conversation.archive() -- not duplicated here."""

    def __init__(self, conversation_repo: ConversationRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID) -> Conversation:
        from common.exceptions import ResourceNotFound

        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")

        event = conversation.archive()

        with transaction.atomic():
            saved = self._conversation_repo.save(conversation)
            self._ctx.stage_events([("ConversationArchivedEvent", event.to_payload())])

        self._ctx.audit().updated(entity_type="Conversation", entity_id=str(conversation_id), before={}, after={"status": "archived"})
        self._ctx.metric("chat_conversations_archived_total")
        return saved
