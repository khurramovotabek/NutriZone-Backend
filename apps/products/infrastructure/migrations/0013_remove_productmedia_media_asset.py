from django.db import migrations


class Migration(migrations.Migration):
    """Media Asset architecture removal (ProductMedia), step 3 of 3: remove the old `media_asset` FK now that every real ProductMedia's file data is safely copied into storage_path/thumbnail_paths/etc (step 2)."""

    dependencies = [
        ("products", "0012_productmedia_copy_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="productmedia",
            name="media_asset",
        ),
    ]
