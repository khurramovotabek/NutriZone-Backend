"""
Django AppConfig for the `chat` bounded context.

Maps 1:1 to Domain Architecture Specification 2.12 and to the
`chat` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    label = "chat"
    verbose_name = _("Chat")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern. Local imports inside `ready()`
        are a genuine Django framework requirement (the app registry
        is not populated at module-import time), not a style choice.
        """
        from apps.chat.infrastructure import inbox_notify  # noqa: F401 -- new message -> notification bell
        from apps.chat.infrastructure import automation  # noqa: F401 -- out-of-hours auto-reply, rating request on close

        from apps.chat.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import chat as chat_event_contracts  # noqa: F401

        from apps.chat.infrastructure.health import (
            check_chat_cache,
            check_chat_outbox_backlog,
            check_chat_repository,
            check_composition_integrity,
            check_message_content_integrity,
            check_orphaned_participants,
        )
        from core.health.registry import register_module_check

        register_module_check("chat_repository", check_chat_repository)
        register_module_check("chat_outbox_backlog", check_chat_outbox_backlog)
        register_module_check("chat_orphaned_participants", check_orphaned_participants)
        register_module_check("chat_message_content_integrity", check_message_content_integrity)
        register_module_check("chat_composition_integrity", check_composition_integrity)
        register_module_check("chat_cache", check_chat_cache)
