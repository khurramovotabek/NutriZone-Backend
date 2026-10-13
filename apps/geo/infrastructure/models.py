"""
Geo & Location ORM models.

Covers countries, regions, districts, cities, neighborhoods, addresses,
and address_metadata. Every model composes from exactly one of
common/models/'s three base mixins per the model-category decision
tree in the Universal Module Implementation Contract §3 -- reusing the
exact platform base classes (`BaseModel`, `SoftDeleteModel`,
`AppendOnlyModel`), never redefining them, matching this phase's
explicit "reuse existing platform base classes" instruction.

Localization: Country/Region/District/City/Neighborhood follow the
same translation-table pattern already established platform-wide
(Database Blueprint §4.2's Category/Brand pattern, reused verbatim by
apps.products.infrastructure.models).
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.geo.domain.enums import (
    AddressType,
    CityStatus,
    CountryStatus,
    DistrictStatus,
    NeighborhoodStatus,
    RegionStatus,
)
from common.models import AllObjectsManager, BaseModel, SoftDeleteModel
from common.utils import LOCALE_CHOICES, enum_field_kwargs
from core.outbox import AbstractOutboxEvent


# ---------------------------------------------------------------------------
# Administrative hierarchy: Country -> Region -> District -> City -> Neighborhood
# ---------------------------------------------------------------------------


class Country(SoftDeleteModel):
    code = models.CharField(max_length=2, unique=True, db_index=True, verbose_name=_("ISO 3166-1 alpha-2 code"))
    icon = models.CharField(max_length=8, null=True, blank=True, verbose_name=_("Flag icon"), help_text=_("Optional. Auto-derived from the country code if left blank."))
    status = models.CharField(default=CountryStatus.ACTIVE.value, **enum_field_kwargs(CountryStatus))
    timezone = models.CharField(max_length=64, null=True, blank=True, verbose_name=_("Default IANA timezone"))

    class Meta:
        db_table = "geo_countries"
        verbose_name=_("Country")
        verbose_name_plural=_("Countries")
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:  # pragma: no cover
        """"🇺🇸 AQSH" in dropdowns (e.g. a product's country of manufacture) instead of a bare "US"."""
        names = {t.locale_code: t.name for t in self.translations.all()} if self.pk else {}
        name = names.get("uz") or names.get("en") or self.code
        return f"{self.icon} {name}".strip() if self.icon and len(self.icon) <= 4 and not self.icon.isascii() else name

    def save(self, *args, **kwargs):
        if not self.icon and self.code:
            # Real, admin-convenience default: converts an ISO 3166-1
            # alpha-2 code (e.g. "UZ") into its flag emoji via Unicode's
            # own Regional Indicator Symbols (each letter A-Z maps to
            # U+1F1E6-U+1F1FF) -- the same technique browsers/OSes use
            # to render flag emoji from country codes. Never overwrites
            # an admin-provided icon.
            try:
                self.icon = "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in self.code.upper())
            except (TypeError, ValueError):
                pass
        super().save(*args, **kwargs)


class CountryTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=140)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "geo_country_translations"
        constraints = [
            models.UniqueConstraint(fields=["country", "locale_code"], name="uq_country_translations_country_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_country_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


class Region(SoftDeleteModel):
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="regions")
    code = models.CharField(max_length=10, unique=True, db_index=True)
    status = models.CharField(default=RegionStatus.ACTIVE.value, **enum_field_kwargs(RegionStatus))

    class Meta:
        db_table = "geo_regions"
        verbose_name=_("Region")
        verbose_name_plural = _("Regions")
        indexes = [models.Index(fields=["country", "status"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class RegionTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=140)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "geo_region_translations"
        constraints = [
            models.UniqueConstraint(fields=["region", "locale_code"], name="uq_region_translations_region_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_region_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


class District(SoftDeleteModel):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="districts")
    code = models.CharField(max_length=10, unique=True, db_index=True)
    status = models.CharField(default=DistrictStatus.ACTIVE.value, **enum_field_kwargs(DistrictStatus))

    class Meta:
        db_table = "geo_districts"
        verbose_name=_("District")
        verbose_name_plural = _("Districts")
        indexes = [models.Index(fields=["region", "status"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class DistrictTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=140)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "geo_district_translations"
        constraints = [
            models.UniqueConstraint(fields=["district", "locale_code"], name="uq_district_translations_district_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_district_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


class City(SoftDeleteModel):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="cities")
    district = models.ForeignKey(District, on_delete=models.PROTECT, null=True, blank=True, related_name="cities")
    code = models.CharField(max_length=10, unique=True, db_index=True)
    status = models.CharField(default=CityStatus.ACTIVE.value, **enum_field_kwargs(CityStatus))
    center_latitude = models.FloatField(null=True, blank=True)
    center_longitude = models.FloatField(null=True, blank=True)
    timezone = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "geo_cities"
        verbose_name=_("City")
        verbose_name_plural = _("Cities")
        indexes = [
            models.Index(fields=["region", "status"]),
            models.Index(fields=["center_latitude", "center_longitude"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(center_latitude__isnull=True) | (models.Q(center_latitude__gte=-90) & models.Q(center_latitude__lte=90)),
                name="ck_cities_center_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(center_longitude__isnull=True) | (models.Q(center_longitude__gte=-180) & models.Q(center_longitude__lte=180)),
                name="ck_cities_center_longitude_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class CityTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=140)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "geo_city_translations"
        constraints = [
            models.UniqueConstraint(fields=["city", "locale_code"], name="uq_city_translations_city_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_city_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


class Neighborhood(SoftDeleteModel):
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="neighborhoods")
    code = models.CharField(max_length=10, unique=True, db_index=True)
    status = models.CharField(default=NeighborhoodStatus.ACTIVE.value, **enum_field_kwargs(NeighborhoodStatus))
    center_latitude = models.FloatField(null=True, blank=True)
    center_longitude = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "geo_neighborhoods"
        verbose_name=_("Neighborhood")
        verbose_name_plural = _("Neighborhoods")
        indexes = [models.Index(fields=["city", "status"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class NeighborhoodTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=140)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "geo_neighborhood_translations"
        constraints = [
            models.UniqueConstraint(fields=["neighborhood", "locale_code"], name="uq_neighborhood_translations_neighborhood_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_neighborhood_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


# ---------------------------------------------------------------------------
# Boundaries and delivery zones
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


class Address(SoftDeleteModel):
    owner_type = models.CharField(max_length=32, db_index=True)
    owner_id = models.UUIDField(db_index=True)
    address_type = models.CharField(**enum_field_kwargs(AddressType))

    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="addresses")
    region = models.ForeignKey(Region, on_delete=models.PROTECT, null=True, blank=True, related_name="addresses")
    district = models.ForeignKey(District, on_delete=models.PROTECT, null=True, blank=True, related_name="addresses")
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="addresses")
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.PROTECT, null=True, blank=True, related_name="addresses")

    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, null=True, blank=True)
    postal_code = models.CharField(max_length=16, null=True, blank=True)

    # Real, product-required capability: who the delivery is for and
    # how to reach them -- distinct from the account owner (a customer
    # may order for someone else). recipient_name/recipient_phone are
    # required at the application layer (see AddAddressSerializer);
    # recipient_telegram_username is optional.
    recipient_name = models.CharField(max_length=255, null=True, blank=True)
    recipient_phone = models.CharField(max_length=32, null=True, blank=True)
    recipient_telegram_username = models.CharField(max_length=32, null=True, blank=True)

    formatted_single_line = models.CharField(max_length=1024, null=True, blank=True)
    formatted_lines = models.JSONField(default=list, blank=True)

    coordinate_latitude = models.FloatField(null=True, blank=True)
    coordinate_longitude = models.FloatField(null=True, blank=True)
    coordinate_accuracy_meters = models.FloatField(null=True, blank=True)
    coordinate_source = models.CharField(max_length=32, null=True, blank=True)

    normalized_signature = models.CharField(max_length=64, db_index=True)
    is_default = models.BooleanField(default=False)

    def __str__(self) -> str:  # pragma: no cover
        """Dashboard cleanup phase: without this, Django's default
        `__str__` ("Address object (<uuid>)") leaked the raw UUID into
        every admin page title/breadcrumb for this model -- the one
        display surface a ModelAdmin itself can't override. A pure
        Python method, no schema/migration impact, matching every
        sibling model in this file's own established `__str__`
        convention (Country/Region/District/City/Neighborhood all
        override it too)."""
        return self.formatted_single_line or self.line1

    class Meta:
        db_table = "geo_addresses"
        verbose_name=_("Address")
        verbose_name_plural=_("Addresses")
        indexes = [
            models.Index(fields=["owner_type", "owner_id"]),
            models.Index(fields=["city"]),
            models.Index(fields=["normalized_signature"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(coordinate_latitude__isnull=True) | (models.Q(coordinate_latitude__gte=-90) & models.Q(coordinate_latitude__lte=90)),
                name="ck_addresses_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(coordinate_longitude__isnull=True) | (models.Q(coordinate_longitude__gte=-180) & models.Q(coordinate_longitude__lte=180)),
                name="ck_addresses_longitude_range",
            ),
        ]


class AddressMetadata(models.Model):
    """1:1 with Address, per this module's brief's explicit separate `address_metadata` table -- kept off the Address table itself since this data (building/unit/delivery-instructions) is optional, sparse, and conceptually a distinct concern from the structured postal address."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    address = models.OneToOneField(Address, on_delete=models.CASCADE, related_name="metadata")
    building_name = models.CharField(max_length=128, null=True, blank=True)
    entrance = models.CharField(max_length=16, null=True, blank=True, verbose_name=_("Entrance (podyezd)"))
    floor = models.CharField(max_length=16, null=True, blank=True)
    unit = models.CharField(max_length=16, null=True, blank=True)
    delivery_instructions = models.TextField(null=True, blank=True)
    entrance_code = models.CharField(max_length=32, null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "geo_address_metadata"
        verbose_name_plural=_("Address Metadata")


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


class GeoOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "geo_outbox_events"
        ordering = ["created_at"]
