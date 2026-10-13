from django.db import migrations, models


class Migration(migrations.Migration):
    """Media Asset architecture removal (Certificate), step 1 of 4: add the new direct file-storage fields alongside the existing `document_media_asset` FK, so step 2 (a real data migration) can copy any existing Certificate's real document into them before `document_media_asset` is ever removed in step 3, and ProductMediaAsset itself is deleted in step 4."""

    dependencies = [
        ("products", "0014_alter_productmedia_storage_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="certificate",
            name="document_storage_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="certificate",
            name="document_thumbnail_paths",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
