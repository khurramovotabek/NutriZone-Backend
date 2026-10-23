"""
Puts the flavour artwork (apps/products/infrastructure/flavour_art, made by the storefront repo's
scripts/flavour-art.mjs) on the reference flavours, matched by slug.

    python manage.py apply_flavour_art            # only flavours without an image
    python manage.py apply_flavour_art --force    # replace every image (also ones uploaded in the dashboard)
    python manage.py apply_flavour_art --dry-run

Images go through the same media pipeline as a dashboard upload. Run seed_catalog_reference first so new
flavours exist.
"""
from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError

ART_DIR = pathlib.Path(__file__).resolve().parents[2] / "infrastructure" / "flavour_art"


class Command(BaseCommand):
    help = "Applies the bundled flavour artwork (missing images only, unless --force)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Replace existing images too.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, force=False, dry_run=False, **options):
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.composition import build_media_pipeline
        from core.media import MediaType, MediaUploadRequest

        try:
            manifest = json.loads((ART_DIR / "manifest.json").read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"No artwork manifest in {ART_DIR}") from exc
        pipeline = build_media_pipeline()
        stats = {"applied": 0, "kept": 0, "missing": 0}
        for flavour in orm.Flavour.objects.all():
            if flavour.image_storage_path and not force:
                stats["kept"] += 1
                continue
            file = manifest.get(flavour.slug)
            if not file or not (ART_DIR / file).exists():
                stats["missing"] += 1
                self.stderr.write(f"  no artwork for: {flavour.slug}")
                continue
            if not dry_run:
                result = pipeline.process(MediaUploadRequest(filename=file, content=(ART_DIR / file).read_bytes(), mime_type="image/jpeg", media_type=MediaType.IMAGE))
                if result.is_failure:
                    raise CommandError(f"{flavour.slug}: {result.errors[0].message}")
                orm.Flavour.objects.filter(pk=flavour.pk).update(image_storage_path=result.value.storage_path, image_thumbnail_paths=result.value.thumbnail_paths)
            stats["applied"] += 1
        verb = "would apply" if dry_run else "applied"
        self.stdout.write(self.style.SUCCESS(f"Flavour art: {stats['applied']} {verb}, {stats['kept']} kept (own image), {stats['missing']} missing"))
