"""
Real, live-verified regression test: UserProfileSerializer previously
exposed only `profile_picture_media_id` (a raw UUID, unusable by a
frontend as an image URL) -- no way to actually render the current
avatar. `avatar_url` resolves the user's own most recent
UserAvatarAsset and returns a real, renderable thumbnail path. Every
scenario here was proven live via a real avatar upload through the
actual REST endpoints before being formalized.
"""
from __future__ import annotations

import io
import json
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from apps.identity.infrastructure import models as identity_orm
from apps.identity.infrastructure.security import hash_otp_code

pytestmark = pytest.mark.django_db


def _real_authenticated_client() -> tuple[Client, dict]:
    client = Client()
    phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
    client.post("/api/v1/identity/auth/request-otp", data=json.dumps({"phone_number": phone}), content_type="application/json")
    challenge = identity_orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
    challenge.code_hash = hash_otp_code("999999")
    challenge.save(update_fields=["code_hash"])
    response = client.post("/api/v1/identity/auth/verify-otp", data=json.dumps({"phone_number": phone, "code": "999999"}), content_type="application/json")
    access_token = json.loads(response.content)["data"]["access_token"]
    return client, {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}


def _real_jpeg_bytes(size=(300, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buf, format="JPEG")
    return buf.getvalue()


class TestProfileAvatarUrl:
    def test_avatar_url_is_none_before_any_upload(self):
        client, auth = _real_authenticated_client()
        response = client.get("/api/v1/identity/users/me", **auth)
        assert response.status_code == 200
        assert json.loads(response.content)["data"]["avatar_url"] is None

    def test_avatar_url_becomes_real_after_upload(self):
        client, auth = _real_authenticated_client()
        upload_response = client.post("/api/v1/identity/users/me/avatar", data={"avatar": SimpleUploadedFile("avatar.jpg", _real_jpeg_bytes(), content_type="image/jpeg")}, **auth)
        assert upload_response.status_code == 201

        get_response = client.get("/api/v1/identity/users/me", **auth)
        avatar_url = json.loads(get_response.content)["data"]["avatar_url"]
        assert avatar_url is not None
        assert "small" in avatar_url

    def test_full_profile_update_persists_all_fields(self):
        client, auth = _real_authenticated_client()
        response = client.patch(
            "/api/v1/identity/users/me",
            data=json.dumps({"full_name": "Ali Karimov", "email": "ali@example.com", "birthday": "1995-05-20", "height_cm": 178, "weight_kg": 75, "goal": "muscle_gain"}),
            content_type="application/json",
            **auth,
        )
        assert response.status_code == 200
        data = json.loads(response.content)["data"]
        assert data["full_name"] == "Ali Karimov"
        assert data["email"] == "ali@example.com"
        assert data["birthday"] == "1995-05-20"
        assert data["height_cm"] == 178
        assert data["weight_kg"] == 75
        assert data["goal"] == "muscle_gain"


def test_reading_the_profile_is_not_limited_by_the_update_budget():
    """Regression: GET /users/me shared the 30/hour profile-update throttle, so ordinary browsing locked customers out."""
    client, auth = _real_authenticated_client()
    statuses = {client.get("/api/v1/identity/users/me", **auth).status_code for _ in range(35)}
    assert statuses == {200}
