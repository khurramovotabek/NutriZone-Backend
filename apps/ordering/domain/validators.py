"""
Ordering domain validators -- thin, intention-revealing wrappers over
value object constructors, matching every prior module's
domain/validators.py pattern.
"""
from __future__ import annotations

from apps.ordering.domain.value_objects import AddressSnapshot, OrderNote, OrderNumber, ReturnNumber, TrackingNumber


def OrderNumberValidator(value: str) -> OrderNumber:  # noqa: N802
    return OrderNumber(value)


def ReturnNumberValidator(value: str) -> ReturnNumber:  # noqa: N802
    return ReturnNumber(value)


def TrackingNumberValidator(value: str) -> TrackingNumber:  # noqa: N802
    return TrackingNumber(value)


def OrderNoteValidator(text: str) -> OrderNote:  # noqa: N802
    return OrderNote(text)


def AddressSnapshotValidator(recipient_name: str, line1: str, city: str, country_code: str, **kwargs) -> AddressSnapshot:  # noqa: N802
    return AddressSnapshot(recipient_name=recipient_name, line1=line1, city=city, country_code=country_code, **kwargs)
