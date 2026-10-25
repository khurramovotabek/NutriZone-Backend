"""
Full-stack API tests for the authentication flow -- exercise the real
URL routing, serializers, views, application services, and repository
layer together against a real database (Django Implementation
Blueprint §11's "API tests" category). Marked `integration`, not
`unit`, since this is the multi-layer, real-DB tier.
"""
from __future__ import annotations

import json

import pytest
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class TestRequestOTPEndpoint:
    def test_valid_phone_number_returns_202(self, api_client, settings):
        settings.NUTRIZONE_OTP_PROVIDER = "console"
        response = api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": "+998901234567"}, format="json")
        assert response.status_code == 202
        body = response.json()
        assert body["success"] is True

    def test_invalid_phone_number_returns_422(self, api_client):
        response = api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": "not-a-phone"}, format="json")
        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["error"]["category"] == "validation"

    def test_response_envelope_shape_matches_standard(self, api_client):
        response = api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": "+998901112222"}, format="json")
        body = response.json()
        assert set(body.keys()) == {"success", "data", "meta"}
        assert "request_id" in body["meta"]


class TestVerifyOTPEndpoint:
    def test_correct_code_returns_token_pair(self, api_client):
        phone = "+998909998877"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")

        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
        assert challenge is not None

        # The real code is only known to the (console-logged) OTP
        # provider in a real flow; for this test we bypass that by
        # directly overwriting the stored hash with a known value,
        # matching the same "known challenge" pattern used in the
        # application-layer tests.
        from apps.identity.infrastructure.security import hash_otp_code

        challenge.code_hash = hash_otp_code("999999")
        challenge.save(update_fields=["code_hash"])

        response = api_client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "999999"}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["is_new_user"] is True

    def test_incorrect_code_returns_422(self, api_client):
        phone = "+998901010101"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")

        response = api_client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "000000"}, format="json")
        assert response.status_code == 422


class TestVerifyCodeOnlyEndpoint:
    """Real, product-required login path: /auth/verify-code takes only a code, no phone_number -- the website's login page never collects one."""

    def test_correct_code_returns_token_pair_without_a_phone_number(self, api_client):
        phone = "+998909998811"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")

        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
        assert challenge is not None

        from apps.identity.infrastructure.security import hash_otp_code

        challenge.code_hash = hash_otp_code("482913")
        challenge.save(update_fields=["code_hash"])

        response = api_client.post("/api/v1/identity/auth/verify-code", {"code": "482913"}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]

    def test_incorrect_code_returns_422(self, api_client):
        response = api_client.post("/api/v1/identity/auth/verify-code", {"code": "000000"}, format="json")
        assert response.status_code == 422

    def test_already_consumed_code_cannot_be_reused(self, api_client):
        phone = "+998909998822"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")
        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()

        from apps.identity.infrastructure.security import hash_otp_code

        challenge.code_hash = hash_otp_code("317654")
        challenge.save(update_fields=["code_hash"])

        first = api_client.post("/api/v1/identity/auth/verify-code", {"code": "317654"}, format="json")
        assert first.status_code == 200

        second = api_client.post("/api/v1/identity/auth/verify-code", {"code": "317654"}, format="json")
        assert second.status_code == 422

    def test_no_phone_number_field_is_required_at_all(self, api_client):
        """Confirms the serializer contract itself: only `code` is required -- an empty body (no phone_number) still validates on the `code` field alone."""
        response = api_client.post("/api/v1/identity/auth/verify-code", {}, format="json")
        assert response.status_code == 422


class TestMeEndpointPermissions:
    def test_unauthenticated_request_returns_401(self, api_client):
        response = api_client.get("/api/v1/identity/users/me")
        assert response.status_code == 401

    def test_authenticated_request_returns_profile(self, api_client):
        phone = "+998905554433"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")
        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()

        from apps.identity.infrastructure.security import hash_otp_code

        challenge.code_hash = hash_otp_code("555555")
        challenge.save(update_fields=["code_hash"])

        verify_response = api_client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "555555"}, format="json")
        access_token = verify_response.json()["data"]["access_token"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.get("/api/v1/identity/users/me")
        assert response.status_code == 200
        assert response.json()["data"]["phone_number"] == phone


class TestMeEndpointProfileUpdate:
    """
    Regression guard for a real, severe, confirmed bug: PATCH
    /users/me always raised a 500 (AttributeError: 'str' object has
    no attribute 'value') because the repository's own
    _user_to_domain() mapper loaded row.language as a raw string,
    never wrapping it in the LanguagePreference enum that
    User._snapshot() unconditionally expects -- confirmed via live
    testing against the real database, the only way to catch this
    class of bug (a fake-repository unit test cannot exercise the
    real ORM mapping layer where the defect actually lived).
    """

    def test_patch_updates_full_name_and_bio_without_crashing(self, api_client):
        phone = "+998905554434"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")
        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()

        from apps.identity.infrastructure.security import hash_otp_code

        challenge.code_hash = hash_otp_code("555555")
        challenge.save(update_fields=["code_hash"])

        verify_response = api_client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "555555"}, format="json")
        access_token = verify_response.json()["data"]["access_token"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = api_client.patch("/api/v1/identity/users/me", {"full_name": "Regression Test User", "bio": "A real, non-fabricated bio"}, format="json")

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["full_name"] == "Regression Test User"
        assert body["bio"] == "A real, non-fabricated bio"
        assert body["language"] == "uz"  # untouched by the PATCH: the default (Uzbek)

        get_response = api_client.get("/api/v1/identity/users/me")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["full_name"] == "Regression Test User"


class TestRequestTelegramLoginCodeEndpoint:
    """
    Every scenario here was proven live via a real end-to-end HTTP
    flow (request -> real mocked Telegram delivery -> verify via the
    existing, UNCHANGED /verify-otp endpoint -> real JWT) before
    being formalized. Confirms VerifyOTP correctly requires no
    knowledge of which provider delivered the code.
    """

    def test_linked_phone_receives_code_and_can_verify_via_existing_endpoint(self, api_client, settings):
        import uuid

        from apps.identity.infrastructure.security import hash_otp_code

        settings.TELEGRAM_BOT_TOKEN = "test-fake-token-for-mocked-http-only"
        phone = f"+99890{str(uuid.uuid4().int)[:7]}"
        telegram_id = int(str(uuid.uuid4().int)[:9])
        orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Telegram User", status="active", language="uz", telegram_user_id=telegram_id)

        from unittest.mock import MagicMock, patch

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"message_id": 1}})
            request_response = api_client.post("/api/v1/identity/auth/request-telegram-code", {"phone_number": phone}, format="json")

        assert request_response.status_code == 202
        sent_chat_id = mock_post.call_args.kwargs["json"]["chat_id"]
        assert sent_chat_id == str(telegram_id)

        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
        challenge.code_hash = hash_otp_code("482917")
        challenge.save(update_fields=["code_hash"])

        verify_response = api_client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "482917"}, format="json")
        assert verify_response.status_code == 200
        assert verify_response.json()["data"]["access_token"]

    def test_unlinked_phone_does_not_crash_and_does_not_fabricate_success(self, api_client):
        """Never a fabricated 202/success -- fails as a real (currently 503) delivery error rather than silently succeeding or falling back to SMS."""
        import uuid

        phone = f"+99890{str(uuid.uuid4().int)[:7]}"
        orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Unlinked User", status="active", language="uz")

        response = api_client.post("/api/v1/identity/auth/request-telegram-code", {"phone_number": phone}, format="json")

        assert response.status_code != 202
        assert response.status_code != 200
        assert response.status_code < 500 or response.json()["error"]["code"] == "OTP_DELIVERY_FAILED"


class TestTelegramAutomaticLoginEndpoints:
    """
    Every scenario here was proven live via real HTTP requests (real
    session creation, real bot /start + confirm callback, real
    status-polling that issues real JWT, real replay rejection, and
    the issued token verified against a real protected endpoint)
    before being formalized as a test.
    """

    def test_create_session_returns_deep_link_and_never_exposes_internals(self, api_client, settings):
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_bot"

        response = api_client.post("/api/v1/identity/auth/telegram/session")

        assert response.status_code == 201
        data = response.json()["data"]
        assert "session_id" in data
        assert data["telegram_url"].startswith("https://t.me/nutrizone_bot?start=")
        assert "token_hash" not in data
        assert "id" not in data

    def test_status_is_pending_before_bot_confirmation(self, api_client):
        response = api_client.post("/api/v1/identity/auth/telegram/session")
        session_id = response.json()["data"]["session_id"]

        status_response = api_client.get(f"/api/v1/identity/auth/telegram/session/{session_id}")

        assert status_response.status_code == 200
        assert status_response.json()["data"]["status"] == "pending"

    def test_full_flow_issues_real_jwt_that_authenticates_a_real_endpoint(self, api_client, settings):
        import uuid

        from apps.telegram_bot.interfaces.api.v1.views import _handle_telegram_auth_start
        from apps.telegram_bot.interfaces.callback_router import handle_callback

        settings.TELEGRAM_BOT_USERNAME = "nutrizone_bot"

        create_response = api_client.post("/api/v1/identity/auth/telegram/session")
        session_id = create_response.json()["data"]["session_id"]
        raw_token = create_response.json()["data"]["telegram_url"].split("start=")[1]

        phone = f"+99890{uuid.uuid4().int % 10_000_000:07d}"
        telegram_id = uuid.uuid4().int % 1_000_000_000
        user = orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Full Flow Test", status="active", language="uz", telegram_user_id=telegram_id)

        _handle_telegram_auth_start(raw_token, {"id": telegram_id}, {"id": telegram_id})
        handle_callback({"from": {"id": telegram_id}, "message": {"chat": {"id": telegram_id}, "message_id": 1}, "data": f"authlogin:confirm:{session_id}"})

        status_response = api_client.get(f"/api/v1/identity/auth/telegram/session/{session_id}")
        body = status_response.json()["data"]
        assert body["status"] == "verified"
        assert body["access_token"]
        assert body["user_id"] == str(user.id)

        replay_response = api_client.get(f"/api/v1/identity/auth/telegram/session/{session_id}")
        replay_body = replay_response.json()["data"]
        assert replay_body["status"] == "consumed"
        assert "access_token" not in replay_body

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")
        me_response = api_client.get("/api/v1/identity/users/me")
        assert me_response.status_code == 200

    def test_wrong_telegram_user_cannot_confirm_someone_elses_session(self, api_client):
        import uuid

        from apps.telegram_bot.interfaces.callback_router import handle_callback

        create_response = api_client.post("/api/v1/identity/auth/telegram/session")
        session_id = create_response.json()["data"]["session_id"]

        wrong_telegram_id = uuid.uuid4().int % 1_000_000_000
        handle_callback({"from": {"id": wrong_telegram_id}, "message": {"chat": {"id": wrong_telegram_id}, "message_id": 1}, "data": f"authlogin:confirm:{session_id}"})

        status_response = api_client.get(f"/api/v1/identity/auth/telegram/session/{session_id}")
        assert status_response.json()["data"]["status"] == "pending"


class TestAdminEndpointPermissionDenial:
    def test_customer_cannot_list_admin_users(self, api_client):
        """A user with no role assignments (the default for a freshly-verified customer) must be denied -- permission checks fail closed."""
        phone = "+998908887766"
        api_client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")
        challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()

        from apps.identity.infrastructure.security import hash_otp_code

        challenge.code_hash = hash_otp_code("444444")
        challenge.save(update_fields=["code_hash"])

        verify_response = api_client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "444444"}, format="json")
        access_token = verify_response.json()["data"]["access_token"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.get("/api/v1/identity/admin/users")
        assert response.status_code == 403

    def test_unauthenticated_admin_request_returns_401(self, api_client):
        response = api_client.get("/api/v1/identity/admin/users")
        assert response.status_code == 401


class TestIdentityUserProxyDRFContract:
    """
    Confirmed, severe defect: DRF's own stock UserRateThrottle (the
    global DEFAULT_THROTTLE_CLASSES entry) calls request.user.pk
    directly in get_cache_key() -- proven via direct isolation testing
    to raise AttributeError against IdentityUserProxy, which exposed
    only .id, not .pk. Any authenticated view without an explicit
    throttle_classes override (e.g. CartDetailView) would 500 on every
    successful request, since DRF's own initial() always calls
    check_throttles() after authentication and permissions succeed.
    """

    def test_identity_user_proxy_exposes_pk_matching_id(self):
        import uuid as uuid_module

        from apps.identity.infrastructure.authentication import IdentityUserProxy

        class _FakeDomainUser:
            id = uuid_module.uuid4()
            status = "active"

        domain_user = _FakeDomainUser()
        proxy = IdentityUserProxy(domain_user, store_ids=set())
        assert proxy.pk == proxy.id == domain_user.id

    def test_stock_drf_user_rate_throttle_does_not_crash_on_identity_user_proxy(self):
        """The exact real-world mechanism confirmed to crash before this fix -- DRF's own UserRateThrottle.get_cache_key(), not a synthetic reproduction."""
        import uuid as uuid_module

        from rest_framework.test import APIRequestFactory
        from rest_framework.throttling import UserRateThrottle

        from apps.identity.infrastructure.authentication import IdentityUserProxy

        class _FakeDomainUser:
            id = uuid_module.uuid4()
            status = "active"

        proxy = IdentityUserProxy(_FakeDomainUser(), store_ids=set())
        request = APIRequestFactory().get("/api/v1/cart/some-code")
        request.user = proxy

        key = UserRateThrottle().get_cache_key(request, view=None)
        assert key is not None
        assert str(proxy.id) in key
