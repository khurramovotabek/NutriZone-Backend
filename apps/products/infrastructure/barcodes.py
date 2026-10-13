"""
One place that turns a scanned code into a product variant: the variant's main barcode, then its extra (batch)
barcodes (`ProductVariantBarcode`), then the SKU. Every scanner in the system -- Kirim, transfers, both POS
terminals, catalogue search, the Excel import -- goes through here, so a new batch barcode works everywhere at once.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import Q

CODE_RE = re.compile(r"^[0-9A-Za-z\-]{4,32}$")


@dataclass(frozen=True)
class Match:
    variant: object
    barcode: str = ""        # the code that matched
    is_extra: bool = False   # matched an extra (batch) barcode rather than the main one / SKU
    batch: str = ""
    expires_at: object = None


def normalize(code) -> str:
    code = str(code or "").strip()
    return code[:-2] if code.endswith(".0") and code[:-2].isdigit() else code  # Excel turns long barcodes into floats


def gs1_gtin(code: str) -> str | None:
    """A 2D (DataMatrix / "Asl belgisi") scan: "01" + GTIN-14 + "21" + a per-unit serial... -> the GTIN-14.
    Scanners may prefix the AIM id "]d2" and separate fields with the GS character (\x1d)."""
    raw = code.replace("]d2", "", 1).replace("]C1", "", 1).lstrip("\x1d")
    if len(raw) >= 16 and raw.startswith("01") and raw[2:16].isdigit():
        return raw[2:16]
    return None


def _gtin_forms(gtin14: str) -> list[str]:
    """GTIN-14 "04780012345678" is the same item as EAN-13 "4780012345678" (and UPC-A with two leading zeros)."""
    forms = [gtin14]
    if gtin14.startswith("0"):
        forms.append(gtin14[1:])
    if gtin14.startswith("00"):
        forms.append(gtin14[2:])
    return forms


def resolve(code) -> Match | None:
    from apps.products.infrastructure.models import ProductVariant, ProductVariantBarcode

    code = normalize(code)
    if not code:
        return None
    gtin = gs1_gtin(code)
    if gtin:  # a marked unit: match the product by its GTIN, whatever the unit serial is
        for form in _gtin_forms(gtin):
            m = resolve(form)
            if m is not None:
                return m
        return None
    variant = ProductVariant.objects.filter(barcode=code).order_by("-status").first()
    if variant is not None:
        return Match(variant, code)
    extra = ProductVariantBarcode.objects.filter(barcode=code, is_active=True, variant__is_deleted=False).select_related("variant").first()
    if extra is not None:
        return Match(extra.variant, code, True, extra.batch, extra.expires_at)
    variant = ProductVariant.objects.filter(sku__iexact=code).order_by("-status").first()
    return Match(variant, code) if variant is not None else None


def barcode_q(code: str, prefix: str = "") -> Q:
    """Q matching variants (or rows related to a variant via `prefix`, e.g. "product_variant__") by any of their barcodes."""
    return Q(**{f"{prefix}barcode": code}) | Q(**{f"{prefix}extra_barcodes__barcode": code, f"{prefix}extra_barcodes__is_active": True})


def barcode_contains_q(q: str, prefix: str = "") -> Q:
    return Q(**{f"{prefix}barcode__icontains": q}) | Q(**{f"{prefix}extra_barcodes__barcode__icontains": q})


def owner_of(code: str, exclude_extra_id=None):
    """Who already uses this barcode (a variant as main barcode, or an extra barcode row) -- for uniqueness checks."""
    from apps.products.infrastructure.models import ProductVariant, ProductVariantBarcode

    code = normalize(code)
    v = ProductVariant.all_objects.filter(barcode=code).first()
    if v is not None:
        return v
    qs = ProductVariantBarcode.objects.filter(barcode=code)
    if exclude_extra_id:
        qs = qs.exclude(pk=exclude_extra_id)
    row = qs.select_related("variant").first()
    return row.variant if row else None


def attach(variant, code: str, *, batch: str = "", expires_at=None, note: str = "", actor: str = ""):
    """Adds an extra barcode to a variant. Raises ValueError (Uzbek message) if it's malformed or already taken."""
    from apps.products.infrastructure.models import ProductVariantBarcode

    code = normalize(code)
    if not CODE_RE.match(code):
        raise ValueError("Shtrix-kod 4–32 ta harf/raqamdan iborat bo'lishi kerak.")
    owner = owner_of(code)
    if owner is not None:
        if owner.pk == variant.pk:
            raise ValueError("Bu shtrix-kod allaqachon shu mahsulotga biriktirilgan.")
        raise ValueError(f"Bu shtrix-kod boshqa mahsulotda ishlatilgan ({owner.sku}).")
    return ProductVariantBarcode.objects.create(variant=variant, barcode=code, batch=(batch or "")[:64], expires_at=expires_at or None, note=(note or "")[:120], added_by=(actor or "")[:150])
