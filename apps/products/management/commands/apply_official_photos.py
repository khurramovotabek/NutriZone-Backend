"""
Replaces product photos with the brand's official pack shots bundled in apps/products/infrastructure/official_photos
(manifest.json: product slug → its product id, the file and the official source URL), matched by product id.

    python manage.py apply_official_photos            # products whose main photo isn't the official one yet
    python manage.py apply_official_photos --dry-run

The product's main photo (role "primary") is replaced by the official shot, through the same media pipeline and services
as a dashboard upload. The gallery (the shop's info cards, label photos), videos and documents are kept.
Re-running is a no-op: the pipeline's storage path is content-addressed, so an applied photo is recognised.
"""
from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError

PHOTO_DIR = pathlib.Path(__file__).resolve().parents[2] / "infrastructure" / "official_photos"


class Command(BaseCommand):
    help = "Applies the bundled official product photos as the main photo of the listed products."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.composition import (
            build_delete_image,
            build_media_pipeline,
            build_upload_image,
        )
        from core.media import MediaType, MediaUploadRequest

        try:
            manifest = json.loads((PHOTO_DIR / "manifest.json").read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"No photo manifest in {PHOTO_DIR}") from exc
        pipeline = build_media_pipeline()
        stats = {"applied": 0, "kept": 0, "missing": 0}
        for slug, entry in manifest.items():
            product = orm.Product.objects.filter(pk=entry["product_id"]).first()
            path = PHOTO_DIR / entry["file"]
            if product is None or not path.exists():
                stats["missing"] += 1
                self.stderr.write(f"  skipped (no product or file): {slug}")
                continue
            content = path.read_bytes()
            result = pipeline.process(MediaUploadRequest(filename=entry["file"], content=content, mime_type="image/jpeg", media_type=MediaType.IMAGE))
            if result.is_failure:
                raise CommandError(f"{slug}: {result.errors[0].message}")
            images = list(orm.ProductMedia.objects.filter(product=product, media_role="primary"))
            if len(images) == 1 and images[0].variant_id is None and images[0].storage_path == result.value.storage_path:
                stats["kept"] += 1
                continue
            if not dry_run:
                for media in images:
                    build_delete_image().execute(product_id=product.id, media_id=media.id)
                build_upload_image().execute(product_id=product.id, filename=entry["file"], content=content, mime_type="image/jpeg", media_role="primary")
            stats["applied"] += 1
            self.stdout.write(f"  {'would replace' if dry_run else 'replaced'} {len(images)} main photo(s): {slug}")
        verb = "would apply" if dry_run else "applied"
        self.stdout.write(self.style.SUCCESS(f"Official photos: {stats['applied']} {verb}, {stats['kept']} already official, {stats['missing']} skipped"))
