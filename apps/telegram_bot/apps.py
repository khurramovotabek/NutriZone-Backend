from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TelegramBotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.telegram_bot"
    label = "telegram_bot"
    verbose_name = _("Telegram Bot")

    def ready(self) -> None:
        from apps.telegram_bot import (
            checks,  # noqa: F401 -- registers the Django System Check Framework hooks below
        )
        from apps.telegram_bot.infrastructure import admin, models  # noqa: F401 -- admin.py registers Telegram postlar

        self._maybe_auto_register_webhook()

    def _maybe_auto_register_webhook(self) -> None:
        """
        Real answer to "the bot should start when the backend starts":
        Telegram's Bot API is webhook-based (confirmed: no polling
        process exists or is needed anywhere in this codebase) -- the
        bot IS the `/api/v1/telegram/webhook` view, already live the
        moment the web server is. The one real missing step was
        registering that URL with Telegram via `setWebhook`, which
        this now does automatically on server startup, in the
        background, so a production deploy needs no manual step.

        Every guard below exists because `AppConfig.ready()` fires on
        EVERY management command invocation (migrate, test, shell,
        makemigrations, collectstatic) -- not just the real server
        process -- and firing a real, network-dependent Telegram API
        call during `manage.py test` or a CI `migrate` would be a real
        defect (slow, flaky, and spuriously failing with no real bot
        token configured):

        - Opt-in only (`TELEGRAM_AUTO_SET_WEBHOOK=true`) -- off by
          default, so no sandbox/CI/local-dev environment is ever
          surprised by an outbound network call it didn't ask for.
        - Requires `PUBLIC_BASE_URL` and at least one of `TELEGRAM_BOT_TOKEN`
          (customer bot) / `TELEGRAM_ORDERS_BOT_TOKEN` (separate Orders
          Bot) already configured -- silently skips otherwise rather
          than raising during Django's own startup sequence. Each
          configured bot is registered independently, via
          `telegram_set_webhook --bot customer`/`--bot orders`.
        - Only when argv[0] is a real server command (`runserver`,
          `gunicorn`, `uwsgi`, `daphne`, `uvicorn`) -- every other
          management command (migrate/test/shell/...) is explicitly
          excluded, matching Django's own documented convention for
          "should this ready() side effect run" checks.
        - Runs in a background daemon thread with a short delay,
          never blocking the request-serving process from starting,
          and never raising past this method -- a Telegram API outage
          on deploy must never prevent the web server itself from
          coming up.
        """
        import sys

        from django.conf import settings

        if not getattr(settings, "TELEGRAM_AUTO_SET_WEBHOOK", False):
            return
        if not getattr(settings, "PUBLIC_BASE_URL", None):
            return
        has_customer_bot = bool(getattr(settings, "TELEGRAM_BOT_TOKEN", None))
        has_orders_bot = bool(getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None))
        has_analytics_bot = bool(getattr(settings, "TELEGRAM_ANALYTICS_BOT_TOKEN", None) and getattr(settings, "TELEGRAM_ANALYTICS_WEBHOOK_SECRET", None))
        if not has_customer_bot and not has_orders_bot and not has_analytics_bot:
            return

        # Real, closed gap: "uvicorn" was previously included here,
        # which meant BOTH the "web" service (runserver/gunicorn, WSGI)
        # AND the "channels" service (uvicorn, ASGI -- confirmed via
        # docker-compose.yml's own `command: ["uvicorn", ...]`) would
        # independently call setWebhook on their own startup. Telegram
        # webhook registration only needs to happen once per deploy;
        # a second, redundant call gets rejected with "Too Many
        # Requests: retry after N" -- exactly the failure mode this
        # phase's own requirement explicitly called out. "web" is now
        # the sole owner of webhook registration; "channels" only
        # processes real-time features, never Telegram webhook setup.
        real_server_commands = {"runserver", "gunicorn"}
        invoked_command = sys.argv[1] if len(sys.argv) > 1 else ""
        is_real_server_process = invoked_command in real_server_commands or any(cmd in sys.argv[0] for cmd in ("gunicorn",))
        if not is_real_server_process:
            return

        import threading

        def _register():
            import logging
            import time

            from django.core.management import call_command

            time.sleep(2)  # let the app registry and DB connections finish settling first
            logger = logging.getLogger("nutrizone.telegram_bot")
            if has_customer_bot:
                try:
                    call_command("telegram_set_webhook", bot="customer")
                except Exception:  # noqa: BLE001 -- a webhook-registration failure must never crash or destabilize the running server
                    logger.exception("Automatic Telegram webhook registration failed on startup (customer bot).")
                try:
                    call_command("telegram_set_menu_button")
                except Exception:  # noqa: BLE001 -- same failure discipline: the shop button is a convenience, never a startup blocker
                    logger.exception("Setting the Telegram Mini App menu button failed on startup.")
            if has_orders_bot:
                try:
                    call_command("telegram_set_webhook", bot="orders")
                except Exception:  # noqa: BLE001 -- same failure discipline as the customer bot registration above
                    logger.exception("Automatic Telegram webhook registration failed on startup (orders bot).")
            if has_analytics_bot:
                try:
                    call_command("analytics_bot_setup")  # schedules + command menu + webhook, all idempotent
                except Exception:  # noqa: BLE001 -- same failure discipline
                    logger.exception("Automatic NutriZoneAnalyticsBot setup failed on startup.")

        threading.Thread(target=_register, daemon=True, name="telegram-webhook-autoregister").start()
