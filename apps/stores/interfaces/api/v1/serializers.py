"""Public, read-only Store API serializers."""
from __future__ import annotations

from rest_framework import serializers


class MyStoreUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    phone_numbers = serializers.ListField(child=serializers.CharField(), required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    telegram_username = serializers.CharField(max_length=64, required=False, allow_blank=True)
    instagram_username = serializers.CharField(max_length=64, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    working_hours = serializers.DictField(required=False)
    special_hours = serializers.ListField(required=False)
    tagline = serializers.CharField(max_length=140, required=False, allow_blank=True)
    amenities = serializers.ListField(child=serializers.CharField(max_length=32), required=False, max_length=20)
    landmark = serializers.CharField(max_length=255, required=False, allow_blank=True)
    pickup_enabled = serializers.BooleanField(required=False)
    pickup_note = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate_amenities(self, value):
        from apps.stores.infrastructure.models import STORE_AMENITIES

        unknown = [v for v in value if v not in STORE_AMENITIES]
        if unknown:
            raise serializers.ValidationError(f"Unknown amenities: {', '.join(unknown)}")
        return list(dict.fromkeys(value))

    def validate_special_hours(self, value):
        """[{date: YYYY-MM-DD, closed: bool, open: HH:MM, close: HH:MM, note}] -- at most 60 days, dates and times well-formed."""
        import re

        out = []
        for e in value[:60]:
            if not isinstance(e, dict) or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(e.get("date", ""))):
                raise serializers.ValidationError("Each special day needs a date (YYYY-MM-DD).")
            closed = bool(e.get("closed"))
            opn, cls = str(e.get("open") or ""), str(e.get("close") or "")
            # a row being edited may not have its times yet (the day then counts as closed until it does)
            if any(v and not re.match(r"^\d{2}:\d{2}$", v) for v in (opn, cls)):
                raise serializers.ValidationError(f"{e['date']}: times must look like 09:00.")
            out.append({"date": e["date"], "closed": closed, "open": "" if closed else opn, "close": "" if closed else cls, "note": str(e.get("note") or "")[:120]})
        return sorted(out, key=lambda x: x["date"])


class MyStoreProductCreateSerializer(serializers.Serializer):
    """Real, critical boundary: only ever references an EXISTING product_variant_id -- never creates or edits a product. Validated against the real ProductVariant table in the view, not trusted blindly."""

    product_variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=0)


class MyStoreProductUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)


class StoreListSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    status = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)
    cover_image_url = serializers.CharField(allow_null=True)
    address = serializers.CharField()
    city = serializers.CharField()
    district = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    is_open_now = serializers.BooleanField()
    distance_meters = serializers.FloatField(allow_null=True, required=False)
    # Field names deliberately match ProductCard's own real, existing
    # rating_average/rating_count fields (apps/products) -- one
    # consistent rating shape across the whole public API, not a
    # second, differently-named convention invented for stores.
    rating_average = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField()
    color = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_null=True)
    today_hours = serializers.DictField(required=False)
    product_count = serializers.IntegerField(required=False, allow_null=True)
    tagline = serializers.CharField(required=False, allow_blank=True)
    amenities = serializers.ListField(child=serializers.CharField(), required=False)
    landmark = serializers.CharField(required=False, allow_blank=True)
    pickup_enabled = serializers.BooleanField(required=False)


class StoreRatingInputSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    # Optional private review -- goes to management only (never public). Omitted = keep the existing text.
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000, trim_whitespace=True)


class MyStoreRatingSerializer(serializers.Serializer):
    rating = serializers.IntegerField(allow_null=True)


class StoreMediaSerializer(serializers.Serializer):
    id = serializers.IntegerField()  # the owner's gallery removes a photo by it (DELETE /my-store/media/<id>)
    url = serializers.CharField()
    is_video = serializers.BooleanField()
    sort_order = serializers.IntegerField()


class StoreProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    product_variant_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    name = serializers.CharField()
    product_slug = serializers.CharField(allow_null=True)
    sku = serializers.CharField()
    image_url = serializers.CharField(allow_null=True)
    quantity = serializers.IntegerField()
    weight_value = serializers.FloatField(allow_null=True)
    weight_unit = serializers.CharField(allow_null=True)
    price = serializers.CharField(allow_null=True)
    currency = serializers.CharField(allow_null=True)
    compare_at_price = serializers.CharField(allow_null=True)
    discount_percent = serializers.IntegerField(allow_null=True)


class StoreDetailSerializer(StoreListSerializer):
    description = serializers.CharField()
    phone_numbers = serializers.ListField(child=serializers.CharField())
    email = serializers.CharField()
    telegram_username = serializers.CharField()
    instagram_username = serializers.CharField()
    working_hours = serializers.DictField()
    special_hours = serializers.ListField()
    media = StoreMediaSerializer(many=True)
    products = StoreProductSerializer(many=True)
    owner_full_name = serializers.CharField(allow_null=True)
    upcoming_special_days = serializers.ListField(required=False)
    pickup_note = serializers.CharField(required=False, allow_blank=True)
