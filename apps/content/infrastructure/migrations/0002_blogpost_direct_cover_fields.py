from django.db import migrations, models


class Migration(migrations.Migration):
    """Media Asset architecture removal (BlogPost), step 1 of 3: add the new direct file-storage fields alongside the existing `cover_image` FK, so step 2 (a real data migration) can copy every existing BlogPost's real cover image into them before `cover_image` is ever removed in step 3."""

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogpost",
            name="cover_image_storage_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="cover_image_thumbnail_paths",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
