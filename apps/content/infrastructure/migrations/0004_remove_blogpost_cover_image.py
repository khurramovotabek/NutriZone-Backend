from django.db import migrations


class Migration(migrations.Migration):
    """Media Asset architecture removal (BlogPost), step 3 of 3: remove the old `cover_image` FK now that every real BlogPost's cover image data is safely copied into cover_image_storage_path/cover_image_thumbnail_paths (step 2)."""

    dependencies = [
        ("content", "0003_blogpost_copy_cover_image_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="blogpost",
            name="cover_image",
        ),
    ]
