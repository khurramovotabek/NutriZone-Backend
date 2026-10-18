"""
Fills category and brand descriptions with the long uz / ru / en texts (category_texts.py, brand_texts.py).

    python manage.py seed_descriptions             # only empty descriptions and the old short seed texts
    python manage.py seed_descriptions --force     # replace every description (also ones edited in the dashboard)
    python manage.py seed_descriptions --dry-run

Without --force a description written in the dashboard is never touched: only an empty one or one still equal to the
short text seed_categories / seed_brands put there is replaced. Categories are found by English name under the same
parent (like seed_categories); brands by any of their names or aliases (like seed_brands).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

LOCALES = ("uz", "ru", "en")


class Command(BaseCommand):
    help = "Writes the long category and brand descriptions (empty / old seed texts only, unless --force)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Replace descriptions edited in the dashboard too.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, force=False, dry_run=False, **options):
        from django.db import transaction

        stats = {"written": 0, "kept": 0, "missing": 0}
        with transaction.atomic():
            self._categories(stats, force)
            self._brands(stats, force)
            if dry_run:
                transaction.set_rollback(True)
        verb = "would write" if dry_run else "written"
        self.stdout.write(self.style.SUCCESS(f"Descriptions: {stats['written']} {verb}, {stats['kept']} kept (edited in the dashboard), {stats['missing']} not found"))

    def _write(self, row, text: str, old_defaults: set, force: bool, stats: dict) -> None:
        current = (row.description or "").strip()
        if current == text.strip():
            return
        if current and current not in old_defaults and not force:
            stats["kept"] += 1
            return
        row.description = text
        row.save(update_fields=["description", "updated_at"])
        stats["written"] += 1

    def _category(self, names: tuple, default: tuple, parent, stats: dict, force: bool):
        from django.db.models.functions import Lower

        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.category_texts import CATEGORY_TEXTS

        category = orm.Category.objects.filter(parent=parent).annotate(n=Lower("translations__name")).filter(
            translations__locale_code="en", n=names[2].lower()).first()
        texts = CATEGORY_TEXTS.get(names[2])
        if category is None or texts is None:
            stats["missing"] += 1
            self.stderr.write(f"  category not found: {names[2]}")
            return category
        for i, locale in enumerate(LOCALES):
            row = orm.CategoryTranslation.objects.filter(category=category, locale_code=locale).first()
            if row is not None:
                self._write(row, texts[i], {default[i].strip()} if default else set(), force, stats)
        return category

    def _categories(self, stats: dict, force: bool) -> None:
        from apps.products.infrastructure.category_catalog import TREE, _leaf_description

        for uz, ru, en, desc, sections in TREE:
            top = self._category((uz, ru, en), desc, None, stats, force)
            for suz, sru, sen, sdesc, leaves in sections if top else ():
                section = self._category((suz, sru, sen), sdesc, top, stats, force)
                for leaf in leaves if section else ():
                    self._category(leaf, _leaf_description(leaf, (suz, sru, sen)), section, stats, force)

    def _brands(self, stats: dict, force: bool) -> None:
        from django.db.models.functions import Lower

        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.brand_catalog import BRANDS
        from apps.products.infrastructure.brand_texts import BRAND_TEXTS

        for name, _code, uz, ru, en, aliases in BRANDS:
            texts = BRAND_TEXTS.get(name)
            wanted = {n.lower() for n in (name, *aliases)}
            brand = next((b for b in orm.Brand.objects.annotate(n=Lower("translations__name")).filter(n__in=wanted)), None)
            if brand is None or texts is None:
                stats["missing"] += 1
                self.stderr.write(f"  brand not found: {name}")
                continue
            for i, (locale, old) in enumerate(zip(LOCALES, (uz, ru, en), strict=True)):
                row = orm.BrandTranslation.objects.filter(brand=brand, locale_code=locale).first()
                if row is not None:
                    self._write(row, texts[i], {old.strip()}, force, stats)
