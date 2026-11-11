"""Shop channel daily schedule (daily_posts.py), scheduled Dashboard posts and multi-bot delivery (posts.plan/send)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.telegram_bot.infrastructure import daily_posts as dp
from apps.telegram_bot.infrastructure import posts
from apps.telegram_bot.infrastructure.models import ChannelAutoPostSettings, ChannelPostSlot, TelegramBotSubscriber, TelegramPost

pytestmark = pytest.mark.django_db
TZ = ZoneInfo("Asia/Tashkent")
DAY = datetime(2026, 11, 11, tzinfo=TZ).date()


def _card(i, **kw):
    return {"id": f"00000000-0000-0000-0000-00000000000{i}", "slug": f"p{i}", "name": f"Mahsulot {i}", "price": "289000", "compare_at_price": None,
            "discount_percent": 0, "rating_average": None, "rating_count": 0, "size_count": 1, "flavour_count": 0, "stock_quantity": 10 * i,
            "stock_status": "in_stock", "primary_image_path": "x", "created_at": f"2026-11-0{i}", "brand_id": None, "category_id": None, **kw}


CARDS = [_card(1), _card(2, discount_percent=20, compare_at_price="361000"), _card(3)]


@pytest.fixture
def channel_on(settings):
    settings.FRONTEND_URL = "https://nutrizone.uz"
    s = ChannelAutoPostSettings.get()
    s.channel, s.daily_enabled = "@nutrizonepit", True
    s.save()
    if not s.slots.exists():  # seeded by migration 0015; recreate if a test DB was flushed
        for t, kind, head in ((10, "top", "☀️ Kun mahsuloti"), (15, "sale", "🔥 Kun taklifi"), (20, "pick", "🌙 Kechki tavsiya")):
            ChannelPostSlot.objects.create(settings=s, time=datetime(2000, 1, 1, t).time(), kind=kind, heading=head)
    return s


def test_default_slots_are_10_15_20():
    assert [f"{x.time:%H:%M}" for x in ChannelPostSlot.objects.all()] == ["10:00", "12:30", "15:00", "20:00"]
    assert ChannelPostSlot.objects.get(time="12:30").kind == "tip"  # migration 0017


def test_render_drops_lines_with_empty_variables_and_escapes():
    values = dp.variables(_card(1, name="Gold <Whey>"), "☀️ Kun mahsuloti", {"brand": "", "category": "Protein", "description": ""})
    text = dp.render("", values)
    assert "Gold &lt;Whey&gt;" in text and "☀️ Kun mahsuloti" in text and "289 000 so'm" in text
    assert "🏷" not in text and "⭐" not in text and "<i></i>" not in text  # empty brand / rating / description lines are gone
    assert "#Protein" in text and "#NutriZone" in text


def test_discount_price_line():
    values = dp.variables(CARDS[1], "", {"brand": "ON"})
    assert values["narx_qator"] == "💰 <s>361 000</s> → <b>289 000 so'm</b>  (−20%)"
    assert values["chegirma"] == "−20%"


def test_pick_by_kind_and_skips_recent():
    rng = random.Random(1)
    assert dp.pick("sale", CARDS, set(), rng)["id"] == CARDS[1]["id"]
    assert dp.pick("new", CARDS, set(), rng)["id"] == CARDS[2]["id"]
    assert dp.pick("new", CARDS, {CARDS[2]["id"]}, rng)["id"] == CARDS[1]["id"]
    assert dp.pick("sale", [CARDS[0]], set(), rng)["id"] == CARDS[0]["id"]  # no discount anywhere → falls back to the top product
    assert dp.pick("pick", CARDS, {c["id"] for c in CARDS}, rng) is not None  # all posted lately → repeat rather than stay silent


def _run(at):
    with patch.object(dp, "pool", return_value=CARDS), patch.object(dp, "_extras", side_effect=lambda cards: {c["id"]: {} for c in cards}), \
         patch.object(posts, "queue") as queue:
        result = dp.run(at)
    return result, queue


def test_slot_posts_once_inside_its_window(channel_on):
    result, queue = _run(datetime(2026, 11, 11, 10, 1, tzinfo=TZ))
    assert result["daily"] == 1 and queue.call_count == 1
    post = TelegramPost.objects.get(source="daily")
    assert post.to_channel and post.channel == "@nutrizonepit" and "☀️ Kun mahsuloti" in post.body
    assert post.dedupe_key == f"daily:{DAY:%Y%m%d}:{ChannelPostSlot.objects.get(time='10:00').pk}"
    assert _run(datetime(2026, 11, 11, 10, 2, tzinfo=TZ))[0]["daily"] == 0  # once a day
    assert _run(datetime(2026, 11, 11, 12, 0, tzinfo=TZ))[0]["daily"] == 0  # between slots
    assert _run(datetime(2026, 11, 11, 15, 0, tzinfo=TZ))[0]["daily"] == 1


def test_late_start_does_not_post_the_morning_slot_at_night(channel_on):
    assert _run(datetime(2026, 11, 11, 10, 50, tzinfo=TZ))[0]["daily"] == 0


def test_manual_channel_post_around_slot_wins(channel_on):
    TelegramPost.objects.create(title="Aksiya", body="x", to_channel=True, channel="@nutrizonepit", status="sent",
                                sent_at=datetime(2026, 11, 11, 9, 40, tzinfo=TZ))
    assert _run(datetime(2026, 11, 11, 10, 0, tzinfo=TZ))[0]["daily"] == 0


def test_disabled_schedule_posts_nothing(channel_on):
    channel_on.daily_enabled = False
    channel_on.save()
    assert _run(datetime(2026, 11, 11, 10, 0, tzinfo=TZ))[0]["daily"] == 0


def test_scheduled_post_is_queued_at_its_time(channel_on):
    when = timezone.now() + timedelta(hours=1)
    post = TelegramPost.objects.create(title="Kechki aksiya", body="x", to_channel=True, channel="@nutrizonepit")
    posts.schedule(post, when)
    assert _run(timezone.now())[0]["scheduled_sent"] == 0
    result, queue = _run(when + timedelta(seconds=30))
    assert result["scheduled_sent"] == 1 and queue.call_args.args[0].pk == post.pk


def test_one_post_through_every_bot(settings):
    settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_ORDERS_BOT_TOKEN, settings.TELEGRAM_ANALYTICS_BOT_TOKEN = "1:a", "2:b", "3:c"
    settings.TELEGRAM_ORDERS_CHAT_ID = "-100777"
    TelegramBotSubscriber.objects.create(bot="orders", chat_id=501)
    TelegramBotSubscriber.objects.create(bot="analytics", chat_id=601)
    TelegramBotSubscriber.objects.create(bot="analytics", chat_id=602, is_active=False)
    post = TelegramPost.objects.create(title="E'lon", body="<b>Yig'ilish</b> 18:00 da", to_channel=True, channel="@nutrizonepit",
                                       to_orders_channel=True, to_orders_staff=True, to_analytics_staff=True, status="queued")
    calls = []

    def fake(method, *, data=None, files=None, bot="shop"):
        calls.append((bot, method, str((data or {}).get("chat_id"))))
        return {"message_id": 5}

    with patch.object(posts, "_api", side_effect=fake), patch.object(posts, "PACE_SECONDS", 0):
        assert posts.send(post.pk) == {"sent": 4, "failed": 0}
    assert ("shop", "sendMessage", "@nutrizonepit") in calls and ("orders", "sendMessage", "-100777") in calls
    assert ("orders", "sendMessage", "501") in calls and ("analytics", "sendMessage", "601") in calls
    assert not any(c[2] == "602" for c in calls)
    assert posts.audience(post) == ["Kanal @nutrizonepit", "Buyurtmalar kanali", "Orders bot xodimlari", "Analytics bot"]


@pytest.fixture
def root():
    c = Client()
    c.force_login(get_user_model().objects.create_superuser("root_dp", "r@example.com", "x"))
    return c


def test_schedule_page_shows_today_plan_and_variables(root, channel_on):
    with patch.object(dp, "pool", return_value=CARDS), patch.object(dp, "_extras", side_effect=lambda cards: {c["id"]: {} for c in cards}):
        html = root.get("/django-admin/telegram_bot/channelautopostsettings/1/change/").content.decode()
    assert "Kanal jadvali" in html and "{narx_qator}" in html and "10:00" in html and "20:00" in html


def test_composer_schedules_for_later(root, settings):
    settings.TELEGRAM_BOT_TOKEN = "1:a"
    when = timezone.localtime() + timedelta(days=1)
    r = root.post("/django-admin/telegram_bot/telegrampost/add/", {
        "title": "Ertangi aksiya", "body": "<b>-20%</b>", "to_channel": "on", "channel": "@nutrizonepit",
        "scheduled_at": when.strftime("%Y-%m-%dT%H:%M"), "_nztg_send": "1"})
    assert r.status_code == 302
    post = TelegramPost.objects.get(title="Ertangi aksiya")
    assert post.status == "scheduled" and abs((post.scheduled_at - when).total_seconds()) < 60
    page = root.get(f"/django-admin/telegram_bot/telegrampost/{post.pk}/change/").content.decode()
    assert "Rejani bekor qilish" in page
    root.post(f"/django-admin/telegram_bot/telegrampost/{post.pk}/change/", {
        "title": "Ertangi aksiya", "body": "<b>-20%</b>", "to_channel": "on", "channel": "@nutrizonepit", "_nztg_unschedule": "1"})
    post.refresh_from_db()
    assert post.status == "draft"


def test_composer_refuses_past_time(root):
    r = root.post("/django-admin/telegram_bot/telegrampost/add/", {
        "title": "Kech", "body": "x", "to_channel": "on", "channel": "@nutrizonepit",
        "scheduled_at": (timezone.localtime() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"), "_nztg_send": "1"})
    assert r.status_code == 200 and not TelegramPost.objects.filter(title="Kech").exists()


def test_daily_tip_posts_a_knowledge_entry_once_and_walks_the_base(channel_on):
    from apps.assistant.infrastructure.models import KnowledgeEntry

    if not ChannelPostSlot.objects.filter(kind="tip").exists():
        ChannelPostSlot.objects.create(settings=channel_on, time=datetime(2000, 1, 1, 12, 30).time(), kind="tip", heading="💡 Kun maslahati")
    KnowledgeEntry.objects.update(is_active=False)
    a = KnowledgeEntry.objects.create(topic="product", priority=99, title="Kreatin turlari test", answer_uz="**Monogidrat** — eng yaxshisi. " * 8, keywords="kreatin")
    b = KnowledgeEntry.objects.create(topic="usage", priority=98, title="Protein qanday ichiladi test", answer_uz="Kuniga 1–2 porsiya _suv bilan_. " * 8)
    result, _queue = _run(datetime(2026, 11, 11, 12, 31, tzinfo=TZ))
    post = TelegramPost.objects.get(source="daily", title__startswith=dp.TIP_TITLE)
    assert result["daily"] == 1 and "💡 Kun maslahati" in post.body and ("<b>Monogidrat</b>" in post.body or "<i>suv bilan</i>" in post.body)
    first = post.title
    _run(datetime(2026, 11, 12, 12, 31, tzinfo=TZ))
    titles = set(TelegramPost.objects.filter(title__startswith=dp.TIP_TITLE).values_list("title", flat=True))
    assert len(titles) == 2 and first in titles and {f"{dp.TIP_TITLE}{a.title}", f"{dp.TIP_TITLE}{b.title}"} == titles  # no repeat
