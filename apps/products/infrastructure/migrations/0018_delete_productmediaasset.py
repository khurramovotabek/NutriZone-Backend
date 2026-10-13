from django.db import migrations


class Migration(migrations.Migration):
    """
    Media Asset architecture removal, final step: delete the
    ProductMediaAsset table itself. Every real entity that used to
    reference it (Brand, Category, Banner, BlogPost, ProductMedia,
    Certificate) has already been migrated forward to its own direct
    storage_path/thumbnail_paths fields in earlier phases and earlier
    steps of this same migration chain -- by this point, no foreign
    key anywhere in the project points at this table, and dropping it
    destroys no reachable data.
    """

    dependencies = [
        ("products", "0017_remove_certificate_document_media_asset"),
        # Real, confirmed bug this closes: this migration's own docstring
        # claims Banner/BlogPost were "already migrated forward... in
        # earlier phases", but neither cross-app removal was ever
        # declared as an actual dependency here -- only same-app
        # products migrations were. Django's migration graph is free to
        # schedule ANY node the moment its OWN listed dependencies are
        # satisfied, so on a genuine from-scratch migrate, this could
        # (and, confirmed live, does) run BEFORE platform.0010 removes
        # Banner's FK to this exact model, deleting ProductMediaAsset
        # while Banner.image (platform.0007_banner) still references it
        # -- "Related model 'products.productmediaasset' cannot be
        # resolved". Explicit cross-app dependencies here are the
        # correct, standard Django fix (a `run_before` on the other side
        # would work equally well, but keeping the ordering constraint
        # on the deleting migration itself is clearer).
        ("platform", "0010_remove_banner_image"),
        ("content", "0004_remove_blogpost_cover_image"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ProductMediaAsset",
        ),
    ]
