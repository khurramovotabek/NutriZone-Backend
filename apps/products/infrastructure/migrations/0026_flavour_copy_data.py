# Data migration -- copies real, existing data forward into the new
# Flavour module before 0027 drops the old columns/tables it reads
# from (matches the 0006_brand_copy_logo_data precedent). Two
# independent copies:
#
# 1. ProductVariant.weight_grams -> ProductVariant.weight_value (every
#    existing value was always grams, so weight_unit's own model
#    default of "g" is already correct and needs no extra write here).
# 2. Every AttributeValue under the reserved Attribute(code="flavor")
#    -> a real Flavour + FlavourTranslation row (same id reused, for
#    traceability), and every VariantAttributeValue link to one of
#    those values -> a ProductFlavour link on that variant's own
#    product (Flavour is a Product-level tag now, not a variant-level
#    one -- see domain/aggregates.py::Flavour's docstring -- so
#    several variants of the same product tagging the same flavor
#    value collapse to one ProductFlavour row via get_or_create).
#
# package_size/form attribute values are NOT migrated -- confirmed,
# before this refactor, to have zero real rows in this database, and
# explicitly torn down per the same product decision that removed the
# whole Attribute/AttributeValue system.

from django.db import migrations
from django.utils.text import slugify


def _unique_slug(base: str, taken: set) -> str:
    slug = slugify(base) or "flavour"
    candidate = slug
    suffix = 2
    while candidate in taken:
        candidate = f"{slug}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def copy_weight_and_flavours(apps, schema_editor):
    ProductVariant = apps.get_model("products", "ProductVariant")
    Attribute = apps.get_model("products", "Attribute")
    AttributeValue = apps.get_model("products", "AttributeValue")
    Flavour = apps.get_model("products", "Flavour")
    FlavourTranslation = apps.get_model("products", "FlavourTranslation")
    ProductFlavour = apps.get_model("products", "ProductFlavour")

    for variant in ProductVariant.objects.exclude(weight_grams__isnull=True).only("id", "weight_grams"):
        ProductVariant.objects.filter(id=variant.id).update(weight_value=variant.weight_grams)

    flavor_attribute = Attribute.objects.filter(code="flavor").first()
    if flavor_attribute is None:
        return

    taken_slugs = set(Flavour.objects.values_list("slug", flat=True))
    flavour_id_by_value_id: dict = {}

    for value in AttributeValue.objects.filter(attribute=flavor_attribute).prefetch_related("translations", "variant_links__variant"):
        slug = _unique_slug(value.code, taken_slugs)
        flavour = Flavour.objects.create(
            id=value.id, slug=slug, color_hex=value.color_hex or "#8B5CF6", sort_order=value.sort_order,
            is_active=True, image_storage_path=value.image_storage_path, image_thumbnail_paths=value.image_thumbnail_paths,
        )
        flavour_id_by_value_id[value.id] = flavour.id

        for translation in value.translations.all():
            FlavourTranslation.objects.create(flavour=flavour, locale_code=translation.locale_code, name=translation.name)

        for link in value.variant_links.all():
            ProductFlavour.objects.get_or_create(product_id=link.variant.product_id, flavour_id=flavour.id)


def noop_reverse(apps, schema_editor):
    """No reverse -- the old Attribute/AttributeValue tables this reads from are dropped in 0027, matching the same one-way precedent 0006_brand_copy_logo_data already established for this app."""


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0025_flavour_schema"),
    ]

    operations = [
        migrations.RunPython(copy_weight_and_flavours, noop_reverse),
    ]
