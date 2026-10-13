"""
Media Application Services: UploadImage, DeleteImage, UploadVideo,
DeleteVideo, UploadDocument, DeleteDocument.

Integrates with the existing Media Pipeline (core.media, Foundation
Hardening phase) exactly as `apps.identity.application.services.
profile::UploadAvatar` does -- validate -> scan -> optimize -> WebP ->
thumbnails -> store, with hash-based deduplication (the pipeline's
content-addressed storage path, `core.media.build_storage_path`,
already deduplicates identical file content by construction: two
uploads with the same bytes produce the same path).
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.products.application.ports import ProductRepository
from apps.products.application.services._shared import ProductServiceContext
from apps.products.domain.aggregates import Product
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole
from apps.products.domain.value_objects import ImageMetadata, VideoMetadata
from common.exceptions import ResourceNotFound, ValidationFailed


class UploadImage:
    def __init__(self, product_repo: ProductRepository, media_pipeline, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._media_pipeline = media_pipeline
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, filename: str, content: bytes, mime_type: str, media_role: str = MediaRole.GALLERY.value, variant_id: uuid.UUID | None = None) -> Product:
        from core.media import MediaType, MediaUploadRequest

        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        if variant_id is not None and variant_id not in product.variants:
            raise ValidationFailed("That variant does not belong to this product.", details={"fields": [{"field": "variant_id", "code": "INVALID_VARIANT"}]})

        request = MediaUploadRequest(filename=filename, content=content, mime_type=mime_type, media_type=MediaType.IMAGE)
        result = self._media_pipeline.process(request)
        if result.is_failure:
            first_error = result.errors[0]
            raise ValidationFailed(first_error.message, details={"fields": [{"field": "image", "code": first_error.code}]})

        processed = result.value
        media_id = uuid.uuid4()
        media = ProductMedia(
            id=media_id, media_id=media_id, media_role=MediaRole(media_role), storage_path=processed.storage_path, thumbnail_paths=processed.thumbnail_paths, sort_order=len(product.media),
            variant_id=variant_id,
            image_metadata=ImageMetadata(width_px=processed.metadata.width_px or 0, height_px=processed.metadata.height_px or 0, checksum_sha256=processed.metadata.checksum_sha256),
        )
        event = product.add_media(media)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductMediaUploaded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"media_uploaded": str(media.id), "role": media_role})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("media_uploaded_total", media_type="image")

        return saved


class DeleteImage:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, media_id: uuid.UUID) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        product.remove_media(media_id)
        saved = self._product_repo.save(product)

        from apps.products.domain.events import ProductMediaDeleted

        self._ctx.stage_events([("ProductMediaDeleted", ProductMediaDeleted(product_id=product_id, media_id=media_id).to_payload())])
        self._ctx.audit().deleted(entity_type="Product", entity_id=str(product_id), before={"media_id": str(media_id)})
        self._ctx.invalidate_product_cache()

        return saved


class UploadVideo:
    def __init__(self, product_repo: ProductRepository, media_pipeline, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._media_pipeline = media_pipeline
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, filename: str, content: bytes, mime_type: str, duration_seconds: float, variant_id: uuid.UUID | None = None) -> Product:
        from core.media import MediaType, MediaUploadRequest

        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        if variant_id is not None and variant_id not in product.variants:
            raise ValidationFailed("That variant does not belong to this product.", details={"fields": [{"field": "variant_id", "code": "INVALID_VARIANT"}]})

        request = MediaUploadRequest(filename=filename, content=content, mime_type=mime_type, media_type=MediaType.VIDEO)
        result = self._media_pipeline.process(request)
        if result.is_failure:
            first_error = result.errors[0]
            raise ValidationFailed(first_error.message, details={"fields": [{"field": "video", "code": first_error.code}]})

        processed = result.value
        media_id = uuid.uuid4()
        media = ProductMedia(
            id=media_id, media_id=media_id, media_role=MediaRole.VIDEO, storage_path=processed.storage_path, thumbnail_paths=processed.thumbnail_paths, sort_order=len(product.media),
            variant_id=variant_id,
            video_metadata=VideoMetadata(duration_seconds=duration_seconds, checksum_sha256=processed.metadata.checksum_sha256),
        )
        event = product.add_media(media)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductMediaUploaded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"media_uploaded": str(media.id), "role": "video"})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("media_uploaded_total", media_type="video")

        return saved


class DeleteVideo(DeleteImage):
    """Identical mechanics to DeleteImage -- ProductMedia is one unified entity regardless of role (domain/entities.py::ProductMedia's docstring), so 'delete a video' and 'delete an image' are the same domain operation."""


class UploadDocument:
    def __init__(self, product_repo: ProductRepository, media_pipeline, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._media_pipeline = media_pipeline
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, filename: str, content: bytes, mime_type: str) -> Product:
        from core.media import MediaType, MediaUploadRequest

        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        request = MediaUploadRequest(filename=filename, content=content, mime_type=mime_type, media_type=MediaType.DOCUMENT)
        result = self._media_pipeline.process(request)
        if result.is_failure:
            first_error = result.errors[0]
            raise ValidationFailed(first_error.message, details={"fields": [{"field": "document", "code": first_error.code}]})

        processed = result.value
        media_id = uuid.uuid4()
        media = ProductMedia(id=media_id, media_id=media_id, media_role=MediaRole.DOCUMENT, storage_path=processed.storage_path, thumbnail_paths=processed.thumbnail_paths, sort_order=len(product.media))
        event = product.add_media(media)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductMediaUploaded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"media_uploaded": str(media.id), "role": "document"})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("media_uploaded_total", media_type="document")

        return saved


class DeleteDocument(DeleteImage):
    """Same rationale as DeleteVideo -- see DeleteImage."""
