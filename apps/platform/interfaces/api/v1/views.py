"""
Platform API views.

Thin per Django Implementation Blueprint §3: each view deserializes
the request, calls exactly one Application Service (built via
infrastructure/composition.py), and returns the result through the
standard response envelope. Matches `apps/products/interfaces/api/v1/
views.py`'s pattern exactly.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.platform.domain.aggregates import UNSET
from apps.platform.infrastructure import composition
from apps.platform.interfaces.api.v1.permissions import ManageFeatureFlags
from apps.platform.interfaces.api.v1.serializers import (
    ContactMessageCreateSerializer, DefineFeatureFlagSerializer, EvaluatedFlagsSerializer, FeatureFlagSerializer, UpdateFeatureFlagSerializer,
)
from common.responses import success_response
from core.flags.definitions import FlagContext
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _flag_payload(flag) -> dict:
    return {"id": str(flag.id), "key": flag.key, "is_globally_enabled": flag.is_globally_enabled, "rollout_percentage": flag.rollout_percentage, "rollout_scope": flag.rollout_scope}


class SiteSettingsPublicView(APIView):
    """`GET /settings/public` -- real, public (AllowAny), read-only. Exposes only public-safe SiteSettings fields (site_name, support_phone, support_email, address, working_hours, telegram_username, telegram_channel_url, instagram_url, primary_color) for the storefront's Contact page/footer and the bot's own social-links menu button -- never the admin-only fields (max_concurrent_orders, feature toggles, etc)."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Platform"], summary="Get public site settings", responses={200: OpenApiResponse(description="Public site settings")})
    def get(self, request):
        settings_obj = composition.build_get_site_settings()
        return success_response(data={
            "site_name": settings_obj.site_name,
            "support_phone": settings_obj.support_phone,
            "support_email": settings_obj.support_email,
            "address": settings_obj.address,
            "working_hours": settings_obj.working_hours,
            "telegram_username": settings_obj.telegram_username,
            "telegram_channel_url": settings_obj.telegram_channel_url,
            "instagram_url": settings_obj.instagram_url,
            "primary_color": settings_obj.primary_color,
            "verification": _verification_codes(),
            "requisites": _seller_requisites(),
            **_brand_payload(request),
        })


def _verification_codes() -> dict:
    """Search-engine ownership codes (Dashboard → Sozlamalar → Qidiruv tizimlari) for the storefront's <meta> tags."""
    from apps.platform.infrastructure.models import SiteSettings

    row = SiteSettings.objects.filter(pk=1).values("google_site_verification", "yandex_verification", "bing_verification").first() or {}
    return {"google": row.get("google_site_verification", ""), "yandex": row.get("yandex_verification", ""), "bing": row.get("bing_verification", "")}


def _seller_requisites() -> dict:
    """The seller's legal details (Dashboard → Chek sozlamalari) -- printed on every receipt, shown in the public offer."""
    from apps.receipts.infrastructure.models import ReceiptSettings

    try:
        r = ReceiptSettings.get()
    except Exception:  # noqa: BLE001 - the public settings must load even without the receipts table
        return {"legal_name": "", "tin": "", "address": "", "phone": ""}
    return {"legal_name": r.legal_name, "tin": r.tin, "address": r.address, "phone": r.phone}


def _brand_payload(request) -> dict:
    """The storefront's whole brand (name, short name, logo, colours) -- see apps/platform/infrastructure/branding.py."""
    from apps.platform.infrastructure.branding import brand

    b = brand()
    logo = request.build_absolute_uri(b["logo_url"]) if b["logo_url"] else None
    return {"brand": {"name": b["name"], "short_name": b["short_name"] or b["name"], "logo_url": logo,
                      "primary_color": b["primary_color"], "secondary_color": b["secondary_color"], "accent_color": b["accent_color"]}}


class BannerListView(APIView):
    """`GET /settings/banners` -- real, public (AllowAny), read-only. Returns only is_active=True banners, ordered by sort_order, for the storefront's homepage hero slider."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Platform"], summary="List active homepage banners", responses={200: OpenApiResponse(description="Active banners")})
    def get(self, request):
        from django.conf import settings as django_settings

        from apps.platform.infrastructure.models import Banner

        from common.utils.localization import resolve_locale

        locale = resolve_locale(request, request.query_params.get("locale"))
        banners = Banner.objects.filter(is_active=True).order_by("sort_order", "-created_at")
        data = []
        for banner in banners:
            image_url = None
            if banner.image_storage_path:
                # The hero is full-width (2560 px on a retina laptop): send the full-resolution original -- the
                # storefront's image optimizer serves each screen its own size; the 800 px thumbnail only blurred.
                path = banner.image_storage_path
                base = (getattr(django_settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
                image_url = path if path.startswith(("http://", "https://")) else f"{base}{django_settings.MEDIA_URL}{path}"
            data.append({
                "id": str(banner.id), "title": banner.localized("title", locale), "subtitle": banner.localized("subtitle", locale),
                "cta_text": banner.localized("cta_text", locale), "cta_url": banner.cta_url, "image_url": image_url,
                "duration_seconds": banner.duration_seconds,
            })
        return success_response(data=data)


class FeatureFlagListView(APIView):
    """`GET /settings/feature-flags` (evaluate) + `POST /settings/feature-flags` (define) -- REST API Blueprint §13.18."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [ManageFeatureFlags()]

    @extend_schema(tags=["Platform"], summary="Evaluated feature flags for the current context", responses={200: EvaluatedFlagsSerializer})
    def get(self, request):
        user = getattr(request, "user", None)
        context = FlagContext(
            user_id=getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None,
            store_id=next(iter(getattr(user, "store_ids", []) or []), None) if getattr(user, "is_authenticated", False) else None,
            environment=None,
        )
        evaluate_fn = composition.build_flag_evaluator(context)
        flags = composition.build_evaluate_flags().execute(evaluate_fn)
        return success_response(data={"flags": flags})

    @extend_schema(tags=["Platform"], summary="Define a feature flag (staff)", request=DefineFeatureFlagSerializer, responses={201: FeatureFlagSerializer, **_responses(401, 403, 409, 422)})
    def post(self, request):
        serializer = DefineFeatureFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor_id = getattr(request.user, "id", None)
        flag = composition.build_define_feature_flag(actor_id=actor_id).execute(**serializer.validated_data)
        return success_response(data=_flag_payload(flag), status_code=201)


class FeatureFlagDetailView(APIView):
    """`PATCH /settings/feature-flags/{id}` (update rollout rule) -- REST API Blueprint §13.18."""

    permission_classes = [ManageFeatureFlags]

    @extend_schema(tags=["Platform"], summary="Update a feature flag's rollout rule (staff)", request=UpdateFeatureFlagSerializer, responses={200: FeatureFlagSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, flag_id: str):
        serializer = UpdateFeatureFlagSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor_id = getattr(request.user, "id", None)
        flag = composition.build_update_feature_flag(actor_id=actor_id).execute(
            flag_id=uuid.UUID(flag_id),
            is_globally_enabled=data.get("is_globally_enabled"),
            rollout_percentage=data["rollout_percentage"] if "rollout_percentage" in data else UNSET,
            rollout_scope=data.get("rollout_scope"),
        )
        return success_response(data=_flag_payload(flag))


class ContactMessageThrottle(ScopedRateLimitThrottle):
    scope = "platform.contact_message"
    limit = 3
    window_seconds = 3600
    identifier_source = "field:email"


class ContactMessageCreateView(APIView):
    """`POST /contact-messages` -- real, public (AllowAny) Contact page form submission. Writes a real ContactMessage row an admin reviews from the Dashboard (see ContactMessageAdmin) -- never a fake "sent" response with nowhere for the message to actually go."""

    permission_classes = [AllowAny]
    throttle_classes = [ContactMessageThrottle]

    @extend_schema(tags=["Platform"], summary="Submit a Contact page message", request=ContactMessageCreateSerializer, responses={201: OpenApiResponse(description="Message received"), **_responses(422, 429)})
    def post(self, request):
        serializer = ContactMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.platform.infrastructure.models import ContactMessage

        message = ContactMessage.objects.create(**serializer.validated_data)
        return success_response(data={"id": str(message.id)}, status_code=201)
