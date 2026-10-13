from django.db import migrations


class Migration(migrations.Migration):
    """Media Asset architecture removal (Banner), step 3 of 3: remove the old `image` FK now that every real Banner's image data is safely copied into image_storage_path/image_thumbnail_paths (step 2)."""

    dependencies = [
        ("platform", "0009_banner_copy_image_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="banner",
            name="image",
        ),
    ]
