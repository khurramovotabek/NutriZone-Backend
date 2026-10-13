"""
Geo & Location `/api/v1/geo/...` URL routing.

Every collection endpoint (list+create) is ONE view class on ONE path
entry -- the exact bug found and fixed in the Products module
(two view classes on one path leaves the second unreachable, since
Django resolves by path pattern, not HTTP method) is avoided here by
construction, not by a later fix.
"""
from __future__ import annotations

from django.urls import path

from apps.geo.interfaces.api.v1 import views

app_name = "geo"

urlpatterns = [
    # --- Public: hierarchy reads ---
    path("countries", views.CountryListView.as_view(), name="countries-list"),
    path("countries/<str:country_id>/regions", views.RegionListView.as_view(), name="regions-list"),
    path("regions/<str:region_id>/districts", views.DistrictListView.as_view(), name="districts-list"),
    path("cities", views.CityListView.as_view(), name="cities-list"),
    path("cities/<str:city_id>", views.CityDetailView.as_view(), name="cities-detail"),
    path("cities/<str:city_id>/neighborhoods", views.NeighborhoodListView.as_view(), name="neighborhoods-list"),
    path("cities/<str:city_id>/ancestors", views.CityAncestorsView.as_view(), name="cities-ancestors"),
    # --- Public: search / geocoding / maps ---
    path("locations/search", views.LocationSearchView.as_view(), name="locations-search"),
    path("locations/autocomplete", views.LocationAutocompleteView.as_view(), name="locations-autocomplete"),
    path("locations/reverse-geocode", views.ReverseGeocodeView.as_view(), name="locations-reverse-geocode"),
    path("locations/bounding-box", views.BoundingBoxCitiesView.as_view(), name="locations-bounding-box"),
    path("locations/locate", views.LocateView.as_view(), name="locations-locate"),
    path("locations/geocode", views.GeocodeView.as_view(), name="locations-geocode"),
    path("locations/parse-link", views.ParseMapLinkView.as_view(), name="locations-parse-link"),
    # --- Addresses (self-service) ---
    path("addresses", views.AddressListCreateView.as_view(), name="addresses-list-create"),
    path("addresses/validate", views.ValidateAddressView.as_view(), name="addresses-validate"),
    path("addresses/normalize", views.NormalizeAddressView.as_view(), name="addresses-normalize"),
    path("addresses/<str:address_id>", views.AddressDetailView.as_view(), name="addresses-detail"),
    path("addresses/<str:address_id>/coordinates", views.AddressAssignCoordinatesView.as_view(), name="addresses-assign-coordinates"),
    # --- Admin: hierarchy CRUD ---
    path("admin/countries", views.AdminCountryListCreateView.as_view(), name="admin-countries-list-create"),
    path("admin/countries/<str:country_id>", views.AdminCountryDetailView.as_view(), name="admin-countries-detail"),
    path("admin/countries/<str:country_id>/regions", views.AdminRegionListCreateView.as_view(), name="admin-regions-list-create"),
    path("admin/regions/<str:region_id>", views.AdminRegionDetailView.as_view(), name="admin-regions-detail"),
    path("admin/regions/<str:region_id>/districts", views.AdminDistrictListCreateView.as_view(), name="admin-districts-list-create"),
    path("admin/districts/<str:district_id>", views.AdminDistrictDetailView.as_view(), name="admin-districts-detail"),
    path("admin/cities", views.AdminCityListCreateView.as_view(), name="admin-cities-list-create"),
    path("admin/cities/<str:city_id>", views.AdminCityDetailView.as_view(), name="admin-cities-detail"),
    path("admin/cities/<str:city_id>/neighborhoods", views.AdminNeighborhoodListCreateView.as_view(), name="admin-neighborhoods-list-create"),
    path("admin/neighborhoods/<str:neighborhood_id>", views.AdminNeighborhoodDetailView.as_view(), name="admin-neighborhoods-detail"),
]
