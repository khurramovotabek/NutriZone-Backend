"""
Real, live-verified regression test for User.avatar_preview: uses
UserAvatarAsset (apps/identity/infrastructure/models.py), a real,
FK-backed model -- not a loose ProductMediaAsset lookup against
profile_picture_media_id, which was itself a real oversight corrected
in this same phase (UserAvatarAsset already existed and is the actual,
correct owner of avatar assets).
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.test import Client

from apps.identity.infrastructure import models as i_models

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestUserAvatarThumbnail:
    def test_user_with_real_avatar_shows_real_thumbnail_url_not_emoji(self, staff_client):
        customer = i_models.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active")
        i_models.UserAvatarAsset.objects.create(
            id=uuid.uuid4(), user=customer, storage_path="avatars/user.webp", thumbnail_paths={"small": "avatars/user_small.webp"}, checksum_sha256="a" * 64,
        )

        response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "avatars/user_small.webp" in body
        assert "🖼️" not in body

    def test_user_without_avatar_shows_fallback_not_broken(self, staff_client):
        i_models.User.objects.create(id=uuid.uuid4(), phone_number=f"+99891{uuid.uuid4().int % 10000000:07d}", full_name="Aziz Karimov", status="active")

        response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
        assert 'class="nzi-av "' in response.content.decode() and ">AK</span>" in response.content.decode()  # initials, never a broken image
