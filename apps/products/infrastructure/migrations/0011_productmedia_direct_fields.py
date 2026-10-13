from django.db import migrations, models


class Migration(migrations.Migration):
    """Media Asset architecture removal (ProductMedia), step 1 of 3: add the new direct file-storage fields alongside the existing `media_asset` FK, so step 2 (a real data migration) can copy every existing ProductMedia's real file data into them before `media_asset` is ever removed in step 3."""

    dependencies = [
        ("products", "0010_remove_category_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="productmedia",
            name="storage_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="productmedia",
            name="thumbnail_paths",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="productmedia",
            name="has_webp_variant",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="productmedia",
            name="width_px",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="productmedia",
            name="height_px",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="productmedia",
            name="checksum_sha256",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
