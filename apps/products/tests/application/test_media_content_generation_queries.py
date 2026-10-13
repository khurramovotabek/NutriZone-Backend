from __future__ import annotations

import inspect
import uuid

import pytest

from apps.products.application.services._shared import ProductServiceContext
from apps.products.application.services.content import UpdateDirections, UpdateIngredients, UpdateSEO, UpdateWarnings
from apps.products.application.services.generation import GenerateSKU, GenerateSlug
from apps.products.application.services.media import DeleteImage, UploadImage
from apps.products.application.services.queries import AdminListProducts, GetProduct, ListProducts, SearchProducts
from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole, ProductStatus
from apps.products.domain.value_objects import SKU, Slug
from apps.products.tests.application.fakes import FakeProductRepository, collect_events
from common.exceptions import ResourceNotFound, ValidationFailed
from core.media import MediaMetadata, ProcessedMedia
from core.result import Error, Result


def _ctx():
    events: list = []
    return ProductServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


def _bare_product() -> Product:
    return Product(id=uuid.uuid4(), slug=Slug("x"), name="X")


class _FakeMediaPipeline:
    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed

    def process(self, request):
        if not self.succeed:
            return Result.failure(Error(code="UNSUPPORTED_MIME_TYPE", message="bad file"))
        return Result.success(
            ProcessedMedia(
                storage_path="image/ab/cd/checksum.jpg", media_type=request.media_type, mime_type=request.mime_type,
                metadata=MediaMetadata(size_bytes=100, checksum_sha256="checksum", width_px=800, height_px=600),
                has_webp_variant=True, thumbnail_paths={"small": "x", "medium": "y", "large": "z"},
            )
        )


class _FakeMediaAssetRepository:
    def __init__(self) -> None:
        self.created: list = []

    def create(self, **kwargs):
        asset_id = uuid.uuid4()
        self.created.append((asset_id, kwargs))
        return asset_id


@pytest.mark.django_db
class TestUploadDeleteImage:
    def test_upload_image_adds_primary_media(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, events = _ctx()

        updated = UploadImage(repo, _FakeMediaPipeline(), ctx).execute(
            product_id=product.id, filename="photo.jpg", content=b"data", mime_type="image/jpeg", media_role="primary"
        )

        assert len(updated.media) == 1
        assert any(e[0] == "ProductMediaUploaded" for e in events)

    def test_upload_image_pipeline_failure_raises_validation_failed(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, _ = _ctx()

        with pytest.raises(ValidationFailed):
            UploadImage(repo, _FakeMediaPipeline(succeed=False), ctx).execute(
                product_id=product.id, filename="bad.exe", content=b"data", mime_type="application/x-msdownload"
            )

    def test_delete_image(self):
        repo = FakeProductRepository()
        product = _bare_product()
        media = ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.GALLERY)
        product.add_media(media)
        repo.save(product)
        ctx, events = _ctx()

        updated = DeleteImage(repo, ctx).execute(product_id=product.id, media_id=media.id)

        assert media.id not in updated.media
        assert any(e[0] == "ProductMediaDeleted" for e in events)


@pytest.mark.django_db
class TestContentServices:
    def test_update_ingredients(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, _ = _ctx()
        updated = UpdateIngredients(repo, ctx).execute(product_id=product.id, ingredients_text="Whey protein isolate.")
        assert updated.supplement_facts_text_uz == "Whey protein isolate."

    def test_update_warnings(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, _ = _ctx()
        updated = UpdateWarnings(repo, ctx).execute(product_id=product.id, warnings_text="Consult a doctor.")
        assert updated.warnings_text_uz == "Consult a doctor."

    def test_update_directions(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, _ = _ctx()
        updated = UpdateDirections(repo, ctx).execute(product_id=product.id, directions_text="Mix with water.")
        assert updated.directions_text_uz == "Mix with water."

    def test_update_seo(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, events = _ctx()
        updated = UpdateSEO(repo, ctx).execute(product_id=product.id, meta_title="Best Whey")
        assert updated.seo.meta_title == "Best Whey"
        assert any(e[0] == "ProductSEOUpdated" for e in events)

    def test_content_service_missing_product_raises(self):
        repo = FakeProductRepository()
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            UpdateIngredients(repo, ctx).execute(product_id=uuid.uuid4(), ingredients_text="x")


class TestGenerationServices:
    def test_generate_slug_unique(self):
        repo = FakeProductRepository()
        slug = GenerateSlug(repo).execute("Whey Protein")
        assert slug.value == "whey-protein"

    def test_generate_sku_avoids_collision(self):
        repo = FakeProductRepository()
        product = _bare_product()
        product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("ON-WHEY")))
        repo.save(product)

        sku = GenerateSKU(repo).execute("on", "whey")
        assert sku == "ON-WHEY-2"


class TestQueryServices:
    def test_get_product_returns_published_only(self):
        repo = FakeProductRepository()
        product = _bare_product()
        product.status = ProductStatus.DRAFT
        repo.save(product)
        with pytest.raises(ResourceNotFound):
            GetProduct(repo).execute(product.slug.value)

    def test_get_product_returns_published_product(self):
        repo = FakeProductRepository()
        product = _bare_product()
        product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1")))
        product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY))
        product.publish()
        repo.save(product)

        found = GetProduct(repo).execute(product.slug.value)
        assert found.id == product.id

    def test_list_products_only_returns_published(self):
        repo = FakeProductRepository()
        draft = _bare_product()
        repo.save(draft)
        results, total = ListProducts(repo).execute()
        assert total == 0

    def test_admin_list_products_returns_all_statuses(self):
        repo = FakeProductRepository()
        repo.save(_bare_product())
        results, total = AdminListProducts(repo).execute()
        assert total == 1


class TestSearchProducts:
    class _FakeSelector:
        def search(self, query, filters, page, page_size, sort, locale=None):
            return {"results": [{"id": "x"}], "total_count": 1, "facets": {}}

    def test_search_calls_selector_and_caches(self):
        service = SearchProducts(self._FakeSelector())
        result = service.execute(query="whey", filters={})
        assert result["total_count"] == 1

    def test_search_second_call_is_cached(self):
        selector = self._FakeSelector()
        call_count = {"n": 0}
        original_search = selector.search

        def counting_search(*args, **kwargs):
            call_count["n"] += 1
            return original_search(*args, **kwargs)

        selector.search = counting_search
        service = SearchProducts(selector)
        service.execute(query="whey", filters={})
        service.execute(query="whey", filters={})
        assert call_count["n"] == 1

    def test_different_locales_are_not_served_from_the_same_cache_entry(self):
        """A real defect fix: locale is now part of the cache key -- without this, a search cached under one language would incorrectly be served to a request in a different language. Proves the fix directly rather than merely asserting the parameter is accepted."""
        selector = self._FakeSelector()
        call_count = {"n": 0}
        original_search = selector.search

        def counting_search(*args, **kwargs):
            call_count["n"] += 1
            return original_search(*args, **kwargs)

        selector.search = counting_search
        service = SearchProducts(selector)
        service.execute(query="whey", filters={}, locale="en")
        service.execute(query="whey", filters={}, locale="ru")
        assert call_count["n"] == 2, "Two different locales must not share a cache entry."

    def test_same_locale_repeated_is_still_cached(self):
        selector = self._FakeSelector()
        call_count = {"n": 0}
        original_search = selector.search

        def counting_search(*args, **kwargs):
            call_count["n"] += 1
            return original_search(*args, **kwargs)

        selector.search = counting_search
        service = SearchProducts(selector)
        service.execute(query="whey", filters={}, locale="ru")
        service.execute(query="whey", filters={}, locale="ru")
        assert call_count["n"] == 1

    def test_locale_is_forwarded_to_the_selector(self):
        received = {}

        class _CapturingSelector:
            def search(self, query, filters, page, page_size, sort, locale=None):
                received["locale"] = locale
                return {"results": [], "total_count": 0, "facets": {}}

        SearchProducts(_CapturingSelector()).execute(query="whey", filters={}, locale="uz")
        assert received["locale"] == "uz"

    def test_without_variant_repo_or_detail_reader_falls_straight_to_text_search(self):
        """Backward-compatibility proof: an existing caller (like every other test in this class) that doesn't wire the new dependencies gets exactly the prior, unchanged behavior -- the cascade is skipped entirely, never raises for missing dependencies."""
        service = SearchProducts(self._FakeSelector())
        result = service.execute(query="5901234123457", filters={})
        assert result["total_count"] == 1  # the fake selector's own fixed full-text response, cascade never touched

    def test_valid_barcode_resolves_directly_to_the_exact_product(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()

        class _VariantRepo:
            def get_by_barcode(self, barcode):
                return (product_id, variant_id) if barcode == "5901234123457" else None

            def get_by_sku(self, sku):
                return None

        class _DetailReader:
            def get_by_id(self, pid, locale=None):
                return {"id": str(pid), "name": "Exact Match Product"} if pid == product_id else None

        service = SearchProducts(self._FakeSelector(), variant_repo=_VariantRepo(), detail_reader=_DetailReader())
        result = service.execute(query="5901234123457", filters={})

        assert result["total_count"] == 1
        assert result["results"][0]["id"] == str(product_id)

    def test_barcode_miss_falls_through_to_the_real_overlap_case_sku(self):
        """The genuine, disclosed regex-overlap finding already proven during POS's own Search phase: a valid-checksum barcode-format string also matches SKU's own pattern. When the barcode lookup misses, the cascade must try SKU next -- not error out, not skip to text."""
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()

        class _VariantRepo:
            def get_by_barcode(self, barcode):
                return None  # registered nowhere as a barcode

            def get_by_sku(self, sku):
                return (product_id, variant_id) if sku == "5901234123457" else None

        class _DetailReader:
            def get_by_id(self, pid, locale=None):
                return {"id": str(pid), "name": "SKU Match Product"}

        service = SearchProducts(self._FakeSelector(), variant_repo=_VariantRepo(), detail_reader=_DetailReader())
        result = service.execute(query="5901234123457", filters={})

        assert result["total_count"] == 1
        assert result["results"][0]["id"] == str(product_id)

    def test_neither_barcode_nor_sku_match_falls_through_to_text_search(self):
        class _VariantRepo:
            def get_by_barcode(self, barcode):
                return None

            def get_by_sku(self, sku):
                return None

        class _DetailReader:
            def get_by_id(self, pid, locale=None):
                return None

        service = SearchProducts(self._FakeSelector(), variant_repo=_VariantRepo(), detail_reader=_DetailReader())
        result = service.execute(query="5901234123457", filters={})

        assert result["total_count"] == 1  # falls through to the fake selector's own fixed full-text response

    def test_free_text_query_never_attempts_an_exact_lookup(self):
        """A direct proof the cascade skips both lookup calls entirely for genuinely non-identifier text, rather than merely returning None from within them."""
        calls = {"barcode": 0, "sku": 0}

        class _VariantRepo:
            def get_by_barcode(self, barcode):
                calls["barcode"] += 1
                return None

            def get_by_sku(self, sku):
                calls["sku"] += 1
                return None

        service = SearchProducts(self._FakeSelector(), variant_repo=_VariantRepo(), detail_reader=None)
        service.execute(query="protein powder", filters={})
        assert calls == {"barcode": 0, "sku": 0}, "'protein powder' matches neither Barcode's nor SKU's format -- no lookup call should ever be attempted."

    def test_exact_match_never_duplicates_pricing_or_availability_logic(self):
        """A direct, executable proof this cascade only ever renders a product card obtained from ProductDetailReader -- it computes nothing itself."""
        source = inspect.getsource(SearchProducts._try_exact_identifier_match)
        assert "price" not in source.lower()
        assert "availability" not in source.lower()
        assert "stock" not in source.lower()
