from django.db import migrations


class Migration(migrations.Migration):
    """Media Asset architecture removal (Certificate), step 3 of 4: remove the old `document_media_asset` FK now that every real Certificate's document data is safely copied into document_storage_path/document_thumbnail_paths (step 2). This is also the last real FK into ProductMediaAsset anywhere in the project -- step 4 deletes the model itself."""

    dependencies = [
        ("products", "0016_certificate_copy_document_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="certificate",
            name="document_media_asset",
        ),
    ]
