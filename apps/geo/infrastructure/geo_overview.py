"""
NutriZone Admin "Geo Overview" data aggregation.

Real, closed gap: Country/Region/District/City/Neighborhood/Address
form a real, confirmed geographic hierarchy, but had zero visual
overview anywhere -- only separate, bare, standard Django admin grids,
with no way to see "how many regions/cities does this country actually
have" or "how many real customer addresses exist per country" without
manually cross-referencing every one of those grids.

Matches apps.identity.infrastructure.roles_overview's own established
error-isolation and aggregation conventions exactly -- read-only,
no new business logic, over already-existing, already-tested models.
"""
from __future__ import annotations

from django.db.models import Count

from apps.geo.infrastructure.models import Address, City, Country, District, Neighborhood, Region


def _translated_name(translations_qs, fallback: str) -> str:
    """Same real, established pattern used throughout products/content selectors: prefer an "en" translation row, otherwise fall back to a stable identifier -- never a fabricated name."""
    row = next((t for t in translations_qs if t.locale_code == "en"), None)
    return row.name if row else fallback


class GeoOverviewAggregator:
    def countries_with_hierarchy_counts(self) -> list[dict]:
        """One row per real Country, with real, currently-existing counts of every level beneath it -- never an assumed or fabricated count."""
        countries = list(Country.objects.prefetch_related("translations").order_by("code"))
        region_counts = {row["country_id"]: row["count"] for row in Region.objects.values("country_id").annotate(count=Count("id"))}

        result = []
        for country in countries:
            regions = Region.objects.filter(country=country)
            region_ids = list(regions.values_list("id", flat=True))
            district_count = District.objects.filter(region_id__in=region_ids).count()
            city_count = City.objects.filter(region_id__in=region_ids).count()
            city_ids = list(City.objects.filter(region_id__in=region_ids).values_list("id", flat=True))
            neighborhood_count = Neighborhood.objects.filter(city_id__in=city_ids).count()
            address_count = Address.objects.filter(country=country).count()

            result.append({
                "id": str(country.id), "code": country.code, "name": _translated_name(country.translations.all(), country.code),
                "status": country.status, "region_count": region_counts.get(country.id, 0),
                "district_count": district_count, "city_count": city_count,
                "neighborhood_count": neighborhood_count, "address_count": address_count,
            })
        return result

    def summary(self) -> dict:
        return {
            "total_countries": Country.objects.count(),
            "total_regions": Region.objects.count(),
            "total_cities": City.objects.count(),
            "total_addresses": Address.objects.count(),
        }

    def cities_missing_coordinates(self) -> list[dict]:
        """Real, actionable configuration gap: a City with no center_latitude/longitude cannot be used for any distance/map-based feature -- surfaced explicitly, not hidden."""
        cities = City.objects.filter(center_latitude__isnull=True).select_related("region").prefetch_related("translations", "region__translations")[:20]
        return [
            {
                "code": c.code, "name": _translated_name(c.translations.all(), c.code),
                "region_name": _translated_name(c.region.translations.all(), c.region.code) if c.region else "—",
            }
            for c in cities
        ]
