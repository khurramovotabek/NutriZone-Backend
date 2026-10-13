"""
Media/static storage configuration component.

Local disk for development, object-storage-ready for production
(Django Implementation Blueprint §10). `NUTRIZONE_STORAGE_BACKEND`
selects the backend consumed by core/storage/backends.py.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR / "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = str(BASE_DIR / "media")

NUTRIZONE_STORAGE_BACKEND = os.environ.get("NUTRIZONE_STORAGE_BACKEND", "local")
NUTRIZONE_OBJECT_STORAGE_BUCKET = os.environ.get("NUTRIZONE_OBJECT_STORAGE_BUCKET", "")
NUTRIZONE_OBJECT_STORAGE_ENDPOINT = os.environ.get("NUTRIZONE_OBJECT_STORAGE_ENDPOINT", "")

# Upload size caps (Enterprise REST API Blueprint §11) -- enforced by
# the `content` app's application-layer validators once implemented;
# these Django-level ceilings are a defense-in-depth backstop.
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024  # 200MB, matches the largest allowed type (video)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
