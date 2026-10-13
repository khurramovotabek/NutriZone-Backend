"""
Pillow-backed `ImageOptimizer`.

`Pillow` is already a pinned base dependency (`requirements/base.txt`),
imported directly at module scope like every other hard runtime
dependency in `core/` (e.g. `core.caching.redis_client`'s direct
`import redis`) -- not deferred behind a try/except, since a
deployment missing it is a genuine configuration error that should
fail loudly at import time, not silently at first upload.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

_JPEG_QUALITY = 85
_WEBP_QUALITY = 82
_THUMBNAIL_WEBP_QUALITY = 78


def _load(content: bytes) -> Image.Image:
    image = Image.open(BytesIO(content))
    image.load()  # force-read now, while the BytesIO buffer is still alive
    return image


def _normalize_mode_for(image: Image.Image, target_format: str) -> Image.Image:
    """JPEG has no alpha channel; WebP/PNG do. Convert only when the target format actually requires it."""
    if target_format == "JPEG" and image.mode in ("RGBA", "P", "LA"):
        return image.convert("RGB")
    if target_format in ("WEBP",) and image.mode not in ("RGB", "RGBA"):
        return image.convert("RGBA" if "A" in image.getbands() else "RGB")
    return image


class PillowImageOptimizer:
    """The foundation-phase, default `ImageOptimizer` -- real `Pillow`-based optimize/WebP/thumbnail/dimension-reading."""

    def optimize(self, content: bytes) -> bytes:
        """Re-encodes the image in its own format, with lossless-safe compression applied."""
        with _load(content) as image:
            original_format = (image.format or "JPEG").upper()
            image = _normalize_mode_for(image, original_format)
            buffer = BytesIO()
            save_kwargs: dict = {"optimize": True}
            if original_format == "JPEG":
                save_kwargs["quality"] = _JPEG_QUALITY
            image.save(buffer, format=original_format, **save_kwargs)
            return buffer.getvalue()

    def to_webp(self, content: bytes) -> bytes:
        """Produces a WebP-encoded copy of (already-optimized) image content."""
        with _load(content) as image:
            image = _normalize_mode_for(image, "WEBP")
            buffer = BytesIO()
            image.save(buffer, format="WEBP", quality=_WEBP_QUALITY, method=6)
            return buffer.getvalue()

    def generate_thumbnails(self, content: bytes, sizes: dict[str, int]) -> dict[str, bytes]:
        """`sizes` maps a thumbnail name to its max pixel dimension (aspect ratio preserved); returns WebP-encoded thumbnail bytes per name."""
        thumbnails: dict[str, bytes] = {}
        with _load(content) as image:
            image = _normalize_mode_for(image, "WEBP")
            for name, max_dimension in sizes.items():
                thumbnail = image.copy()
                thumbnail.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
                buffer = BytesIO()
                thumbnail.save(buffer, format="WEBP", quality=_THUMBNAIL_WEBP_QUALITY, method=6)
                thumbnails[name] = buffer.getvalue()
        return thumbnails

    def read_dimensions(self, content: bytes) -> tuple[int, int]:
        with _load(content) as image:
            return image.size
