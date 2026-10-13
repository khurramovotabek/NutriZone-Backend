"""
POS domain validators -- thin, intention-revealing wrappers over
value object constructors, matching every prior module's
domain/validators.py pattern.

**No `MoneyValidator` exists here** -- `Money` is the Shared Kernel's
own primitive; POS does not own its construction/validation logic and
must not wrap it a second time.
"""
from __future__ import annotations

from apps.pos.domain.value_objects import Quantity


def QuantityValidator(value: int) -> Quantity:  # noqa: N802
    return Quantity(value)
