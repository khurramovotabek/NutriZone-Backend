"""NutriZoneAnalyticsBot scheduled reports (beat rows are created by `manage.py analytics_bot_setup`)."""
from __future__ import annotations

from celery import shared_task


@shared_task(queue="default", name="telegram_bot.analytics_report")
def analytics_report(kind: str) -> dict:
    """kind = today (evening pulse) | week (Monday, last week) | month (1st, last month); once per period and recipient."""
    from apps.telegram_bot.infrastructure.analytics_bot import send_scheduled

    return send_scheduled(kind)


@shared_task(queue="default", name="telegram_bot.store_posts")
def store_posts() -> dict:
    """Every 30 s (beat, migration 0009): branch owners' own feeds -- till sales, assigned online orders and their status (Orders bot), unanswered store chats (Analytics bot)."""
    from apps.telegram_bot.infrastructure.store_posts import run

    return run()


@shared_task(queue="default", name="telegram_bot.send_post")
def send_post(post_id: str) -> dict:
    """Dashboard → Telegram → Postlar: one rich post to the channel / subscribers / customers."""
    from apps.telegram_bot.infrastructure.posts import send

    return send(post_id)


@shared_task(queue="default", name="telegram_bot.channel_autopost")
def channel_autopost() -> dict:
    """Every 15 min: new products / discounts / back-in-stock posts to the shop channel (when enabled)."""
    from apps.telegram_bot.infrastructure.channel_autopost import run

    return run()
