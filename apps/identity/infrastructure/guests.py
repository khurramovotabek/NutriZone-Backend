"""
Guest customers: someone who orders with just a typed name + phone, without signing in.

- `find_or_create(phone, name)` -- the account the order is placed for. A number nobody has yet gets a new guest
  account (is_guest=True, default customer role) and the caller may hand its browser a session (`issue_session`), so
  the order page, online payment and the next order work as usual. A number that already has an account gets the
  order on that account, but NEVER a session: typing a number proves nothing.
- `claim(user_id)` -- the number's real owner signed in (Telegram contact / bot code / OTP): the account stops being a
  guest and every session the guest browser held is revoked.
- Guests earn no coins (loyalty/services.award_order_detailed, signup_bonus) -- signing up is what unlocks cashback.
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction

from apps.identity.domain.phone import parse_uz_phone


class GuestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_guest(user_id) -> bool:
    if not user_id:
        return False
    from apps.identity.infrastructure.models import User

    return User.all_objects.filter(pk=user_id, is_guest=True).exists()


def find_or_create(phone_raw: str, full_name: str, language: str = "uz"):
    """(user, created) for the typed phone; raises GuestError for an unreadable number or a blocked account."""
    from apps.identity.infrastructure.composition import _assign_default_customer_role
    from apps.identity.infrastructure.models import User

    phone = parse_uz_phone(phone_raw)
    if not phone:
        raise GuestError("INVALID_PHONE", "Telefon raqamini to'g'ri kiriting, masalan: 94 205 20 40.")
    name = " ".join((full_name or "").split())[:255]
    if len(name) < 2:
        raise GuestError("NAME_REQUIRED", "Ismingizni kiriting.")
    user = User.all_objects.filter(phone_number=phone).first()
    if user is not None:
        if user.status == "blocked":
            raise GuestError("ACCOUNT_BLOCKED", "Bu raqam bilan buyurtma berib bo'lmaydi. Iltimos, biz bilan bog'laning.")
        if user.is_deleted:
            User.all_objects.filter(pk=user.pk).update(is_deleted=False, deleted_at=None, deleted_by=None)
            user.refresh_from_db()
        if not (user.full_name or "").strip():
            User.all_objects.filter(pk=user.pk).update(full_name=name)
            user.full_name = name
        return user, False
    try:
        with transaction.atomic():
            user = User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name=name, status="pending_verification", is_guest=True,
                                       language=language if language in ("uz", "ru", "en") else "uz")
            _assign_default_customer_role(user.id)
    except IntegrityError:  # the same number submitted twice at once
        return User.all_objects.get(phone_number=phone), False
    return user, True


def issue_session(user, request) -> dict:
    """A token pair for a guest account this request just created (never for an existing account)."""
    from apps.identity.application.services.auth import IssueAuthenticationForUser
    from apps.identity.infrastructure.composition import stage_identity_events
    from apps.identity.infrastructure.repositories import DjangoUserRepository, DjangoUserSessionRepository
    from apps.identity.infrastructure.security import SimpleJWTTokenIssuer
    from apps.identity.interfaces.api.v1.views import _build_device_context

    domain_user = DjangoUserRepository().get_by_id(user.id)
    with transaction.atomic():  # the session row and its outbox events commit together (stage_event demands it)
        result = IssueAuthenticationForUser(DjangoUserSessionRepository(), SimpleJWTTokenIssuer(), stage_identity_events).execute(
            domain_user, _build_device_context(request), provider_type="phone_otp", is_new_user=True)
    return {"access_token": result.access_token, "refresh_token": result.refresh_token, "session_id": str(result.session_id), "is_new_user": True}


def claim(user_id) -> bool:
    """The number's owner proved it: no longer a guest, the guest browser's sessions end. True when it was a guest."""
    from apps.identity.infrastructure.models import User

    if not user_id or not User.all_objects.filter(pk=user_id, is_guest=True).update(is_guest=False, status="active"):
        return False
    try:
        from apps.identity.infrastructure.composition import build_logout_all

        build_logout_all().execute(user_id)
    except Exception:  # noqa: BLE001 - claiming must never block a sign-in
        import logging

        logging.getLogger("nutrizone.app").exception("guests.claim: could not revoke guest sessions of %s", user_id)
    return True
