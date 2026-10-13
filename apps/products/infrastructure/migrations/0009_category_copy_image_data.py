from django.db import migrations


def copy_image_data_forward(apps, schema_editor):
    """Media Asset architecture removal (Category), step 2 of 3: for every Category that currently has a real `image` (ProductMediaAsset FK), copy its real storage_path/thumbnail_paths into the new direct fields. Real, existing production data is preserved -- nothing is regenerated or re-uploaded."""
    Category = apps.get_model("products", "Category")
    for category in Category.objects.exclude(image=None).select_related("image"):
        category.image_storage_path = category.image.storage_path
        category.image_thumbnail_paths = category.image.thumbnail_paths
        category.save(update_fields=["image_storage_path", "image_thumbnail_paths"])


def copy_image_data_backward(apps, schema_editor):
    """Reverse: best-effort only -- cannot recreate a ProductMediaAsset row with its original id/checksum, so this is a no-op."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0008_category_direct_image_fields"),
    ]

    operations = [
        migrations.RunPython(copy_image_data_forward, copy_image_data_backward),
    ]
