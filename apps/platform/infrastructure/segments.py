"""
Customer segments (RFM: how recently, how often, how much) from every purchase a customer made -- store tills
(receipts with a customer attached) and delivered / completed online orders -- with the same revenue definition as
business_analytics (net of returns).

    vip        top 10% by spend (min. 2 purchases), bought in the last 90 days
    loyal      3+ purchases, last one within 45 days
    new        first purchase within the last 30 days
    active     bought within 30 days (and none of the above)
    at_risk    last purchase 30-60 days ago
    lost       last purchase more than 60 days ago
    no_purchase  registered, never bought

A customer is in exactly one segment (first match in that order). Computed on demand and cached for 10 minutes;
used by the Dashboard "Mijozlar segmentlari" page and as a broadcast audience ("segment:<code>").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

ZERO = Decimal(0)
CACHE_KEY = "segments:v1"
CACHE_SECONDS = 600
SEGMENTS = {
    "vip": {"label": "VIP mijozlar", "icon": "fa-crown", "tone": "#f59e0b", "hint": "Eng ko'p xarid qilgan 10% (oxirgi 90 kunda faol)", "action": "Shaxsiy taklif, yangi mahsulotlarni birinchi bo'lib ko'rsatish"},
    "loyal": {"label": "Doimiy xaridorlar", "icon": "fa-heart", "tone": "#ec4899", "hint": "3+ xarid, oxirgisi 45 kun ichida", "action": "Bonus coins, \"birga olinadi\" takliflari"},
    "new": {"label": "Yangi xaridorlar", "icon": "fa-seedling", "tone": "#22c55e", "hint": "Birinchi xarid 30 kun ichida", "action": "Qo'llanma, ikkinchi xaridga chegirma"},
    "active": {"label": "Faol", "icon": "fa-bolt", "tone": "#0ea5e9", "hint": "30 kun ichida xarid qilgan", "action": "Tugash vaqtida eslatma"},
    "at_risk": {"label": "Ketish xavfi", "icon": "fa-triangle-exclamation", "tone": "#f97316", "hint": "Oxirgi xarid 30–60 kun oldin", "action": "\"Sizni sog'indik\" xabari va chegirma kuponi"},
    "lost": {"label": "Yo'qotilgan", "icon": "fa-user-clock", "tone": "#ef4444", "hint": "60 kundan beri xarid yo'q", "action": "Qaytarish kampaniyasi (kuchli taklif)"},
    "no_purchase": {"label": "Xarid qilmagan", "icon": "fa-user", "tone": "#64748b", "hint": "Ro'yxatdan o'tgan, hali xarid yo'q", "action": "Birinchi xarid uchun kupon"},
}
ORDER = tuple(SEGMENTS)
VIP_MIN_POOL = 10


@dataclass
class Profile:
    customer_id: object
    purchases: int = 0
    revenue: Decimal = ZERO
    first: object = None
    last: object = None
    channels: set = field(default_factory=set)

    def add(self, at, amount, channel: str) -> None:
        self.purchases += 1
        self.revenue += amount or ZERO
        self.first = at if self.first is None or at < self.first else self.first
        self.last = at if self.last is None or at > self.last else self.last
        self.channels.add(channel)


def _profiles() -> dict:
    from apps.platform.infrastructure.business_analytics import EARNED, _online_orders
    from apps.pos.infrastructure import sales_reports as rep

    epoch = timezone.now() - timedelta(days=365 * 5)
    out: dict = {}
    for r in rep.rows(rep.closed_sales().filter(completed_at__gte=epoch, customer_id__isnull=False)):
        if r["status"] in ("completed", "refunded") and r["customer_id"]:
            out.setdefault(r["customer_id"], Profile(r["customer_id"])).add(r["when"], r["revenue"], "store")
    for o in _online_orders(epoch, timezone.now() + timedelta(minutes=1)):
        if o["status"] in EARNED and o["customer_id"]:
            out.setdefault(o["customer_id"], Profile(o["customer_id"])).add(o["at"], o["amount"] or ZERO, "online")
    return out


def classify(profiles: dict, now=None) -> dict:
    """{customer_id: segment code} for the customers who bought anything."""
    now = now or timezone.now()
    spenders = sorted((p.revenue for p in profiles.values() if p.purchases >= 2), reverse=True)
    # "top 10%" only means something with enough repeat buyers -- below 10 nobody is VIP yet
    vip_floor = spenders[len(spenders) // 10 - 1] if len(spenders) >= VIP_MIN_POOL else None
    out = {}
    for cid, p in profiles.items():
        days = (now - p.last).days
        if vip_floor is not None and p.purchases >= 2 and p.revenue >= vip_floor and days <= 90:
            seg = "vip"
        elif p.purchases >= 3 and days <= 45:
            seg = "loyal"
        elif (now - p.first).days <= 30:
            seg = "new"
        elif days <= 30:
            seg = "active"
        elif days <= 60:
            seg = "at_risk"
        else:
            seg = "lost"
        out[cid] = seg
    return out


def snapshot(force: bool = False) -> dict:
    """{"segments": {code: {count, revenue, avg_check, avg_days}}, "members": {code: [customer ids]}, "total_customers"} (cached)."""
    if not force:
        hit = cache.get(CACHE_KEY)
        if hit is not None:
            return hit
    from apps.identity.infrastructure.models import User

    profiles = _profiles()
    seg_of = classify(profiles)
    now = timezone.now()
    members: dict = {code: [] for code in ORDER}
    for cid, seg in seg_of.items():
        members[seg].append(cid)
    buyers = set(seg_of)
    customers = User.objects.exclude(status="blocked")
    members["no_purchase"] = [cid for cid in customers.values_list("id", flat=True) if cid not in buyers]
    stats = {}
    for code in ORDER:
        ids = members.get(code, [])
        ps = [profiles[c] for c in ids if c in profiles]
        revenue = sum((p.revenue for p in ps), ZERO)
        purchases = sum(p.purchases for p in ps)
        stats[code] = {
            **SEGMENTS[code], "code": code, "count": len(ids), "revenue": revenue,
            "avg_check": (revenue / purchases).quantize(Decimal("1")) if purchases else None,
            "avg_days": round(sum((now - p.last).days for p in ps) / len(ps)) if ps else None,
        }
    total_revenue = sum((s["revenue"] for s in stats.values()), ZERO)
    for s in stats.values():
        s["share"] = round(float(s["revenue"] / total_revenue * 100), 1) if total_revenue else 0
    data = {"segments": stats, "members": {k: [str(c) for c in v] for k, v in members.items()},
            "profiles": {str(c): {"purchases": p.purchases, "revenue": str(p.revenue), "last": p.last.isoformat(), "channels": sorted(p.channels)} for c, p in profiles.items()},
            "total_customers": customers.count(), "generated_at": now.isoformat()}
    cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return data


def members(code: str) -> list[str]:
    return snapshot()["members"].get(code, []) if code in SEGMENTS else []
