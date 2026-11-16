"""
Payment analytics for Dashboard → To'lovlar -- read-only, computed from PaymentModel / PaymentCallbackLog.

  readiness(state, row, base)   go-live checklist + score for one acquirer (the "5-minute setup" card)
  credential_checks(state)      format validation of what was pasted from the merchant cabinet
  analytics(days, provider)     per-provider conversion, volume, time-to-pay, failure reasons, daily series, funnel, hours
  callback_stats(days)          per provider/method latency (avg / p95) and error rate, top error codes explained
  explain(provider, code)       what a protocol error code means and what to do about it
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.payment.infrastructure.models import PaymentCallbackLog, PaymentModel, PaymentProviderConfig, PaymentStatusChoices
from apps.payment.infrastructure.providers import registry

ZERO = Decimal(0)
S = PaymentStatusChoices

# ---------------------------------------------------------------- error codes

ERROR_HELP: dict[str, dict[int, tuple[str, str]]] = {
    "payme": {
        -32504: ("Avtorizatsiya xatosi", "Kassa kaliti dashboard'dagi bilan mos emas yoki test/production rejimi aralashgan."),
        -32300: ("POST emas", "So'rov POST usulida kelmagan."),
        -32700: ("JSON xato", "So'rov tanasini o'qib bo'lmadi."),
        -32600: ("Noto'g'ri so'rov", "JSON-RPC tuzilmasi buzilgan."),
        -32601: ("Metod topilmadi", "Payme yangi metod yubordi — jurnalni tekshiring."),
        -32602: ("Parametr xato", "Majburiy parametr yo'q."),
        -32400: ("Ichki xato", "Server xatosi — loglarni tekshiring."),
        -31001: ("Summa noto'g'ri", "To'lov summasi buyurtma summasiga teng emas (tiyinda)."),
        -31003: ("Tranzaksiya topilmadi", "Payme bizda yo'q tranzaksiyani so'radi."),
        -31007: ("Bekor qilib bo'lmaydi", "Buyurtma jo'natilgan — pul qaytarilmaydi."),
        -31008: ("Bajarib bo'lmaydi", "Tranzaksiya muddati o'tgan (12 soat) yoki bekor qilingan."),
        -31050: ("Buyurtma topilmadi", "Hisob maydoni (account) kaliti yoki buyurtma raqami noto'g'ri. Self-test shu kodni kutadi."),
        -31051: ("Buyurtma to'langan", "Buyurtma allaqachon to'langan."),
        -31052: ("Buyurtma band", "Bu buyurtma uchun boshqa tranzaksiya ochiq."),
        -32001: ("Chek topilmadi", "SetFiscalData: tranzaksiya yo'q."),
    },
    "click": {
        -1: ("Imzo xato", "SECRET_KEY kabinetdagi bilan mos emas."),
        -2: ("Summa noto'g'ri", "Summa buyurtma summasiga teng emas."),
        -3: ("Amal topilmadi", "action 0 yoki 1 bo'lishi kerak."),
        -4: ("Allaqachon to'langan", "Buyurtma oldin to'langan."),
        -5: ("Buyurtma topilmadi", "merchant_trans_id bo'yicha buyurtma yo'q. Self-test shu kodni kutadi."),
        -6: ("Tranzaksiya topilmadi", "Complete'dagi merchant_prepare_id bizda yo'q."),
        -7: ("Yangilash xatosi", "Bazaga yozib bo'lmadi — qayta urinish."),
        -8: ("So'rov xato", "Majburiy parametr yo'q yoki service_id noto'g'ri."),
        -9: ("Bekor qilingan", "To'lov Click'da muvaffaqiyatsiz bo'ldi yoki buyurtma bekor qilingan."),
    },
    "uzum": {
        10001: ("Ruxsat yo'q", "Basic Auth login/parol mos emas."),
        10002: ("JSON xato", "So'rov tanasini o'qib bo'lmadi."),
        10003: ("Noto'g'ri amal", "Noma'lum endpoint yoki usul."),
        10005: ("Parametr yo'q", "serviceId, timestamp yoki transId yo'q."),
        10006: ("serviceId xato", "Dashboard'dagi Service ID boshqa."),
        10007: ("Buyurtma topilmadi", "params ichidagi buyurtma raqami yo'q. Self-test shu kodni kutadi."),
        10008: ("To'langan", "Buyurtma allaqachon to'langan."),
        10009: ("To'lab bo'lmaydi", "Buyurtma bekor qilingan yoki boshqa tranzaksiya ochiq."),
        10010: ("Takroriy create", "Shu transId bilan tranzaksiya bor."),
        10011: ("Summa noto'g'ri", "Summa buyurtma summasiga teng emas (tiyin)."),
        10012: ("Minimaldan kam", "Dashboard minimal limiti."),
        10013: ("Maksimaldan ko'p", "Dashboard maksimal limiti."),
        10014: ("Tranzaksiya topilmadi", "Bizda bunday transId yo'q."),
        10015: ("Bekor qilingan", "30 daqiqada tasdiqlanmagan yoki bekor qilingan."),
        10016: ("Takroriy confirm", "Allaqachon tasdiqlangan."),
        10017: ("Bekor qilib bo'lmaydi", "Buyurtma jo'natilgan."),
        10018: ("Takroriy reverse", "Allaqachon bekor qilingan."),
    },
}
SELFTEST_CODES = {"payme": -31050, "click": -5, "uzum": 10007}


def explain(provider: str, code) -> tuple[str, str]:
    if code in (None, 0):
        return ("OK", "")
    try:
        return ERROR_HELP.get(provider, {}).get(int(code), (f"Kod {code}", ""))
    except (TypeError, ValueError):
        return (f"Kod {code}", "")


# ---------------------------------------------------------------- setup

_HEX24 = re.compile(r"^[0-9a-f]{24}$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")


def credential_checks(state: registry.ProviderState) -> list[dict]:
    """[{level: bad|warn, field, text}] -- format mistakes that would break callbacks, found before the first payment."""
    out: list[dict] = []

    def add(level, field, text):
        out.append({"level": level, "field": field, "text": text})

    v = state.value
    if state.key == "payme":
        mid = v("merchant_id")
        if mid and not _HEX24.match(mid):
            add("bad", "merchant_id", "Kassa ID 24 belgili hex bo'lishi kerak (masalan 5e730e8e0b852a417aa49ceb).")
        if v("account_field") and not _IDENT.match(v("account_field")):
            add("bad", "account_field", "Hisob maydoni lotin harf/raqam/pastki chiziqdan iborat bo'lishi kerak.")
        for k in ("key", "test_key"):
            if v(k) and len(v(k)) < 20:
                add("warn", k, "Kalit juda qisqa — kabinetdan to'liq nusxalanganini tekshiring.")
            if v(k) and v(k) != v(k).strip():
                add("bad", k, "Kalit boshida/oxirida bo'sh joy bor.")
        if v("key") and v("key") == v("test_key"):
            add("warn", "test_key", "Test kaliti production kaliti bilan bir xil.")
        if state.test_mode and not v("test_key"):
            add("bad", "test_key", "Test rejimi yoqilgan, lekin test kaliti yo'q.")
    elif state.key == "click":
        for k in ("service_id", "merchant_id", "merchant_user_id"):
            if v(k) and not v(k).isdigit():
                add("bad", k, "Faqat raqam bo'lishi kerak.")
        if v("secret_key") and len(v("secret_key")) < 6:
            add("warn", "secret_key", "Secret key juda qisqa.")
        if not v("merchant_user_id"):
            add("warn", "merchant_user_id", "Merchant User ID bo'lmasa, Click bilan avtomatik solishtirish ishlamaydi.")
    elif state.key == "uzum":
        if v("service_id") and not v("service_id").isdigit():
            add("bad", "service_id", "Service ID faqat raqam.")
        if v("login") and " " in v("login"):
            add("bad", "login", "Loginda bo'sh joy bo'lmasligi kerak.")
        if v("password") and len(v("password")) < 6:
            add("warn", "password", "Parol juda qisqa.")
        if v("param_key") and not _IDENT.match(v("param_key")):
            add("bad", "param_key", "Parametr kaliti lotin harf/raqamdan iborat bo'lishi kerak.")
        url = state.public.get("checkout_url") or ""
        if url and not url.startswith("https://"):
            add("bad", "checkout_url", "To'lov havolasi https:// bilan boshlanishi kerak.")
        if not url:
            add("warn", "checkout_url", "To'lov havolasi shabloni yo'q — mijoz Uzum ilovasida servisni o'zi topadi.")
    return out


def selftest_result(row: PaymentProviderConfig | None) -> dict | None:
    return ((row.settings_public or {}).get("_selftest") if row else None) or None


def save_selftest(row: PaymentProviderConfig, ok: bool, code) -> None:
    """Stored next to the public settings without touching updated_at, so 'tested after the last change' stays meaningful."""
    public = dict(row.settings_public or {})
    public["_selftest"] = {"ok": bool(ok), "code": code, "at": timezone.now().isoformat()}
    PaymentProviderConfig.objects.filter(pk=row.pk).update(settings_public=public)
    row.settings_public = public


def readiness(state: registry.ProviderState, row: PaymentProviderConfig | None, base_url: str) -> dict:
    """Go-live checklist for Payme / Click / Uzum: what's done, what's next, and a 0-100 score."""
    checks = credential_checks(state)
    test = selftest_result(row)
    tested_ok = bool(test and test.get("ok"))
    tested_fresh = tested_ok and row is not None and (row.updated_at is None or test.get("at", "") >= row.updated_at.isoformat())
    real_paid = PaymentModel.objects.filter(provider=state.key, status=S.SUCCEEDED, is_test=False).exists()
    any_paid = real_paid or PaymentModel.objects.filter(provider=state.key, status=S.SUCCEEDED).exists()
    items = [
        ("keys", "Kalitlar kiritilgan", not state.missing, "Merchant kabinetidan ID va kalitlarni nusxalab, saqlang."),
        ("format", "Kalitlar formati to'g'ri", not [c for c in checks if c["level"] == "bad"], "Qizil belgilangan maydonlarni tuzating."),
        ("https", "Sayt HTTPS orqali ochiladi", base_url.startswith("https://"), "Provayderlar faqat HTTPS callback'larni qabul qiladi."),
        ("selftest", "Self-test o'tgan", tested_fresh, "«Ulanishni tekshirish» tugmasini bosing (kalit o'zgargandan keyin qayta)."),
        ("callbacks", "Kabinetga callback URL yozilgan", bool(row and row.last_callback_at), "Callback manzillarini kabinetga qo'ying — provayderning birinchi so'rovi kelganda belgilanadi."),
        ("enabled", "Usul yoqilgan", state.enabled, "«Yoqilgan» ni belgilang — checkout'da paydo bo'ladi."),
    ]
    if state.spec.supports_test:
        items.append(("live", "Production rejimi", not state.test_mode, "Test to'lovlar o'tgach test rejimini o'chiring."))
    items.append(("paid", "Birinchi muvaffaqiyatli to'lov", real_paid if not state.test_mode else any_paid, "Kichik summali buyurtmani o'zingiz to'lab ko'ring."))
    done = sum(1 for i in items if i[2])
    nxt = next((i for i in items if not i[2]), None)
    return {
        "items": [{"key": k, "label": label, "ok": ok, "hint": hint} for k, label, ok, hint in items],
        "done": done, "total": len(items), "score": round(done * 100 / len(items)),
        "next": {"label": nxt[1], "hint": nxt[3]} if nxt else None, "checks": checks, "test": test, "tested_fresh": tested_fresh,
        "deg": f"{done * 360 / len(items):.1f}",
    }


# ---------------------------------------------------------------- transactions


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    v = sorted(values)
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def _pctl(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def _rate(a: int, b: int) -> float | None:
    return round(a * 100 / b, 1) if b else None


def _mins(v: float | None) -> str:
    if v is None:
        return "—"
    if v < 1:
        return f"{int(v * 60)} s"
    if v < 90:
        return f"{v:.0f} daq"
    return f"{v / 60:.1f} soat"


def analytics(days: int = 30, provider: str = "", now=None) -> dict:
    now = now or timezone.now()
    since = now - timedelta(days=days)
    prev_since = since - timedelta(days=days)
    base = PaymentModel.objects.exclude(provider="cash")
    if provider:
        base = base.filter(provider=provider)
    qs = base.filter(created_at__gte=since)
    rows = list(qs.values("provider", "method", "status", "amount", "created_at", "paid_at", "failure_reason", "provider_reference"))

    per: dict[str, dict] = {}
    for key in registry.ACQUIRERS:
        if not provider or provider == key:
            per[key] = {"key": key, "name": registry.provider_label(key), "attempts": 0, "started": 0, "paid": 0, "volume": ZERO, "refunded": ZERO, "ttp": [], "fails": Counter()}
    methods: dict[str, Decimal] = defaultdict(lambda: ZERO)
    hours = [0] * 24
    for r in rows:
        p = per.setdefault(r["provider"], {"key": r["provider"], "name": registry.provider_label(r["provider"]), "attempts": 0, "started": 0, "paid": 0,
                                           "volume": ZERO, "refunded": ZERO, "ttp": [], "fails": Counter()})
        p["attempts"] += 1
        if r["provider_reference"]:
            p["started"] += 1
        if r["status"] == S.SUCCEEDED:
            p["paid"] += 1
            p["volume"] += r["amount"]
            methods[r["method"] or r["provider"]] += r["amount"]
            if r["paid_at"]:
                p["ttp"].append((r["paid_at"] - r["created_at"]).total_seconds() / 60)
                hours[timezone.localtime(r["paid_at"]).hour] += 1
        elif r["status"] == S.REFUNDED:
            p["refunded"] += r["amount"]
        elif r["status"] in (S.FAILED, S.CANCELLED) and r["failure_reason"]:
            p["fails"][_reason(r["failure_reason"])] += 1

    providers = []
    total_paid = sum(p["paid"] for p in per.values())
    total_volume = sum((p["volume"] for p in per.values()), ZERO)
    for p in per.values():
        med = _median(p["ttp"])
        providers.append({
            "key": p["key"], "name": p["name"], "logo_key": p["key"], "attempts": p["attempts"], "started": p["started"], "paid": p["paid"],
            "conversion": _rate(p["paid"], p["attempts"]), "success": _rate(p["paid"], p["started"]), "volume": p["volume"],
            "avg": (p["volume"] / p["paid"]) if p["paid"] else ZERO, "refunded": p["refunded"], "ttp": _mins(med), "ttp_p90": _mins(_pctl(p["ttp"], 0.9)),
            "share": _rate(int(p["volume"]), int(total_volume)) or 0, "fails": p["fails"].most_common(3),
        })
    providers.sort(key=lambda x: -x["volume"])
    for p in providers:
        p["share_w"] = f"{p['share']:.1f}"
        p["success_w"] = f"{(p['success'] or 0):.1f}"

    attempts = len(rows)
    started = sum(1 for r in rows if r["provider_reference"])
    refunded = sum(1 for r in rows if r["status"] == S.REFUNDED)
    funnel = [
        ("Checkout ochildi", attempts), ("Provayderda boshlandi", started), ("To'landi", total_paid), ("Qaytarildi", refunded),
    ]
    top = max(attempts, 1)
    funnel = [{"label": label, "n": n, "pct": _rate(n, attempts) if attempts else 0, "w": f"{n * 100 / top:.1f}"} for label, n in funnel]

    # daily paid volume per provider
    labels, series = [], {p["key"]: [] for p in providers}
    day0 = timezone.localdate(now) - timedelta(days=days - 1)
    by_day: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        if r["status"] == S.SUCCEEDED and r["paid_at"]:
            by_day[(timezone.localdate(r["paid_at"]), r["provider"])] += r["amount"]
    for i in range(days):
        d = day0 + timedelta(days=i)
        labels.append(d.strftime("%d.%m"))
        for key in series:
            series[key].append(float(by_day.get((d, key), ZERO)))

    prev = base.filter(created_at__gte=prev_since, created_at__lt=since)
    prev_paid = prev.filter(status=S.SUCCEEDED).aggregate(n=Count("id"), s=Sum("amount"))
    prev_volume = prev_paid["s"] or ZERO
    fails = Counter()
    for p in per.values():
        fails.update(p["fails"])
    peak = max(range(24), key=lambda h: hours[h]) if any(hours) else None
    hmax = max(hours) or 1
    return {
        "days": days, "providers": providers, "funnel": funnel,
        "totals": {
            "attempts": attempts, "started": started, "paid": total_paid, "volume": total_volume, "conversion": _rate(total_paid, attempts),
            "success": _rate(total_paid, started), "avg": (total_volume / total_paid) if total_paid else ZERO,
            "d_volume": _delta(total_volume, prev_volume), "d_paid": _delta(total_paid, prev_paid["n"] or 0), "prev_volume": prev_volume,
            "ttp": _mins(_median([m for p in per.values() for m in p["ttp"]])),
        },
        "chart": {"labels": labels, "series": [{"key": k, "name": registry.provider_label(k), "color": registry.SPECS[k].color if k in registry.SPECS else "#64748b", "data": v}
                                               for k, v in series.items()]},
        "methods": sorted(((registry.provider_label(k), v, _rate(int(v), int(total_volume)) or 0) for k, v in methods.items()), key=lambda x: -x[1]),
        "fails": fails.most_common(6), "hours": [{"h": h, "n": n, "w": f"{n * 100 / hmax:.0f}"} for h, n in enumerate(hours)], "peak": peak,
    }


def _delta(cur, prev):
    if not prev:
        return None
    return round(float((Decimal(cur) - Decimal(prev)) * 100 / Decimal(prev)), 1)


def _reason(text: str) -> str:
    """Groups free-text failure reasons ('Click: Insufficient funds', 'Payme: timeout (reason 4)') into short buckets."""
    t = (text or "").strip()
    low = t.lower()
    if "30 minutes" in low or "timeout" in low or "muddati" in low or "reason 4" in low:
        return "Vaqt tugadi"
    if "dashboard" in low:
        return "Operator bekor qildi"
    if "auto" in low or "avtomatik" in low:
        return "Avtomatik bekor (to'lanmadi)"
    if "order no longer payable" in low or "buyurtma" in low:
        return "Buyurtma bekor qilingan"
    if "reversed" in low or "reason 5" in low or "refund" in low:
        return "Provayder qaytardi"
    return t[:60] or "Noma'lum"


# ---------------------------------------------------------------- callbacks


def callback_stats(days: int = 7, provider: str = "", now=None) -> dict:
    now = now or timezone.now()
    qs = PaymentCallbackLog.objects.filter(created_at__gte=now - timedelta(days=days))
    if provider:
        qs = qs.filter(provider=provider)
    data = list(qs.values_list("provider", "method", "error_code", "duration_ms", "http_status")[:20000])
    groups: dict[tuple, list] = defaultdict(list)
    codes: Counter = Counter()
    all_ms = []
    errors = 0
    for prov, method, code, ms, http in data:
        groups[(prov, method or "—")].append((code, ms))
        all_ms.append(ms)
        if code not in (None, 0):
            errors += 1
            codes[(prov, code)] += 1
    rows = []
    for (prov, method), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ms = [m for _c, m in items]
        bad = sum(1 for c, _m in items if c not in (None, 0))
        p95 = _pctl(ms, 0.95) or 0
        rows.append({"provider": prov, "name": registry.provider_label(prov), "method": method, "n": len(items), "errors": bad, "err_rate": _rate(bad, len(items)) or 0,
                     "avg": round(sum(ms) / len(ms)) if ms else 0, "p95": int(p95), "slow": p95 > 3000})
    top = []
    for (prov, code), n in codes.most_common(8):
        title, hint = explain(prov, code)
        top.append({"provider": prov, "name": registry.provider_label(prov), "code": code, "n": n, "title": title, "hint": hint,
                    "expected": SELFTEST_CODES.get(prov) == code})
    return {
        "days": days, "rows": rows, "top": top, "total": len(data), "errors": errors, "err_rate": _rate(errors, len(data)) or 0,
        "avg": round(sum(all_ms) / len(all_ms)) if all_ms else 0, "p95": int(_pctl(all_ms, 0.95) or 0),
        "last": {p: PaymentCallbackLog.objects.filter(provider=p).values_list("created_at", flat=True).first() for p in registry.ACQUIRERS},
    }


def provider_quick(key: str, days: int = 30) -> dict:
    """Small numbers for a provider card: success rate and attempts over `days`."""
    since = timezone.now() - timedelta(days=days)
    agg = PaymentModel.objects.filter(provider=key, created_at__gte=since).exclude(provider_reference__isnull=True).aggregate(
        n=Count("id"), ok=Count("id", filter=Q(status=S.SUCCEEDED)))
    return {"started": agg["n"] or 0, "success": _rate(agg["ok"] or 0, agg["n"] or 0)}
