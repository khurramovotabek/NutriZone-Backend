"""
UUID utilities.

UUIDv7 is preferred over UUIDv4 for primary keys throughout the platform
(Enterprise Database Blueprint §1.3/§18): it is time-ordered, which keeps
B-tree index locality under high insert concurrency on tables like
`orders`, `wallet_ledger_entries`, and `notifications`. Python 3.13's
stdlib `uuid` module does not yet provide UUIDv7 directly, so a small
RFC 9562-compatible implementation is provided here as the single
generation point every model's `default=` should reference (rather than
`uuid.uuid4` directly) once this becomes the platform standard.
"""
from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Generate an RFC 9562 UUIDv7 (time-ordered)."""
    unix_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits
    rand_bytes = os.urandom(10)

    time_bytes = unix_ms.to_bytes(6, byteorder="big")

    # Version (7) in the high nibble of byte 6, low nibble from random.
    byte6 = 0x70 | (rand_bytes[0] & 0x0F)
    # Variant (10xx) in the high bits of byte 8.
    byte8 = 0x80 | (rand_bytes[2] & 0x3F)

    uuid_bytes = (
        time_bytes
        + bytes([byte6, rand_bytes[1]])
        + bytes([byte8, rand_bytes[3]])
        + rand_bytes[4:10]
    )
    return uuid.UUID(bytes=uuid_bytes)


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
