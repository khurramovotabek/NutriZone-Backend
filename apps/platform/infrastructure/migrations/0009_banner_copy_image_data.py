from django.db import migrations


def copy_image_data_forward(apps, schema_editor):
    """Media Asset architecture removal (Banner), step 2 of 3: for every Banner that currently has a real `image` (ProductMediaAsset FK), copy its real storage_path/thumbnail_paths into the new direct fields. Real, existing production data is preserved -- nothing is regenerated or re-uploaded."""
    Banner = apps.get_model("platform", "Banner")
    for banner in Banner.objects.exclude(image=None).select_related("image"):
        banner.image_storage_path = banner.image.storage_path
        banner.image_thumbnail_paths = banner.image.thumbnail_paths
        banner.save(update_fields=["image_storage_path", "image_thumbnail_paths"])


def copy_image_data_backward(apps, schema_editor):
    """Reverse: best-effort only -- cannot recreate a ProductMediaAsset row with its original id/checksum, so this is a no-op."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("platform", "0008_banner_direct_image_fields"),
    ]

    operations = [
        migrations.RunPython(copy_image_data_forward, copy_image_data_backward),
    ]
