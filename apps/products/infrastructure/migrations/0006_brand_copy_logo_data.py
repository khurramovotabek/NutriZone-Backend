from django.db import migrations


def copy_logo_data_forward(apps, schema_editor):
    """
    Media Asset architecture removal, step 2 of 3: for every Brand
    that currently has a real `logo` (ProductMediaAsset FK), copy its
    real storage_path/thumbnail_paths into the new direct fields.
    Brands with no logo are untouched (new fields stay at their
    defaults). Real, existing production data is preserved -- nothing
    is regenerated or re-uploaded.
    """
    Brand = apps.get_model("products", "Brand")
    for brand in Brand.objects.exclude(logo=None).select_related("logo"):
        brand.logo_storage_path = brand.logo.storage_path
        brand.logo_thumbnail_paths = brand.logo.thumbnail_paths
        brand.save(update_fields=["logo_storage_path", "logo_thumbnail_paths"])


def copy_logo_data_backward(apps, schema_editor):
    """Reverse: best-effort only -- cannot recreate a ProductMediaAsset row with its original id/checksum, so this is a no-op. The forward migration is the one that matters for the real removal; reversing past this point is not a supported path."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0005_brand_direct_logo_fields"),
    ]

    operations = [
        migrations.RunPython(copy_logo_data_forward, copy_logo_data_backward),
    ]
