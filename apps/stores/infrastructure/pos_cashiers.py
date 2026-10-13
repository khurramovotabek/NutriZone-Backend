"""
Kassas and cashiers.

* **Kassa PIN** -- one shared 4-6 digit PIN per kassa (Store.pos_pin_hash, a Django password hash). It is asked when
  a shift is opened and when another cashier takes over the terminal. 5 wrong PINs in a row lock the kassa for
  LOCK_MINUTES. A kassa without a PIN can't be opened (a superadmin sets it on Dashboard → POS → Kassirlar).
* **Cashiers** -- customer accounts (identity.User) linked to ONE kassa (StoreCashier). The store's owner may always
  sell at their own kassa. A cashier signs in to the storefront with their own account; "My store" resolves to the
  kassa they are linked to (`store_for_user`).
* **Hand-over** -- several cashiers can share one computer: the next cashier picks their name and types the kassa
  PIN; the terminal then carries a signed token (header X-Pos-Cashier) and every sale is recorded under that cashier
  until the terminal is handed over again (`issue_token` / `cashier_from_token`).
* **Online kassa** -- the Dashboard's own till sells online orders from the main warehouse (`online_kassa`).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import transaction
from django.utils import timezone

from common.exceptions import ConflictError, ValidationFailed

MAX_ATTEMPTS = 5
LOCK_MINUTES = 5
TOKEN_SALT = "nz-pos-cashier"
TOKEN_MAX_AGE = 16 * 3600  # a hand-over lasts at most one long working day
ONLINE_KASSA_NAME = "Onlayn kassa"


def _err(code: str, message: str, **details) -> ConflictError:
    e = ConflictError(message, details=details)
    e.code = code
    return e


# ---------------------------------------------------------------- kassa PIN


PIN_ERRORS = {  # code → the Uzbek text the dashboard shows
    "PIN_FORMAT": "PIN 4–6 ta raqamdan iborat bo'lishi kerak.",
    "PIN_TOO_SIMPLE": "Bu PIN juda oson topiladi (1111, 1234, 4321 kabi). Boshqa raqamlar tanlang.",
    "PIN_MISMATCH": "Ikki PIN bir xil emas — qaytadan kiriting.",
}


def valid_pin(pin: str) -> str:
    pin = str(pin or "").strip()
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        err = ValidationFailed("The PIN must be 4 to 6 digits.")
        err.code = "PIN_FORMAT"
        raise err
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
        err = ValidationFailed("Choose a less obvious PIN (not 1111 or 1234).")
        err.code = "PIN_TOO_SIMPLE"
        raise err
    return pin


def has_pin(store) -> bool:
    return bool(store.pos_pin_hash)


def set_pin(store, pin: str) -> None:
    from apps.stores.infrastructure.models import Store

    hashed = make_password(valid_pin(pin))
    now = timezone.now()
    Store.objects.filter(pk=store.pk).update(pos_pin_hash=hashed, pos_pin_changed_at=now, pos_pin_failed=0, pos_pin_locked_until=None)
    store.pos_pin_hash, store.pos_pin_changed_at, store.pos_pin_failed, store.pos_pin_locked_until = hashed, now, 0, None


def locked_seconds(store) -> int:
    now = timezone.now()
    return int((store.pos_pin_locked_until - now).total_seconds()) if store.pos_pin_locked_until and store.pos_pin_locked_until > now else 0


def verify_pin(store, pin: str) -> None:
    """Raises KASSA_PIN_NOT_SET / PIN_LOCKED / PIN_WRONG (counting the attempt); returns quietly when the PIN is right."""
    from apps.stores.infrastructure.models import Store

    failure = None
    with transaction.atomic():
        row = Store.objects.select_for_update().only("id", "pos_pin_hash", "pos_pin_failed", "pos_pin_locked_until").get(pk=store.pk)
        if not row.pos_pin_hash:
            raise _err("KASSA_PIN_NOT_SET", "This kassa has no PIN yet -- ask the administrator to set it.")
        wait = locked_seconds(row)
        if wait:
            raise _err("PIN_LOCKED", "Too many wrong PINs -- try again in a few minutes.", seconds=wait)
        if check_password(str(pin or "").strip(), row.pos_pin_hash):
            if row.pos_pin_failed or row.pos_pin_locked_until:
                Store.objects.filter(pk=row.pk).update(pos_pin_failed=0, pos_pin_locked_until=None)
            return
        attempts = row.pos_pin_failed + 1
        if attempts >= MAX_ATTEMPTS:
            Store.objects.filter(pk=row.pk).update(pos_pin_failed=0, pos_pin_locked_until=timezone.now() + timedelta(minutes=LOCK_MINUTES))
            failure = _err("PIN_LOCKED", "Too many wrong PINs -- try again in a few minutes.", seconds=LOCK_MINUTES * 60)
        else:
            Store.objects.filter(pk=row.pk).update(pos_pin_failed=attempts)
            failure = _err("PIN_WRONG", "Wrong PIN.", left=MAX_ATTEMPTS - attempts)
    raise failure  # outside the atomic block, so the counted attempt is committed


# ---------------------------------------------------------------- cashiers


def cashiers(store):
    """Active cashier links of this kassa (with the user)."""
    from apps.stores.infrastructure.models import StoreCashier

    return StoreCashier.objects.filter(store=store, is_active=True, user__is_deleted=False).exclude(user__status="blocked").select_related("user").order_by("user__full_name")


def store_for_user(user_id):
    """(store, "owner" | "cashier") the user runs, or (None, None)."""
    from apps.stores.infrastructure.models import Store, StoreCashier

    store = Store.objects.filter(owner_id=user_id).exclude(kind="warehouse").order_by("created_at").first()
    if store:
        return store, "owner"
    link = StoreCashier.objects.filter(user_id=user_id, is_active=True).select_related("store").first()
    if link and link.store.kind != "warehouse":
        return link.store, "cashier"
    return None, None


def may_sell(store, user_id) -> bool:
    if not user_id:
        return False
    if store.owner_id and str(store.owner_id) == str(user_id):
        return True
    return cashiers(store).filter(user_id=user_id).exists()


def people(store) -> list[dict]:
    """Everyone who may sell at this kassa: the owner first, then the cashiers."""
    out, seen = [], set()
    if store.owner_id and store.owner and store.owner.status != "blocked" and not store.owner.is_deleted:
        out.append(_person(store.owner, "owner"))
        seen.add(store.owner_id)
    for link in cashiers(store):
        if link.user_id not in seen:
            out.append(_person(link.user, "cashier"))
            seen.add(link.user_id)
    return out


COLORS = ("#2563eb", "#059669", "#d97706", "#db2777", "#7c3aed", "#0891b2", "#dc2626", "#4f46e5")


def color_for(user_id) -> str:
    return COLORS[uuid.UUID(str(user_id)).int % len(COLORS)]


def initials(name: str) -> str:
    return "".join(p[0] for p in (name or "").split()[:2]).upper() or "?"


def _person(user, role: str) -> dict:
    name = user.full_name or user.phone_number or "—"
    return {"id": str(user.id), "full_name": name, "phone": user.phone_number, "role": role, "initials": initials(name), "color": color_for(user.id)}


def link(store, user, added_by: str = ""):
    """Links a customer account to this kassa (moving it from another kassa if needed) and tells the person."""
    from apps.stores.infrastructure.models import Store, StoreCashier

    if store.kind == "warehouse":
        raise ValidationFailed("The online kassa is run from the Dashboard -- link cashiers to a branch kassa.")
    if Store.objects.filter(owner_id=user.id).exclude(pk=store.pk).exists():
        raise ValidationFailed("This person owns another store -- an owner can't be a cashier elsewhere.")
    obj, created = StoreCashier.objects.update_or_create(user=user, defaults={"store": store, "is_active": True, "added_by": added_by[:150]})
    from apps.notifications.infrastructure.notify import notify

    notify(user.id, "cashier_added", {"store": store.name}, link="/profile/store/pos", dedupe_key=f"cashier_added:{obj.id}:{store.id}:{int(timezone.now().timestamp() // 60)}")
    return obj


def touch(store, user_id) -> None:
    """Remembers when a cashier last worked at the terminal (at most once a minute)."""
    from apps.stores.infrastructure.models import StoreCashier

    cutoff = timezone.now() - timedelta(minutes=1)
    StoreCashier.objects.filter(store=store, user_id=user_id).exclude(last_seen_at__gt=cutoff).update(last_seen_at=timezone.now())


# ---------------------------------------------------------------- hand-over token


def issue_token(store, user_id) -> str:
    return signing.dumps({"s": str(store.id), "u": str(user_id)}, salt=TOKEN_SALT, compress=True)


def cashier_from_token(store, token: str | None):
    """The cashier a valid hand-over token names (still allowed at this kassa), else None."""
    if not token:
        return None
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    if data.get("s") != str(store.id) or not may_sell(store, data.get("u")):
        return None
    return uuid.UUID(data["u"])


# ---------------------------------------------------------------- kassa naming / online kassa


def online_kassa():
    """The Dashboard's online till: the main warehouse online orders are packed from."""
    from apps.stores.infrastructure.online_fulfilment import fulfilment_store

    return fulfilment_store()


def kassa_name(store) -> str:
    if store is None:
        return ONLINE_KASSA_NAME
    return ONLINE_KASSA_NAME if store.kind == "warehouse" else store.name
