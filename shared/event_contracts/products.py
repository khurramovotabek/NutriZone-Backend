"""
Products' Domain Event Catalogue registration.

Imported once from `apps/products/apps.py::ProductsConfig.ready()` --
importing this module IS the act of registering these fifteen event
contracts against `core.events.registry.registry`, per MIC §7's
"payload shape must be registered in shared/event_contracts/ before
the emitting code is written" rule -- matching
`shared/event_contracts/identity.py`'s exact pattern.
"""
from __future__ import annotations

from apps.products.domain.events import (
    BrandAssigned,
    CategoryAssigned,
    CertificateAttached,
    ProductArchived,
    ProductCreated,
    ProductDeleted,
    ProductHidden,
    ProductMediaDeleted,
    ProductMediaUploaded,
    ProductPublished,
    ProductRestored,
    ProductSEOUpdated,
    ProductUpdated,
    ProductVariantCreated,
    ProductVariantDeleted,
    ProductVariantUpdated,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("ProductCreated", ProductCreated),
    ("ProductUpdated", ProductUpdated),
    ("ProductPublished", ProductPublished),
    ("ProductHidden", ProductHidden),
    ("ProductArchived", ProductArchived),
    ("ProductRestored", ProductRestored),
    ("ProductDeleted", ProductDeleted),
    ("BrandAssigned", BrandAssigned),
    ("CategoryAssigned", CategoryAssigned),
    ("ProductVariantCreated", ProductVariantCreated),
    ("ProductVariantUpdated", ProductVariantUpdated),
    ("ProductVariantDeleted", ProductVariantDeleted),
    ("ProductMediaUploaded", ProductMediaUploaded),
    ("ProductMediaDeleted", ProductMediaDeleted),
    ("ProductSEOUpdated", ProductSEOUpdated),
    ("CertificateAttached", CertificateAttached),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="products", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
