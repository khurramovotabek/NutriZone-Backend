from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load NutriZone's 3-level category tree (uz/ru/en names, descriptions, slugs); idempotent -- never duplicates or overwrites edits."

    def handle(self, *args, **options):
        from apps.products.infrastructure.category_catalog import seed_categories

        seed_categories(stdout=self.stdout)
