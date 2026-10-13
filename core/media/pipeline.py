"""
Media Pipeline: validate -> scan -> optimize -> WebP -> thumbnails ->
store, for the four `MediaType`s (Foundation Hardening mission; see
`docs/VALIDATION_REPORT_HARDENING.md` §2 for the full requirement
list this module was validated against).

`MediaPipeline.process()` always runs validation and the virus scan
*before* touching storage -- it never stores-then-validates (Validation
Report Hardening §3's explicit security requirement). Every collaborator
is a `Protocol` (see `protocols.py`), so a concrete image optimizer,
virus scanner, or storage backend can be swapped at the composition
root without any change here.
"""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import PurePosixPath

from core.media.enums import MediaType
from core.media.paths import build_storage_path
from core.media.protocols import ImageOptimizer, StorageWriter, VirusScanner
from core.media.scanning import NoOpVirusScanner
from core.media.value_objects import MediaMetadata, MediaUploadRequest, ProcessedMedia
from core.result import Result

# Database Blueprint §14/§10's exact thumbnail set -- name -> max pixel dimension.
THUMBNAIL_SIZES: dict[str, int] = {"small": 150, "medium": 400, "large": 800}

# 25 MiB -- generous enough for a certificate scan or product video-thumbnail
# image, small enough that a single upload can't monopolize a request/worker.
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

ALLOWED_MIME_TYPES: dict[MediaType, frozenset[str]] = {
    MediaType.IMAGE: frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"}),
    MediaType.VIDEO: frozenset({"video/mp4", "video/webm", "video/quicktime"}),
    MediaType.DOCUMENT: frozenset({"application/pdf"}),
    # A certificate is as often a photographed document as a native PDF.
    MediaType.CERTIFICATE: frozenset({"application/pdf", "image/jpeg", "image/png"}),
}


def _guess_extension(filename: str, mime_type: str) -> str:
    suffix = PurePosixPath(filename).suffix.lstrip(".")
    if suffix:
        return suffix.lower()
    guessed = mimetypes.guess_extension(mime_type) or ""
    return guessed.lstrip(".").lower() or "bin"


class MediaPipeline:
    def __init__(
        self,
        storage: StorageWriter,
        virus_scanner: VirusScanner | None = None,
        image_optimizer: ImageOptimizer | None = None,
    ) -> None:
        self._storage = storage
        self._virus_scanner = virus_scanner or NoOpVirusScanner()
        self._image_optimizer = image_optimizer

    def validate(self, request: MediaUploadRequest) -> Result[MediaUploadRequest]:
        if not request.content:
            return Result.single_failure("EMPTY_FILE", "The uploaded file is empty.", field="content")

        if len(request.content) > MAX_FILE_SIZE_BYTES:
            limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            return Result.single_failure("FILE_TOO_LARGE", f"The uploaded file exceeds the {limit_mb}MB limit.", field="content")

        allowed = ALLOWED_MIME_TYPES.get(request.media_type, frozenset())
        if request.mime_type not in allowed:
            return Result.single_failure(
                "UNSUPPORTED_MIME_TYPE",
                f"MIME type '{request.mime_type}' is not allowed for {request.media_type.value} uploads.",
                field="mime_type",
            )

        return Result.success(request)

    def scan(self, request: MediaUploadRequest) -> Result[MediaUploadRequest]:
        if not self._virus_scanner.scan(request.content):
            return Result.single_failure("MALWARE_DETECTED", "The uploaded file failed the malware scan.", field="content")
        return Result.success(request)

    def process(self, request: MediaUploadRequest) -> Result[ProcessedMedia]:
        validation = self.validate(request)
        if validation.is_failure:
            return validation

        scan_result = self.scan(request)
        if scan_result.is_failure:
            return scan_result

        checksum = hashlib.sha256(request.content).hexdigest()
        extension = _guess_extension(request.filename, request.mime_type)

        if request.media_type == MediaType.IMAGE and self._image_optimizer is not None:
            processed = self._process_image(request, checksum, extension)
        else:
            storage_path = self._storage.save(build_storage_path(request.media_type, checksum, extension), request.content)
            processed = ProcessedMedia(
                storage_path=storage_path,
                media_type=request.media_type,
                mime_type=request.mime_type,
                metadata=MediaMetadata(size_bytes=len(request.content), checksum_sha256=checksum),
                has_webp_variant=False,
                thumbnail_paths={},
            )

        return Result.success(processed)

    def _process_image(self, request: MediaUploadRequest, checksum: str, extension: str) -> ProcessedMedia:
        optimizer = self._image_optimizer
        optimized = optimizer.optimize(request.content)
        webp_bytes = optimizer.to_webp(optimized)
        width_px, height_px = optimizer.read_dimensions(optimized)
        thumbnail_bytes = optimizer.generate_thumbnails(optimized, dict(THUMBNAIL_SIZES))

        storage_path = self._storage.save(build_storage_path(request.media_type, checksum, extension), optimized)
        # Deterministic path -- callers that need it (e.g. UploadAvatar) recompute
        # it themselves via build_storage_path() rather than us returning it twice.
        self._storage.save(build_storage_path(request.media_type, checksum, "webp"), webp_bytes)
        thumbnail_paths = {
            name: self._storage.save(build_storage_path(request.media_type, checksum, f"{name}.webp"), data)
            for name, data in thumbnail_bytes.items()
        }

        return ProcessedMedia(
            storage_path=storage_path,
            media_type=request.media_type,
            mime_type=request.mime_type,
            metadata=MediaMetadata(size_bytes=len(request.content), checksum_sha256=checksum, width_px=width_px, height_px=height_px),
            has_webp_variant=True,
            thumbnail_paths=thumbnail_paths,
        )
