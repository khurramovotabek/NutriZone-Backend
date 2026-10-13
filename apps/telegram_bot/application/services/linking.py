"""
Telegram customer linking -- Phase 15B foundation.

## Design decisions, evidenced

- Operates on `apps.identity.infrastructure.models.User` directly
  (the real, existing customer model) rather than threading a new
  concern through the full domain aggregate/repository -- justified
  because `telegram_user_id`/`telegram_linked_at` are pure identity-
  linking metadata, not fields with business invariants the domain
  needs to protect (matching this project's own established
  convention of direct ORM access for narrow infrastructure concerns,
  e.g. every existing outbox subscriber in apps/notifications).
- Reuses `_assign_default_customer_role`'s own established pattern
  (Phase 09.4b) for a brand-new user, via the same seeded "customer"
  Role -- no duplicate role-bootstrapping logic.
- Never trusts a client-supplied phone number as already
  contact-verified: the caller (the webhook handler) must have
  already confirmed `contact.user_id == update.from_user.id`
  (Telegram's own native proof of ownership) before this service is
  ever invoked -- this service's own docstring states that
  precondition explicitly since it cannot re-verify it itself.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.identity.domain.value_objects import PhoneNumber


@dataclass(frozen=True, slots=True)
class LinkResult:
    user_id: uuid.UUID
    full_name: str
    is_new_customer: bool
    already_linked_to_this_telegram_account: bool


class TelegramIdentityAlreadyLinkedToAnotherUser(Exception):
    """The telegram_user_id is already linked to a different NutriZone account -- refuses to silently re-link, which would let one Telegram identity hijack a second account."""


class LinkTelegramCustomer:
    """
    Precondition the caller MUST already have verified: the phone
    number was submitted via Telegram's own native contact-sharing
    mechanism, and `contact.user_id == update.from_user.id` (i.e. the
    Telegram user proved they own the phone number being submitted,
    not submitted someone else's contact card). This service does not
    and cannot re-verify that itself -- it only performs the
    find-or-create/link step once that proof is established.
    """

    def execute(self, telegram_user_id: int, phone_number_raw: str, full_name: str, language: str | None = None) -> LinkResult:
        from apps.identity.infrastructure import models as identity_orm

        phone_number = PhoneNumber(phone_number_raw)

        existing_link = identity_orm.User.objects.filter(telegram_user_id=telegram_user_id).first()
        if existing_link is not None:
            if existing_link.phone_number != phone_number.value:
                raise TelegramIdentityAlreadyLinkedToAnotherUser(
                    "This Telegram account is already linked to a different NutriZone customer."
                )
            return LinkResult(user_id=existing_link.id, full_name=existing_link.full_name, is_new_customer=False, already_linked_to_this_telegram_account=True)

        with transaction.atomic():
            user = identity_orm.User.objects.filter(phone_number=phone_number.value).first()
            is_new = user is None

            if user is None:
                from apps.identity.infrastructure.composition import _assign_default_customer_role

                user = identity_orm.User.objects.create(
                    id=uuid.uuid4(), phone_number=phone_number.value, full_name=full_name or "", status="active",
                    telegram_user_id=telegram_user_id, telegram_linked_at=django_timezone.now(),
                    language=language or "uz",  # Real, business-required capability: the language the user picked during onboarding, when available; falls back to the existing default otherwise.
                )
                _assign_default_customer_role(user.id)
            else:
                if user.telegram_user_id is not None and user.telegram_user_id != telegram_user_id:
                    raise TelegramIdentityAlreadyLinkedToAnotherUser(
                        "This phone number's NutriZone account is already linked to a different Telegram account."
                    )
                user.telegram_user_id = telegram_user_id
                user.telegram_linked_at = django_timezone.now()
                user.save(update_fields=["telegram_user_id", "telegram_linked_at"])

        return LinkResult(user_id=user.id, full_name=user.full_name, is_new_customer=is_new, already_linked_to_this_telegram_account=False)


class ResolveTelegramCustomer:
    """The identity resolver every subsequent authenticated Telegram operation (catalog, cart, checkout) must go through -- rejects an unlinked telegram_user_id rather than allowing anonymous access to customer-scoped operations."""

    def execute(self, telegram_user_id: int) -> uuid.UUID | None:
        from apps.identity.infrastructure import models as identity_orm

        user = identity_orm.User.objects.filter(telegram_user_id=telegram_user_id).first()
        return user.id if user else None
