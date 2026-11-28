"""
Creates the NutriZone shaker (the store's own branded shaker, photo in apps/products/assets/nutrizone-shaker.jpg),
prices it, publishes it and makes it the Sovg'a aksiyasi gift (GiftOfferSettings). Idempotent: a second run only
fixes the price / photo / settings of the product it made the first time (found by SKU).

    python manage.py setup_gift_shaker [--price 30000] [--min 1000000] [--dry-run]

Stock is NOT created here -- the warehouse receives the shakers through the normal WMS receiving, and until then the
gift is not offered (gift_offer only promises what is in stock).
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

SKU = "NZ-SHAKER"
PHOTO = Path(__file__).resolve().parents[2] / "assets" / "nutrizone-shaker.jpg"
NAMES = {"uz": "NutriZone sheykeri", "ru": "Шейкер NutriZone", "en": "NutriZone Shaker"}
SLUGS = {"uz": "nutrizone-sheykeri", "ru": "sheyker-nutrizone", "en": "nutrizone-shaker"}  # Cyrillic would slugify to "nutrizone"
DESCRIPTIONS = {
    "uz": "NutriZone'ning o'z brendli sheykeri: qora mat korpus, mahkam yopiladigan qopqoq va qulay tutqich. Protein, gayner va "
          "aminokislotalarni bir necha soniyada bir tekis aralashtiradi — mashg'ulotga, ishga va safarga olib yurish uchun qulay.",
    "ru": "Фирменный шейкер NutriZone: чёрный матовый корпус, плотно закрывающаяся крышка и удобная петля. Равномерно "
          "размешивает протеин, гейнер и аминокислоты за несколько секунд — удобно брать на тренировку, работу и в дорогу.",
    "en": "NutriZone's own branded shaker: matte black body, a tight-sealing lid and a handy carry loop. Mixes protein, gainer "
          "and amino acids smoothly in seconds — easy to take to the gym, to work and on the road.",
}


class Command(BaseCommand):
    help = "Create / update the NutriZone shaker and make it the order gift (Sovg'a aksiyasi)."

    def add_arguments(self, parser):
        parser.add_argument("--price", type=Decimal, default=Decimal("30000"))
        parser.add_argument("--min", type=Decimal, default=Decimal("1000000"), help="minimal goods total for the gift")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, price, min, dry_run=False, **options):  # noqa: A002 - CLI name
        from apps.products.infrastructure import gift_offer
        from apps.products.infrastructure import models as orm

        if not PHOTO.exists():
            raise CommandError(f"photo missing: {PHOTO}")
        category = self._category(orm)
        variant = orm.ProductVariant.all_objects.filter(sku=SKU).select_related("product").first()
        self.stdout.write(f"category: {category} · existing: {variant.product_id if variant else '-'}")
        if dry_run:
            return

        from apps.pricing.infrastructure import composition as pricing_composition
        from apps.products.infrastructure.admin import _get_or_create_default_price_list
        from apps.products.infrastructure.composition import build_upload_image

        with transaction.atomic():
            if variant is None:
                product = orm.Product.objects.create(category=category, status="unpublished", manufacturer="NutriZone",
                                                     manufacturer_country_id=None, goals=[])
                for loc, name in NAMES.items():
                    orm.ProductTranslation.objects.create(product=product, locale_code=loc, name=name, slug=self._unique_slug(orm, loc, SLUGS[loc]),
                                                          description=DESCRIPTIONS[loc])
                variant = orm.ProductVariant.objects.create(product=product, sku=SKU, status="active", is_default=True)
            product = variant.product
            price_list = _get_or_create_default_price_list()
            pricing_composition.build_set_price().execute(price_list_id=price_list.id, product_variant_id=variant.id, base_amount=price,
                                                          currency=price_list.currency, cost_amount=None, sale_amount=None, compare_at_amount=None)
        if not orm.ProductMedia.objects.filter(product_id=product.id).exists():
            build_upload_image().execute(product_id=product.id, filename=PHOTO.name, content=PHOTO.read_bytes(), mime_type="image/jpeg", media_role="primary")
        orm.Product.objects.filter(pk=product.pk).update(status="published")

        cfg = orm.GiftOfferSettings.load()
        cfg.gift_variant_id = variant.id
        cfg.min_goods_amount = min
        cfg.enabled = True
        cfg.save()
        gift_offer.invalidate()
        self.stdout.write(self.style.SUCCESS(f"NutriZone shaker {product.id} · variant {variant.id} · {price} so'm · gift from {min} so'm"))

    def _category(self, orm):
        """Shakerlar → Klassik (where the other shakers live), else Shakerlar itself."""
        shakers = orm.CategoryTranslation.objects.filter(locale_code="uz", slug="shakerlar").values_list("category_id", flat=True).first()
        if shakers is None:
            raise CommandError("category 'shakerlar' not found")
        classic = orm.Category.objects.filter(parent_id=shakers, translations__locale_code="uz", translations__name__iexact="Klassik").first()
        return classic or orm.Category.objects.get(pk=shakers)

    def _unique_slug(self, orm, locale, name):
        from apps.products.management.commands.import_catalog_additions import _slug

        base = _slug(name)[:200] or "nutrizone-shaker"
        slug, n = base, 1
        while orm.ProductTranslation.objects.filter(locale_code=locale, slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        return slug
