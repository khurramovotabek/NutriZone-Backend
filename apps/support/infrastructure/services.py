"""Support desk operations: every change goes through here (and leaves a note), never straight model writes."""
from __future__ import annotations

import re

from django.db import transaction
from django.utils import timezone

from apps.support.infrastructure.models import OPEN_STATUSES, CaseStatus, SupportCase, SupportNote, SupportProfile


class SupportError(Exception):
    pass


def normalize_phone(raw: str) -> str:
    """Uzbek numbers as typed by staff ("90 123 45 67", "8 90...", "998901234567") → +998901234567."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 10 and digits.startswith("8"):
        digits = "998" + digits[1:]
    if not re.fullmatch(r"998\d{9}", digits):
        raise SupportError(f"Telefon raqami noto'g'ri: {raw}. Masalan: +998 90 123 45 67")
    return "+" + digits


def customer_for(phone: str, name: str = "") -> tuple:
    """The customer with this phone -- created (and marked as made by support) when unknown. Returns (user, created)."""
    import uuid

    from apps.identity.infrastructure.composition import _assign_default_customer_role
    from apps.identity.infrastructure.models import User

    user = User.all_objects.filter(phone_number=phone).first()  # a soft-deleted account still owns the number (unique)
    if user is not None and user.is_deleted:
        User.all_objects.filter(pk=user.pk).update(is_deleted=False, deleted_at=None, deleted_by=None)
        user.refresh_from_db()
    if user is not None:
        if name and not user.full_name.strip():
            User.objects.filter(pk=user.pk).update(full_name=name.strip()[:255])
            user.full_name = name.strip()
        return user, False
    user = User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name=name.strip()[:255], status="active", language="uz")
    _assign_default_customer_role(user.id)
    SupportProfile.objects.create(user=user)
    return user, True


def _next_number() -> str:
    last = SupportCase.objects.select_for_update().order_by("-created_at").values_list("number", flat=True).first()
    n = int(last.split("-")[1]) + 1 if last and "-" in last and last.split("-")[1].isdigit() else 1
    while SupportCase.objects.filter(number=f"SUP-{n:05d}").exists():
        n += 1
    return f"SUP-{n:05d}"


@transaction.atomic
def create_case(*, phone: str, name: str = "", summary: str, topic: str = "product", channel: str = "call_in", status: str = CaseStatus.NEW,
                priority: str = "normal", next_contact_at=None, staff: str = "", products=()) -> SupportCase:
    if not (summary or "").strip():
        raise SupportError("Suhbat mazmunini yozing.")
    phone = normalize_phone(phone)
    user, created = customer_for(phone, name)
    case = SupportCase.objects.create(
        number=_next_number(), customer=user, phone=phone, name=(name or user.full_name or "").strip()[:120], summary=summary.strip(),
        topic=topic, channel=channel, status=status, priority=priority, next_contact_at=next_contact_at, created_by=staff, assigned_to=staff,
        closed_at=None if status in OPEN_STATUSES else timezone.now(),
    )
    if products:
        case.products.set(products)
    SupportNote.objects.create(case=case, kind="call", text=summary.strip(), author=staff)
    if created:
        SupportNote.objects.create(case=case, kind="status", text="Yangi mijoz akkaunti yaratildi (telefon raqami bo'yicha).", author=staff)
    return case


@transaction.atomic
def move(case: SupportCase, status: str, staff: str = "", note: str = "") -> SupportCase:
    if status not in CaseStatus.values:
        raise SupportError("Noma'lum holat.")
    case = SupportCase.objects.select_for_update().get(pk=case.pk)
    if case.status == status and not note:
        return case
    old = case.get_status_display()
    case.status = status
    case.closed_at = None if status in OPEN_STATUSES else (case.closed_at or timezone.now())
    if status == CaseStatus.CALLBACK and not case.next_contact_at:
        case.next_contact_at = timezone.now() + timezone.timedelta(days=1)
    case.save(update_fields=["status", "closed_at", "next_contact_at", "updated_at"])
    SupportNote.objects.create(case=case, kind="status", text=f"{old} → {case.get_status_display()}" + (f": {note}" if note else ""), author=staff)
    return case


def add_note(case: SupportCase, text: str, staff: str = "", kind: str = "note") -> SupportNote:
    if not (text or "").strip():
        raise SupportError("Izoh bo'sh.")
    note = SupportNote.objects.create(case=case, kind=kind, text=text.strip(), author=staff)
    SupportCase.objects.filter(pk=case.pk).update(updated_at=timezone.now())
    return note


def pending_confirmation(user) -> SupportProfile | None:
    """The staff-made profile the bot should ask this customer to confirm (None when there's nothing to confirm)."""
    return SupportProfile.objects.filter(user=user, created_by_support=True, confirmed_at__isnull=True).first()


def confirm_profile(user, full_name: str | None = None) -> None:
    from apps.identity.infrastructure.models import User

    if full_name and full_name.strip():
        User.objects.filter(pk=user.pk).update(full_name=full_name.strip()[:255])
    SupportProfile.objects.filter(user=user).update(confirmed_at=timezone.now())
