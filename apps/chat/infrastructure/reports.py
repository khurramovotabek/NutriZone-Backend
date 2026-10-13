"""
Operator report for the support desk (Dashboard → Chat → Operatorlar hisoboti).

Per staff member over a period: chats they answered, messages, first-response time, closed chats, the customers'
1–5 ★ scores and low (1–2 ★) ratings.

First-response time is measured per customer *request*: a customer message that arrives while nothing is pending
starts the clock, the first staff reply stops it and is credited to whoever answered. A message written outside
working hours starts the clock when the desk opens, so a night message answered at 9:05 counts as 5 minutes, not
11 hours. Bot messages (auto-reply, order bot) never count as an answer.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.chat.infrastructure.automation import BOT_ID, TZ, chat_settings, is_open, staff_names

SLA_MINUTES = 5


def next_open(at: datetime, cfg) -> datetime:
    """`at` itself when the desk is open, otherwise the next moment it opens (within a week)."""
    if is_open(at, cfg) or not cfg.work_days:
        return at
    local = timezone.localtime(at, TZ)
    for d in range(0, 8):
        day = local.date() + timedelta(days=d)
        start = datetime.combine(day, cfg.work_start, tzinfo=TZ)
        if day.weekday() in cfg.work_days and start > local:
            return start
    return at


def first_responses(since: datetime, until: datetime | None = None) -> list[dict]:
    """Every answered customer request in support chats: {conversation_id, operator_id, minutes} (business time)."""
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel

    cfg = chat_settings()
    until = until or timezone.now()
    conv_ids = list(ConversationModel.objects.exclude(conversation_type="customer_sales").filter(
        Q(last_activity_at__gte=since) | Q(created_at__gte=since)).values_list("id", flat=True))
    customers = dict(ParticipantModel.objects.filter(conversation_id__in=conv_ids, role="customer").values_list("conversation_id", "user_id"))
    out, pending = [], {}
    rows = (MessageModel.objects.filter(conversation_id__in=conv_ids, created_at__gte=since, created_at__lt=until).exclude(sender_id=BOT_ID)
            .exclude(message_type="system").order_by("conversation_id", "created_at").values_list("conversation_id", "sender_id", "created_at"))
    for cid, sender, at in rows:
        if sender == customers.get(cid):
            pending.setdefault(cid, at)  # the clock starts at the first unanswered message
        elif cid in pending:
            asked = next_open(pending.pop(cid), cfg)
            out.append({"conversation_id": cid, "operator_id": sender, "minutes": max(0.0, (at - asked).total_seconds() / 60)})
    return out


def _fmt_minutes(m: float | None) -> str:
    if m is None:
        return "—"
    if m < 1:
        return "< 1 daq"
    if m < 60:
        return f"{round(m)} daq"
    return f"{m / 60:.1f} soat"


def operator_report(days: int = 30) -> dict:
    from apps.chat.infrastructure.models import ConversationClosing, ConversationModel, ConversationRating, MessageModel

    now = timezone.now()
    since = now - timedelta(days=days)
    names = staff_names()
    support = ConversationModel.objects.exclude(conversation_type="customer_sales").values("id")
    sent = (MessageModel.objects.filter(created_at__gte=since, sender_id__in=list(names), conversation_id__in=support).exclude(message_type="system")
            .values("sender_id").annotate(messages=Count("id"), chats=Count("conversation_id", distinct=True)))
    stats: dict = {}

    def row(op):
        return stats.setdefault(op, {"operator_id": op, "name": names.get(op, "Noma'lum xodim"), "messages": 0, "chats": 0, "responses": [], "closed": 0,
                                     "rating_avg": None, "rating_count": 0, "low": 0, "review_open": 0})

    for r in sent:
        row(r["sender_id"]).update(messages=r["messages"], chats=r["chats"])
    responses = first_responses(since, now)
    for r in responses:
        if r["operator_id"] in names:
            row(r["operator_id"])["responses"].append(r["minutes"])
    for r in ConversationClosing.objects.filter(closed_at__gte=since, operator_id__isnull=False).values("operator_id").annotate(n=Count("id")):
        row(r["operator_id"])["closed"] = r["n"]
    ratings = ConversationRating.objects.filter(created_at__gte=since)
    for r in ratings.filter(operator_id__isnull=False).values("operator_id").annotate(a=Avg("score"), n=Count("id"), low=Count("id", filter=Q(score__lte=2)),
                                                                                      open=Count("id", filter=Q(review_status="open"))):
        row(r["operator_id"]).update(rating_avg=round(r["a"], 1), rating_count=r["n"], low=r["low"], review_open=r["open"])

    rows = []
    for s in stats.values():
        mins = s.pop("responses")
        s.update(answered=len(mins), first_median=median(mins) if mins else None, first_avg=sum(mins) / len(mins) if mins else None,
                 sla=round(100 * sum(1 for m in mins if m <= SLA_MINUTES) / len(mins)) if mins else None)
        s["first_median_label"], s["first_avg_label"] = _fmt_minutes(s["first_median"]), _fmt_minutes(s["first_avg"])
        rows.append(s)
    rows.sort(key=lambda s: (-(s["answered"] or 0), -(s["messages"] or 0)))

    all_mins = [r["minutes"] for r in responses]
    agg = ratings.aggregate(a=Avg("score"), n=Count("id"), low=Count("id", filter=Q(score__lte=2)))
    totals = {
        "answered": len(all_mins), "first_median": _fmt_minutes(median(all_mins) if all_mins else None),
        "sla": round(100 * sum(1 for m in all_mins if m <= SLA_MINUTES) / len(all_mins)) if all_mins else None,
        "closed": ConversationClosing.objects.filter(closed_at__gte=since).count(),
        "csat": round(agg["a"], 1) if agg["a"] else None, "ratings": agg["n"], "low": agg["low"],
        "review_open": ConversationRating.objects.filter(review_status="open").count(),
    }
    low = [{"conversation_id": str(r.conversation_id), "score": r.score, "comment": r.comment, "operator": names.get(r.operator_id, "—") if r.operator_id else "—",
            "at": timezone.localtime(r.created_at, TZ).strftime("%d.%m.%Y %H:%M"), "status": r.review_status, "reviewed_by": r.reviewed_by, "note": r.review_note}
           for r in ratings.filter(score__lte=2).order_by("-created_at")[:10]]
    return {"days": days, "since": timezone.localtime(since, TZ).strftime("%d.%m.%Y"), "rows": rows, "totals": totals, "low": low, "sla_minutes": SLA_MINUTES}
