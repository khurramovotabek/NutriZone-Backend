"""
Generation Application Services: GenerateSlug, GenerateSKU.

Thin orchestration wrapping the pure domain services
(domain/services.py::SlugGenerator/SKUGenerator) with the repository
lookups they need (collision checking) -- these are the "supply the
is_taken callable" call sites the domain services' own docstrings
describe.
"""
from __future__ import annotations

from apps.products.application.ports import ProductRepository
from apps.products.domain.services import SKUGenerator, SlugGenerator
from apps.products.domain.value_objects import Slug


class GenerateSlug:
    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo

    def execute(self, text: str) -> Slug:
        return SlugGenerator.generate_unique(text, is_taken=self._product_repo.slug_exists)


class GenerateSKU:
    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo

    def execute(self, brand_code: str, product_code: str, variant_suffix: str | None = None) -> str:
        candidate = SKUGenerator.generate(brand_code, product_code, variant_suffix)
        suffix = 1
        result = candidate
        while self._product_repo.sku_exists(result):
            suffix += 1
            result = f"{candidate}-{suffix}"
        return result
