from django.db import migrations, models


class Migration(migrations.Migration):
    """Media Asset architecture removal (Banner), step 1 of 3: add the new direct file-storage fields alongside the existing `image` FK, so step 2 (a real data migration) can copy every existing Banner's real image into them before `image` is ever removed in step 3."""

    dependencies = [
        ("platform", "0007_banner"),
    ]

    operations = [
        migrations.AddField(
            model_name="banner",
            name="image_storage_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="banner",
            name="image_thumbnail_paths",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
