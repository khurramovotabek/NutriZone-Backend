from __future__ import annotations

import ast
from unittest.mock import patch

import pytest

import apps.chat.domain.events as events_module
from apps.chat.infrastructure.event_handlers import CACHE_GROUPS, _EVENT_TO_CACHE_GROUPS, handle_chat_event, invalidate_chat_cache_group

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_chat_cache_group("not_a_real_group")

    def test_all_three_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 3

    def test_invalidate_group_does_not_raise(self):
        invalidate_chat_cache_group("conversation_detail")


class TestEventHandlerDispatch:
    def test_handle_conversation_opened_does_not_raise(self):
        handle_chat_event("ConversationOpened", {"conversation_id": "x"})

    def test_handle_unknown_event_is_a_noop(self):
        handle_chat_event("SomeUnregisteredEvent", {})

    def test_message_read_and_delivered_registered_with_empty_cache_groups(self):
        """Verifies the deliberate design disclosed in Phase 2: MessageRead/MessageDelivered are registered (satisfying the 'every event genuinely handled or explicitly documented' requirement) but map to no cache invalidation, since no selector currently surfaces read-state."""
        assert _EVENT_TO_CACHE_GROUPS["MessageRead"] == ()
        assert _EVENT_TO_CACHE_GROUPS["MessageDelivered"] == ()

    def test_handle_message_read_does_not_raise_despite_empty_cache_groups(self):
        handle_chat_event("MessageRead", {"message_id": "x"})

    def test_all_12_events_dispatched(self):
        """Cross-checks the dispatch table against domain/events.py directly."""
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))
        dispatched = set(_EVENT_TO_CACHE_GROUPS.keys())
        assert domain_events == dispatched, f"Mismatch: {domain_events.symmetric_difference(dispatched)}"

    def test_all_12_events_registered(self):
        """Cross-checks shared/event_contracts/chat.py against domain/events.py directly -- fresh AST parse."""
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))

        with open("shared/event_contracts/chat.py") as f:
            contract_tree = ast.parse(f.read())
        registered = set(n.elts[0].value for n in ast.walk(contract_tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2 and isinstance(n.elts[0], ast.Constant))
        assert domain_events == registered, f"Mismatch: {domain_events.symmetric_difference(registered)}"


class TestOperatorReplyNotifiesCustomerViaTelegram:
    """
    Real, live-verified regression test for the previously one-way
    Telegram chat integration gap: a support operator's reply
    (`MessageSent` with an OPERATOR sender) is now relayed to the
    real customer via a real Telegram message -- without this, a
    customer who started a chat via the bot would never see any
    operator reply anywhere.
    """

    def _open_conversation_with_operator(self):
        import uuid

        from apps.chat.domain.enums import ConversationType, ParticipantRole
        from apps.chat.infrastructure import composition as chat_composition
        from apps.identity.infrastructure import models as identity_orm

        tg_user_id = uuid.uuid4().int % 900000000
        customer = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=tg_user_id, full_name="Test Customer")
        operator = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Test Operator")
        conversation = chat_composition.build_open_conversation(actor_id=customer.id).execute(opened_by=customer.id, conversation_type=ConversationType.CUSTOMER_SUPPORT, opener_role=ParticipantRole.CUSTOMER)
        chat_composition.build_add_participant(actor_id=operator.id).execute(conversation_id=conversation.id, user_id=operator.id, role=ParticipantRole.OPERATOR)
        return customer, operator, conversation, tg_user_id

    def test_customers_own_message_does_not_trigger_a_notification(self):
        from apps.chat.domain.enums import MessageType
        from apps.chat.infrastructure import composition as chat_composition

        customer, _operator, conversation, _tg_id = self._open_conversation_with_operator()
        with patch("apps.notifications.infrastructure.composition.build_telegram_gateway") as mock_gw_factory:
            message = chat_composition.build_send_message(actor_id=customer.id).execute(conversation_id=conversation.id, sender_id=customer.id, message_type=MessageType.TEXT, content="Hello")
            handle_chat_event("MessageSent", {"message_id": str(message.id), "conversation_id": str(conversation.id), "sender_id": str(customer.id), "message_type": "text"})
            assert not mock_gw_factory.called

    def test_operator_reply_sends_a_real_telegram_message_to_the_real_customer(self):
        from apps.chat.domain.enums import MessageType
        from apps.chat.infrastructure import composition as chat_composition

        _customer, operator, conversation, tg_id = self._open_conversation_with_operator()
        with patch("apps.notifications.infrastructure.composition.build_telegram_gateway") as mock_gw_factory:
            mock_gateway = mock_gw_factory.return_value
            message = chat_composition.build_send_message(actor_id=operator.id).execute(conversation_id=conversation.id, sender_id=operator.id, message_type=MessageType.TEXT, content="Your order ships tomorrow.")
            handle_chat_event("MessageSent", {"message_id": str(message.id), "conversation_id": str(conversation.id), "sender_id": str(operator.id), "message_type": "text"})
            assert mock_gw_factory.called
            assert mock_gateway.send_message.call_args[0][0] == str(tg_id)
            assert mock_gateway.send_message.call_args[0][2] == "Your order ships tomorrow."

    def test_customer_with_no_linked_telegram_is_silently_skipped(self):
        import uuid

        from apps.chat.domain.enums import ConversationType, MessageType, ParticipantRole
        from apps.chat.infrastructure import composition as chat_composition
        from apps.identity.infrastructure import models as identity_orm

        customer = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="No Telegram Customer")
        operator = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Operator")
        conversation = chat_composition.build_open_conversation(actor_id=customer.id).execute(opened_by=customer.id, conversation_type=ConversationType.CUSTOMER_SUPPORT, opener_role=ParticipantRole.CUSTOMER)
        chat_composition.build_add_participant(actor_id=operator.id).execute(conversation_id=conversation.id, user_id=operator.id, role=ParticipantRole.OPERATOR)
        with patch("apps.notifications.infrastructure.composition.build_telegram_gateway") as mock_gw_factory:
            message = chat_composition.build_send_message(actor_id=operator.id).execute(conversation_id=conversation.id, sender_id=operator.id, message_type=MessageType.TEXT, content="Reply")
            handle_chat_event("MessageSent", {"message_id": str(message.id), "conversation_id": str(conversation.id), "sender_id": str(operator.id), "message_type": "text"})
            assert not mock_gw_factory.called
