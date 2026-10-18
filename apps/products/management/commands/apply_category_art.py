"""
Puts the premium category artwork (apps/products/infrastructure/category_art, made by the storefront repo's
scripts/category-art.mjs) on the catalogue tree from category_catalog.TREE.

    python manage.py apply_category_art            # only categories without an image
    python manage.py apply_category_art --force    # replace every image (also ones uploaded in the dashboard)
    python manage.py apply_category_art --dry-run

A category is found by its English name under the same parent (like seed_categories), so the two "Sport"-like
names in different sections never mix. Images go through the same media pipeline as a dashboard upload.
"""
from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError

ART_DIR = pathlib.Path(__file__).resolve().parents[2] / "infrastructure" / "category_art"


class Command(BaseCommand):
    help = "Applies the bundled premium artwork to the category tree (missing images only, unless --force)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Replace existing images too.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, force=False, dry_run=False, **options):
        from django.db.models.functions import Lower

        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.category_catalog import TREE
        from apps.products.infrastructure.composition import build_media_pipeline
        from core.media import MediaType, MediaUploadRequest

        try:
            manifest = json.loads((ART_DIR / "manifest.json").read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"No artwork manifest in {ART_DIR}") from exc
        pipeline = build_media_pipeline()
        stats = {"applied": 0, "kept": 0, "missing": 0}

        def find(en: str, parent):
            return orm.Category.objects.filter(parent=parent).annotate(n=Lower("translations__name")).filter(
                translations__locale_code="en", n=en.lower()).first()

        def apply(en: str, parent):
            category = find(en, parent)
            if category is None:
                stats["missing"] += 1
                self.stderr.write(f"  not in the database: {en}")
                return None
            if category.image_storage_path and not force:
                stats["kept"] += 1
                return category
            file = manifest.get(en)
            if not file or not (ART_DIR / file).exists():
                stats["missing"] += 1
                self.stderr.write(f"  no artwork for: {en}")
                return category
            if not dry_run:
                result = pipeline.process(MediaUploadRequest(filename=file, content=(ART_DIR / file).read_bytes(), mime_type="image/jpeg", media_type=MediaType.IMAGE))
                if result.is_failure:
                    raise CommandError(f"{en}: {result.errors[0].message}")
                orm.Category.objects.filter(pk=category.pk).update(image_storage_path=result.value.storage_path, image_thumbnail_paths=result.value.thumbnail_paths)
            stats["applied"] += 1
            return category

        for top in TREE:
            top_row = apply(top[2], None)
            for section in top[4]:
                section_row = apply(section[2], top_row) if top_row else None
                for leaf in section[4]:
                    if section_row:
                        apply(leaf[2], section_row)
        verb = "would apply" if dry_run else "applied"
        self.stdout.write(self.style.SUCCESS(f"Category art: {stats['applied']} {verb}, {stats['kept']} kept (own image), {stats['missing']} missing"))
