"""The global anon/user throttle tiers skip our own storefront server (X-Internal-Token), nobody else."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from rest_framework.test import APIRequestFactory

from core.ratelimit.throttles import AnonRateThrottle, is_trusted_server

pytestmark = pytest.mark.unit

TOKEN = "t" * 40


@pytest.fixture
def rates(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"anon": "2/min", "user": "2/min"}}
    AnonRateThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    cache.clear()
    yield
    from rest_framework.settings import api_settings

    AnonRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
    cache.clear()


def _allowed(headers: dict[str, str], times: int) -> list[bool]:
    factory = APIRequestFactory()
    out = []
    for _ in range(times):
        request = factory.get("/api/v1/products/search", REMOTE_ADDR="172.18.0.1", **headers)
        request.user = AnonymousUser()
        out.append(AnonRateThrottle().allow_request(request, None))
    return out


def test_storefront_server_with_the_token_is_never_throttled(settings, rates):
    settings.INTERNAL_API_TOKEN = TOKEN
    assert _allowed({"HTTP_X_INTERNAL_TOKEN": TOKEN}, 5) == [True] * 5


def test_without_or_with_a_wrong_token_the_limit_applies(settings, rates):
    settings.INTERNAL_API_TOKEN = TOKEN
    assert _allowed({}, 3) == [True, True, False]
    cache.clear()
    assert _allowed({"HTTP_X_INTERNAL_TOKEN": "x" * 40}, 3) == [True, True, False]


def test_an_empty_or_short_configured_token_disables_the_bypass(settings):
    request = APIRequestFactory().get("/", HTTP_X_INTERNAL_TOKEN="")
    settings.INTERNAL_API_TOKEN = ""
    assert is_trusted_server(request) is False
    settings.INTERNAL_API_TOKEN = "short"
    request = APIRequestFactory().get("/", HTTP_X_INTERNAL_TOKEN="short")
    assert is_trusted_server(request) is False


def test_production_settings_use_the_bypassing_classes():
    from config.settings import base  # the testing settings switch throttling off altogether

    assert base.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] == [
        "core.ratelimit.throttles.AnonRateThrottle",
        "core.ratelimit.throttles.UserRateThrottle",
    ]
