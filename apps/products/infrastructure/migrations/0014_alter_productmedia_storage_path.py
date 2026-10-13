from django.db import migrations, models


class Migration(migrations.Migration):
    """Media Asset architecture removal (ProductMedia), final cleanup: storage_path was temporarily blank=True in step 1 (so existing rows could be added with an empty default before step 2's data migration filled them in) -- now tightened to match the model's real, final definition (every ProductMedia row must have a real storage_path)."""

    dependencies = [
        ("products", "0013_remove_productmedia_media_asset"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productmedia",
            name="storage_path",
            field=models.CharField(max_length=500),
        ),
    ]
