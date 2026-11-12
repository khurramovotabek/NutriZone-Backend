"""
Setting a location's stock to a counted number -- by hand on Ombor → Qoldiqlar, or for a whole branch from the OX
(ox-sys) cash-register database.

Every change is ONE stock_service.move() ADJUSTMENT (the ledger records who, when, from what to what); nothing writes
StoreProductStock directly. A count is never set below the units reserved for open orders / transfers: it is clamped to
the reservation and reported, so an order waiting at the branch keeps its goods.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import StockMovementType, StoreProductStock


@dataclass
class SetResult:
    variant_id: str
    before: int
    after: int
    reserved: int
    clamped: bool = False  # asked for less than the reservation -> set to the reservation

    @property
    def available(self) -> int:
        return self.after - self.reserved


def set_count(store, variant_id, target: int, *, actor: str, note: str, reference: str = "STOCK-SET") -> SetResult:
    """Make `store`'s on-hand count of `variant_id` equal `target` (clamped to the reservation)."""
    if target < 0:
        raise ValueError("A count cannot be negative.")
    with transaction.atomic():
        row = StoreProductStock.objects.select_for_update().filter(store=store, product_variant_id=variant_id).first()
        before, reserved = (row.quantity, row.reserved_quantity) if row else (0, 0)
        after = max(target, reserved)
        if after != before:
            stock_service.move(store, variant_id, after - before, StockMovementType.ADJUSTMENT, reference=reference, actor=actor,
                               note=f"{note}: {before} → {after}"[:255])
    return SetResult(str(variant_id), before, after, reserved, clamped=target < reserved)


def _keys(code: str) -> list[str]:
    code = (code or "").strip()
    if code.endswith(".0") and code[:-2].isdigit():
        code = code[:-2]
    return [k for k in {code, code.lstrip("0")} if k]


def barcode_index() -> dict[str, set]:
    """Every main and active extra barcode (also without leading zeros: OX keeps UPC-A, we may keep EAN-13) -> variant ids."""
    from apps.products.infrastructure.models import ProductVariant, ProductVariantBarcode

    index: dict[str, set] = {}
    for vid, code in ProductVariant.objects.filter(is_deleted=False).exclude(barcode__isnull=True).exclude(barcode="").values_list("id", "barcode"):
        for k in _keys(code):
            index.setdefault(k, set()).add(vid)
    for vid, code in ProductVariantBarcode.objects.filter(is_active=True, variant__is_deleted=False).values_list("variant_id", "barcode"):
        for k in _keys(code):
            index.setdefault(k, set()).add(vid)
    return index


@dataclass
class SyncReport:
    store: str
    dry_run: bool
    matched: int = 0
    unchanged: int = 0
    raised: list = field(default_factory=list)     # (variant, name, before, after)
    lowered: list = field(default_factory=list)
    clamped: list = field(default_factory=list)    # (variant, name, wanted, reserved)
    ambiguous: list = field(default_factory=list)  # barcodes that name two of our variants
    unknown: list = field(default_factory=list)    # (barcode, name, qty) -- in OX with stock, not in our catalogue
    not_in_source: list = field(default_factory=list)  # (variant, name, qty) -- we hold it here, OX doesn't list it

    def as_dict(self, sample: int = 40) -> dict:
        units = lambda rows: sum(r[3] - r[2] for r in rows)  # noqa: E731
        return {
            "store": self.store, "dry_run": self.dry_run, "matched": self.matched, "unchanged": self.unchanged,
            "raised": len(self.raised), "raised_units": units(self.raised), "lowered": len(self.lowered), "lowered_units": units(self.lowered),
            "clamped": len(self.clamped), "ambiguous": len(self.ambiguous), "unknown": len(self.unknown),
            "unknown_units": sum(r[2] for r in self.unknown), "not_in_source": len(self.not_in_source),
            "samples": {"raised": self.raised[:sample], "lowered": self.lowered[:sample], "clamped": self.clamped[:sample],
                        "ambiguous": self.ambiguous[:sample], "unknown": sorted(self.unknown, key=lambda r: -r[2])[:sample],
                        "not_in_source": self.not_in_source[:sample]},
        }


def sync_counts(store, counts: list, *, actor: str, source: str = "OX", dry_run: bool = True) -> SyncReport:
    """
    Make `store` hold exactly what the source system counts. `counts` = [[barcode, qty, name], ...] for EVERY item the
    source knows (qty 0 included -- that is how "sold out there" reaches us). Items we hold that the source doesn't list
    are reported, never touched.
    """
    from apps.stores.infrastructure.stock_service import variant_infos

    report = SyncReport(store=store.name, dry_run=dry_run)
    index = barcode_index()
    wanted: dict = {}
    names: dict = {}
    for item in counts:
        code, qty = str(item[0] or ""), int(float(item[1] or 0))
        name = str(item[2]) if len(item) > 2 else ""
        hits = set().union(*(index.get(k, set()) for k in _keys(code))) if _keys(code) else set()
        if len(hits) > 1:
            report.ambiguous.append((code, name, qty))
            continue
        if not hits:
            if qty > 0:
                report.unknown.append((code, name, qty))
            continue
        vid = next(iter(hits))
        wanted[vid] = wanted.get(vid, 0) + max(qty, 0)  # the same product under two barcodes (new batch label) adds up
        names.setdefault(vid, name)
    held = dict(StoreProductStock.objects.filter(store=store).values_list("product_variant_id", "quantity"))
    reserved = dict(StoreProductStock.objects.filter(store=store).values_list("product_variant_id", "reserved_quantity"))
    infos = variant_infos(list(set(wanted) | {v for v, q in held.items() if q > 0}))
    label = lambda vid: getattr(infos.get(vid), "name", "") or names.get(vid, "")  # noqa: E731
    for vid, qty in held.items():
        if qty > 0 and vid not in wanted:
            report.not_in_source.append((str(vid), label(vid), qty))
    report.matched = len(wanted)
    for vid, target in wanted.items():
        before, res = held.get(vid, 0), reserved.get(vid, 0)
        after = max(target, res)
        if target < res:
            report.clamped.append((str(vid), label(vid), target, res))
        if after == before:
            report.unchanged += 1
            continue
        (report.raised if after > before else report.lowered).append((str(vid), label(vid), before, after))
        if not dry_run:
            set_count(store, vid, target, actor=actor, note=f"{source} bazasi bo'yicha", reference=f"{source}-SYNC")
    return report
