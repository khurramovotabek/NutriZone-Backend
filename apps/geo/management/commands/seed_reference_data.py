"""python manage.py seed_reference_data -- countries (with flags), Uzbekistan's regions and cities, package types; uz/ru/en. Safe to re-run."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.geo.infrastructure import reference_data as ref


class Command(BaseCommand):
    help = "Loads/refreshes reference data: countries, Uzbekistan regions + cities, product package types (uz/ru/en)."

    def add_arguments(self, parser):
        parser.add_argument("--only", choices=["countries", "uzbekistan", "packages"], help="Load just one part.")

    @transaction.atomic
    def handle(self, *args, only=None, **options):
        if only in (None, "countries"):
            self.stdout.write(self.style.SUCCESS(f"Countries: {ref.seed_countries()}"))
        if only in (None, "uzbekistan"):
            result = ref.seed_uzbekistan()
            self.stdout.write(self.style.SUCCESS(f"Uzbekistan: {result['regions']} regions, {result['cities']} cities"))
            for note in result["notes"]:
                self.stdout.write(f"  fixed: {note}")
        if only in (None, "packages"):
            self.stdout.write(self.style.SUCCESS(f"Packages: {ref.seed_packages()}"))
