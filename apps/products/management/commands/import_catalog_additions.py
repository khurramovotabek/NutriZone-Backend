"""
Adds products from a bundled dataset (apps/products/infrastructure/catalog_additions/<name>.py + <name>/<barcode>.jpg),
e.g. the stock of a branch that the online catalogue did not have yet.

    python manage.py import_catalog_additions quyliq_2026_10
    python manage.py import_catalog_additions quyliq_2026_10 --dry-run

Each product is written the way the dashboard writes one: ORM rows for the product, its uz/ru/en translations and one
variant (one product per size x flavour, like the rest of the catalogue), the price through pricing's SetPrice, the
photo through UploadImage. A product with a bundled photo is published, one without stays hidden until a photo is added.
Stock is not touched -- it arrives through Ombor documents (Kirim / transfer), as everywhere else.

Re-running is a no-op: an item whose barcode is already a variant's main or extra barcode is skipped. Extra barcodes
(the same product from a new batch with a new label) are attached to the existing variant instead of a new product.
"""
from __future__ import annotations

import importlib
from decimal import Decimal
import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / "infrastructure" / "catalog_additions"
LOCALES = ("uz", "ru", "en")


def _slug(name: str) -> str:
    return slugify(name.replace("’", "").replace("‘", "").replace("'", "").replace("ʼ", ""), allow_unicode=False)


class Command(BaseCommand):
    help = "Imports a bundled dataset of new products (new barcodes only)."

    def add_arguments(self, parser):
        parser.add_argument("dataset")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dataset, dry_run=False, **options):
        try:
            data = importlib.import_module(f"apps.products.infrastructure.catalog_additions.{dataset}")
        except ModuleNotFoundError as exc:
            raise CommandError(f"No dataset {dataset!r} in {DATA_DIR}") from exc
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.barcodes import barcode_q

        self.orm, self.photo_dir, self.dry_run = orm, DATA_DIR / dataset, dry_run
        stats = {"created": 0, "hidden": 0, "barcodes": 0, "skipped": 0}

        for code, existing in getattr(data, "EXTRA_BARCODES", []):
            if orm.ProductVariant.objects.filter(barcode_q(code)).exists():
                stats["skipped"] += 1
                continue
            variant = orm.ProductVariant.objects.filter(barcode=existing).first()
            if variant is None:
                raise CommandError(f"extra barcode {code}: no variant with barcode {existing}")
            if not dry_run:
                orm.ProductVariantBarcode.objects.create(variant=variant, barcode=code, note=getattr(data, "BARCODE_NOTE", ""))
            stats["barcodes"] += 1
            self.stdout.write(f"  {'would add' if dry_run else 'added'} barcode {code} -> {existing}")

        for item in data.ITEMS:
            if orm.ProductVariant.objects.filter(barcode_q(item["barcode"])).exists():
                stats["skipped"] += 1
                continue
            published = self._create(item, data)
            stats["created"] += 1
            stats["hidden"] += 0 if published else 1
            self.stdout.write(f"  {'would create' if dry_run else 'created'}{'' if published else ' (hidden, no photo)'}: {item['names']['uz']}")

        if not dry_run:
            from apps.products.infrastructure.composition import build_context

            build_context().invalidate_product_cache()
        verb = "would create" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(
            f"{dataset}: {stats['created']} products {verb} ({stats['hidden']} hidden without a photo), "
            f"{stats['barcodes']} extra barcodes, {stats['skipped']} already present"))

    # ------------------------------------------------------------------ helpers

    def _brand(self, name, data):
        if not name:
            return None  # an unbranded accessory
        orm = self.orm
        brand = orm.Brand.objects.filter(translations__locale_code="en", translations__name=name).first()
        if brand is not None:
            return brand
        spec = getattr(data, "NEW_BRANDS", {}).get(name)
        if spec is None:
            raise CommandError(f"unknown brand {name!r} (add it to NEW_BRANDS)")
        if self.dry_run:
            return None
        from apps.geo.infrastructure.models import Country

        brand = orm.Brand.objects.create(country=Country.objects.filter(code=spec.get("country", "")).first())
        for loc in LOCALES:
            orm.BrandTranslation.objects.create(brand=brand, locale_code=loc, name=name, slug=_slug(name), description=spec.get(loc, ""))
        return brand

    def _category(self, path):
        parent_name, leaf_name = path
        cat = self.orm.Category.objects.filter(translations__locale_code="en", translations__name=leaf_name,
                                               parent__translations__locale_code="en", parent__translations__name=parent_name).first()
        if cat is None:
            raise CommandError(f"no category {parent_name} > {leaf_name}")
        return cat

    def _flavour(self, name, data):
        if not name:
            return None
        orm = self.orm
        flavour = orm.Flavour.objects.filter(translations__locale_code="en", translations__name=name).first()
        if flavour is not None:
            return flavour
        spec = getattr(data, "NEW_FLAVOURS", {}).get(name)
        if spec is None:
            raise CommandError(f"unknown flavour {name!r} (add it to NEW_FLAVOURS)")
        if self.dry_run:
            return None
        flavour = orm.Flavour.objects.create(slug=_slug(name), color_hex=spec["color"], sort_order=900, is_active=True)
        for loc, label in (("en", name), ("uz", spec["uz"]), ("ru", spec["ru"])):
            orm.FlavourTranslation.objects.create(flavour=flavour, locale_code=loc, name=label)
        return flavour

    def _unique_slug(self, locale, name):
        base = _slug(name)[:200] or "mahsulot"
        slug, n = base, 1
        while self.orm.ProductTranslation.objects.filter(locale_code=locale, slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        return slug

    def _unique_sku(self, sku):
        candidate, n = sku, 1
        while self.orm.ProductVariant.all_objects.filter(sku=candidate).exists():
            n += 1
            candidate = f"{sku}-{n}"
        return candidate

    def _create(self, item, data) -> bool:
        orm = self.orm
        photo = self.photo_dir / f"{item['barcode']}.jpg"
        has_photo = photo.exists()
        brand = self._brand(item["brand"], data)
        category = self._category(item["category"])
        flavour = self._flavour(item.get("flavour"), data)
        package = orm.Package.objects.filter(slug=item["package"]).first()
        if package is None:
            raise CommandError(f"{item['barcode']}: no package {item['package']!r}")
        warn_from = orm.ProductVariant.objects.filter(barcode=item["warnings_from"]).select_related("product").first() if item.get("warnings_from") else None
        if item.get("warnings_from") and warn_from is None:
            raise CommandError(f"{item['barcode']}: warnings_from {item['warnings_from']} not found")
        if self.dry_run:
            return has_photo

        from apps.pricing.infrastructure import composition as pricing_composition
        from apps.products.infrastructure.admin import _get_or_create_default_price_list
        from apps.products.infrastructure.composition import build_upload_image
        from apps.products.infrastructure.product_grouping import sync_product_flavours

        with transaction.atomic():
            fields = {"brand": brand, "category": category, "status": "published" if has_photo else "unpublished",
                      "manufacturer": item.get("manufacturer") or "", "manufacturer_country_id": brand.country_id if brand else None,
                      "goals": item.get("goals", []),
                      "nutrition_serving_size_grams": item.get("serving_g"), "nutrition_servings_per_container": item.get("servings"),
                      "nutrition_calories": item.get("kcal")}
            for loc in LOCALES:
                fields[f"supplement_facts_text_{loc}"] = (item.get("facts") or {}).get(loc) or None
                fields[f"directions_text_{loc}"] = (item.get("directions") or {}).get(loc) or None
                fields[f"warnings_text_{loc}"] = getattr(warn_from.product, f"warnings_text_{loc}") if warn_from else ((item.get("warnings") or {}).get(loc) or None)
            product = orm.Product.objects.create(**fields)
            for loc in LOCALES:
                name = item["names"][loc]
                orm.ProductTranslation.objects.create(product=product, locale_code=loc, name=name,
                                                      slug=self._unique_slug(loc, name), description=item["descriptions"][loc])
            value, unit = item["size"]
            variant = orm.ProductVariant.objects.create(product=product, sku=self._unique_sku(item["sku"]), barcode=item["barcode"],
                                                        status="active", weight_value=value, weight_unit=unit,
                                                        package=package, flavour=flavour, is_default=True)
            sync_product_flavours(product)
            price_list = _get_or_create_default_price_list()
            pricing_composition.build_set_price().execute(price_list_id=price_list.id, product_variant_id=variant.id,
                                                          base_amount=Decimal(str(item["price"])), currency=price_list.currency,
                                                          cost_amount=None, sale_amount=None, compare_at_amount=None)
        if has_photo:
            build_upload_image().execute(product_id=product.id, filename=photo.name, content=photo.read_bytes(),
                                         mime_type="image/jpeg", media_role="primary")
        return has_photo
