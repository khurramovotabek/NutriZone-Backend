"""
In-memory fakes implementing application/ports.py's Protocols, used
across application-layer tests -- matching
`apps/identity/tests/application/fakes.py`'s exact pattern.
"""
from __future__ import annotations

import uuid


class FakeProductRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}
        self.deleted_ids: set = set()

    def get_by_id(self, product_id):
        return self.by_id.get(product_id)

    def get_by_slug(self, slug: str):
        for p in self.by_id.values():
            if p.slug.value == slug:
                return p
        return None

    def save(self, product):
        self.by_id[product.id] = product
        return product

    def slug_exists(self, slug: str, exclude_product_id=None) -> bool:
        return any(p.slug.value == slug and p.id != exclude_product_id for p in self.by_id.values())

    def sku_exists(self, sku: str, exclude_product_id=None) -> bool:
        for p in self.by_id.values():
            if p.id == exclude_product_id:
                continue
            if any(v.sku.value == sku for v in p.variants.values()):
                return True
        return False

    def barcode_exists(self, barcode: str, exclude_product_id=None) -> bool:
        for p in self.by_id.values():
            if p.id == exclude_product_id:
                continue
            if any(v.barcode and v.barcode.value == barcode for v in p.variants.values()):
                return True
        return False

    def list_public(self, category_id=None, brand_id=None, tag_ids=None, query=None, page=1, page_size=20, ordering="-created_at"):
        from apps.products.domain.enums import ProductStatus

        results = [p for p in self.by_id.values() if p.status == ProductStatus.PUBLISHED]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def list_for_admin(self, status=None, query=None, page=1, page_size=20):
        results = list(self.by_id.values())
        if status:
            results = [p for p in results if p.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def delete(self, product_id):
        self.deleted_ids.add(product_id)
        self.by_id.pop(product_id, None)


class FakeBrandRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, brand_id):
        return self.by_id.get(brand_id)

    def get_by_slug(self, slug):
        return next((b for b in self.by_id.values() if b.slug.value == slug), None)

    def save(self, brand):
        self.by_id[brand.id] = brand
        return brand

    def slug_exists(self, slug, exclude_brand_id=None) -> bool:
        return any(b.slug.value == slug and b.id != exclude_brand_id for b in self.by_id.values())

    def list_active(self):
        return [b for b in self.by_id.values() if b.is_active]


class FakeCategoryRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, category_id):
        return self.by_id.get(category_id)

    def get_by_slug(self, slug):
        return next((c for c in self.by_id.values() if c.slug.value == slug), None)

    def save(self, category):
        self.by_id[category.id] = category
        return category

    def slug_exists(self, slug, exclude_category_id=None) -> bool:
        return any(c.slug.value == slug and c.id != exclude_category_id for c in self.by_id.values())

    def list_tree(self):
        return list(self.by_id.values())


class FakeTagRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_code(self, code):
        return next((t for t in self.by_id.values() if t.code == code), None)

    def get_many_by_ids(self, tag_ids):
        return [t for t in self.by_id.values() if t.id in tag_ids]

    def save(self, tag):
        self.by_id[tag.id] = tag
        return tag

    def list_all(self):
        return list(self.by_id.values())


class FakeFlavourRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, flavour_id):
        return self.by_id.get(flavour_id)

    def get_by_slug(self, slug):
        return next((f for f in self.by_id.values() if f.slug.value == slug), None)

    def get_many_by_ids(self, flavour_ids):
        return [f for f in self.by_id.values() if f.id in flavour_ids]

    def save(self, flavour):
        self.by_id[flavour.id] = flavour
        return flavour

    def list_active(self):
        return [f for f in self.by_id.values() if f.is_active]


class FakePackageRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, package_id):
        return self.by_id.get(package_id)

    def get_by_slug(self, slug):
        return next((p for p in self.by_id.values() if p.slug.value == slug), None)

    def save(self, package):
        self.by_id[package.id] = package
        return package

    def list_active(self):
        return [p for p in self.by_id.values() if p.is_active]


def collect_events(sink: list):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
