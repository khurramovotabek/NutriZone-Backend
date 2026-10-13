from django.db import migrations


def copy_media_data_forward(apps, schema_editor):
    """Media Asset architecture removal (ProductMedia), step 2 of 3: for every ProductMedia (media_asset is PROTECT/required, so every real row has one), copy its real storage_path/thumbnail_paths/etc into the new direct fields. Real, existing production data is preserved -- nothing is regenerated or re-uploaded."""
    ProductMedia = apps.get_model("products", "ProductMedia")
    for media in ProductMedia.objects.select_related("media_asset").all():
        asset = media.media_asset
        media.storage_path = asset.storage_path
        media.thumbnail_paths = asset.thumbnail_paths
        media.has_webp_variant = asset.has_webp_variant
        media.width_px = asset.width_px
        media.height_px = asset.height_px
        media.checksum_sha256 = asset.checksum_sha256 or ""
        media.save(update_fields=["storage_path", "thumbnail_paths", "has_webp_variant", "width_px", "height_px", "checksum_sha256"])


def copy_media_data_backward(apps, schema_editor):
    """Reverse: best-effort only -- cannot recreate a ProductMediaAsset row with its original id/checksum, so this is a no-op."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0011_productmedia_direct_fields"),
    ]

    operations = [
        migrations.RunPython(copy_media_data_forward, copy_media_data_backward),
    ]
