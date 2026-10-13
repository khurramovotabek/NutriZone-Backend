"""
NutriZone Admin "Settings" premium page -- data aggregation.

SiteSettings (branding/contact) is edited on this page; environment-
variable-based configuration (Telegram bot token/username/webhook
secret, SMS login toggle) is shown next to it as read-only status.
Feature flags are deliberately not part of the dashboard (product
decision: unnecessary complexity) -- they stay governed via the API.
"""
from __future__ import annotations

from django.conf import settings as django_settings


class SettingsOverviewAggregator:
    def integration_status(self) -> dict:
        """
        Real presence checks only -- never exposes a token/secret
        value itself, matching reports_view.py's own
        telegram_status_view precedent exactly (Configured/Not
        Configured, nothing more).
        """
        return {
            "telegram_bot_token_configured": bool(getattr(django_settings, "TELEGRAM_BOT_TOKEN", None)),
            "telegram_bot_username_configured": bool(getattr(django_settings, "TELEGRAM_BOT_USERNAME", None)),
            "telegram_webhook_secret_configured": bool(getattr(django_settings, "TELEGRAM_WEBHOOK_SECRET", None)),
            "telegram_auto_webhook_enabled": bool(getattr(django_settings, "TELEGRAM_AUTO_SET_WEBHOOK", False)),
            "telegram_gateway_mode": getattr(django_settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled"),
            "sms_login_enabled": bool(getattr(django_settings, "NUTRIZONE_SMS_LOGIN_ENABLED", False)),
        }
