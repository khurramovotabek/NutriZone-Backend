from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Media Asset architecture removal, step 1 of 3: add the new direct
    file-storage fields alongside the existing `logo` FK, so step 2
    (a real data migration) can copy every existing Brand's real logo
    into them before `logo` is ever removed in step 3. No data loss --
    the old field is untouched here.
    """

    dependencies = [
        ("products", "0004_wishlistitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="brand",
            name="logo_storage_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="brand",
            name="logo_thumbnail_paths",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
