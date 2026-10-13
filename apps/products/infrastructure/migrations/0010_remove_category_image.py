from django.db import migrations


class Migration(migrations.Migration):
    """Media Asset architecture removal (Category), step 3 of 3: remove the old `image` FK now that every real Category's image data is safely copied into image_storage_path/image_thumbnail_paths (step 2)."""

    dependencies = [
        ("products", "0009_category_copy_image_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="category",
            name="image",
        ),
    ]
