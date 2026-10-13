# Final cleanup step -- drops ProductVariant.weight_grams (copied
# forward to weight_value by 0026) and the entire old
# Attribute/AttributeValue/VariantAttributeValue system (copied
# forward to Flavour/FlavourTranslation/ProductFlavour by 0026),
# per the explicit product decision to remove it "barcha bog'lanishlar
# ham xavfsiz" (all relations safely). Matches this app's own
# 0007_remove_brand_logo precedent for this exact add -> copy -> remove
# shape.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0026_flavour_copy_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="productvariant",
            name="weight_grams",
        ),
        migrations.RemoveConstraint(
            model_name="attributetranslation",
            name="uq_attribute_translations_attribute_locale",
        ),
        migrations.RemoveConstraint(
            model_name="attributevalue",
            name="uq_attribute_values_attribute_code",
        ),
        migrations.RemoveConstraint(
            model_name="attributevaluetranslation",
            name="uq_attr_value_translations_value_locale",
        ),
        migrations.RemoveIndex(
            model_name="variantattributevalue",
            name="catalog_var_attribu_3042f2_idx",
        ),
        migrations.RemoveConstraint(
            model_name="variantattributevalue",
            name="uq_variant_attribute_values_variant_value",
        ),
        migrations.RemoveField(
            model_name="attributetranslation",
            name="attribute",
        ),
        migrations.RemoveField(
            model_name="attributevalue",
            name="attribute",
        ),
        migrations.RemoveField(
            model_name="attributevaluetranslation",
            name="attribute_value",
        ),
        migrations.RemoveField(
            model_name="variantattributevalue",
            name="attribute_value",
        ),
        migrations.RemoveField(
            model_name="variantattributevalue",
            name="variant",
        ),
        migrations.DeleteModel(
            name="AttributeTranslation",
        ),
        migrations.DeleteModel(
            name="Attribute",
        ),
        migrations.DeleteModel(
            name="AttributeValueTranslation",
        ),
        migrations.DeleteModel(
            name="AttributeValue",
        ),
        migrations.DeleteModel(
            name="VariantAttributeValue",
        ),
    ]
