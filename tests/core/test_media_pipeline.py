from __future__ import annotations

import pytest

from core.media import (
    MediaPipeline,
    MediaType,
    MediaUploadRequest,
    build_storage_path,
)

pytestmark = pytest.mark.unit


class _InMemoryStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    def save(self, path: str, content: bytes) -> str:
        self.saved[path] = content
        return path


class _FakeImageOptimizer:
    def optimize(self, content: bytes) -> bytes:
        return content

    def to_webp(self, content: bytes) -> bytes:
        return content + b"-webp"

    def generate_thumbnails(self, content: bytes, sizes: dict[str, int]) -> dict[str, bytes]:
        return {name: content[:size] for name, size in sizes.items()}

    def read_dimensions(self, content: bytes) -> tuple[int, int]:
        return (800, 600)


class _RejectingScanner:
    def scan(self, content: bytes) -> bool:
        return False


def _document_request(content: bytes = b"%PDF-1.4 fake pdf content") -> MediaUploadRequest:
    return MediaUploadRequest(
        filename="cert.pdf", content=content, mime_type="application/pdf", media_type=MediaType.DOCUMENT
    )


def test_validate_rejects_disallowed_mime_type():
    pipeline = MediaPipeline(storage=_InMemoryStorage())
    request = MediaUploadRequest(filename="x.exe", content=b"data", mime_type="application/x-msdownload", media_type=MediaType.DOCUMENT)
    result = pipeline.validate(request)
    assert result.is_failure
    assert result.errors[0].code == "UNSUPPORTED_MIME_TYPE"


def test_validate_rejects_oversized_file():
    pipeline = MediaPipeline(storage=_InMemoryStorage())
    request = MediaUploadRequest(
        filename="big.pdf", content=b"x" * (26 * 1024 * 1024), mime_type="application/pdf", media_type=MediaType.DOCUMENT
    )
    result = pipeline.validate(request)
    assert result.is_failure
    assert result.errors[0].code == "FILE_TOO_LARGE"


def test_validate_rejects_empty_file():
    pipeline = MediaPipeline(storage=_InMemoryStorage())
    request = MediaUploadRequest(filename="empty.pdf", content=b"", mime_type="application/pdf", media_type=MediaType.DOCUMENT)
    result = pipeline.validate(request)
    assert result.is_failure
    assert result.errors[0].code == "EMPTY_FILE"


def test_validate_accepts_valid_document():
    pipeline = MediaPipeline(storage=_InMemoryStorage())
    result = pipeline.validate(_document_request())
    assert result.is_success


def test_scan_reports_failure_for_flagged_content():
    pipeline = MediaPipeline(storage=_InMemoryStorage(), virus_scanner=_RejectingScanner())
    result = pipeline.scan(_document_request())
    assert result.is_failure
    assert result.errors[0].code == "MALWARE_DETECTED"


def test_process_rejects_before_storing_on_validation_failure():
    storage = _InMemoryStorage()
    pipeline = MediaPipeline(storage=storage)
    request = MediaUploadRequest(filename="bad.exe", content=b"x", mime_type="application/x-msdownload", media_type=MediaType.DOCUMENT)
    result = pipeline.process(request)
    assert result.is_failure
    assert storage.saved == {}


def test_process_stores_document_successfully():
    storage = _InMemoryStorage()
    pipeline = MediaPipeline(storage=storage)
    result = pipeline.process(_document_request())
    assert result.is_success
    assert result.value.storage_path in storage.saved
    assert result.value.metadata.size_bytes == len(_document_request().content)
    assert result.value.has_webp_variant is False


def test_process_image_generates_webp_and_thumbnails():
    storage = _InMemoryStorage()
    pipeline = MediaPipeline(storage=storage, image_optimizer=_FakeImageOptimizer())
    request = MediaUploadRequest(filename="photo.jpg", content=b"fakejpegbytes", mime_type="image/jpeg", media_type=MediaType.IMAGE)
    result = pipeline.process(request)
    assert result.is_success
    assert result.value.has_webp_variant is True
    assert set(result.value.thumbnail_paths.keys()) == {"small", "medium", "large"}
    assert result.value.metadata.width_px == 800
    assert result.value.metadata.height_px == 600


def test_build_storage_path_is_content_addressed_and_deterministic():
    path_a = build_storage_path(MediaType.IMAGE, "abcdef1234567890", "webp")
    path_b = build_storage_path(MediaType.IMAGE, "abcdef1234567890", "webp")
    assert path_a == path_b
    assert path_a.startswith("image/ab/cd/")


def test_certificate_media_type_allows_pdf_and_images():
    pipeline = MediaPipeline(storage=_InMemoryStorage())
    pdf_request = MediaUploadRequest(filename="c.pdf", content=b"content", mime_type="application/pdf", media_type=MediaType.CERTIFICATE)
    image_request = MediaUploadRequest(filename="c.png", content=b"content", mime_type="image/png", media_type=MediaType.CERTIFICATE)
    assert pipeline.validate(pdf_request).is_success
    assert pipeline.validate(image_request).is_success
