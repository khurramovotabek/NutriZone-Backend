"""
Media type vocabulary.

A closed, typed enum -- every `MediaUploadRequest` is tagged with one
of these, and `MediaPipeline.validate()` uses it to select the correct
MIME allow-list (see `pipeline.py::_ALLOWED_MIME_TYPES`). The four
members are the exact set the Foundation Hardening mission named
("four media types"): everyday gallery images, product/store/review
video, standalone documents (spec sheets, manuals), and certificates
(which -- uniquely -- accept either a PDF or a scanned image, since a
certificate is as often a photographed document as a native PDF).
"""
from __future__ import annotations

from enum import StrEnum


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    CERTIFICATE = "certificate"
