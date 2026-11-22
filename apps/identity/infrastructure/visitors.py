"""
Visitor devices: who opens the storefront from what (OS, mobile / computer / tablet, browser, in-app, phone brand).

Fed by the storefront beacon (`POST /api/v1/identity/visits`, once per browser tab session) and, for the days before the
beacon existed, by `manage.py import_visit_log` over the web-server access log. Bots are classified and kept out of every
number. Nothing personal is stored: the key is a sha256 of a random per-browser id (or of IP + User-Agent for log rows).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count, F, Sum
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.identity.infrastructure.models import VisitorDay, VisitorDevice

# ---------------------------------------------------------------- User-Agent → device

_BOT = re.compile(
    r"bot\b|bot/|compatible;|crawl|spider|slurp|lighthouse|headless|pagespeed|chrome-lighthouse|google-|facebookexternalhit|facebookcatalog|"
    r"curl|wget|python|^node|okhttp|go-http|axios|java/|httpclient|libwww|monitor|uptime|scanner|zgrab|masscan|nmap|"
    r"whatsapp|vkshare|skypeuripreview|bytespider|gptbot|claude|anthropic|perplexity|semrush|ahrefs|mj12|dataprovider|"
    r"petalbot|applebot|bingpreview|telegrambot|discordbot|twitterbot|linkedin|embedly|qwantify|seznam|censys|netcraft",
    re.I,
)
OS_ORDER = ("Android", "iOS", "Windows", "macOS", "Linux", "ChromeOS", "HarmonyOS", "Boshqa")
CLASS_ORDER = ("mobile", "desktop", "tablet")
CLASS_LABEL = {"mobile": "Telefon", "desktop": "Kompyuter", "tablet": "Planshet"}
CLASS_ICON = {"mobile": "fa-mobile-screen-button", "desktop": "fa-desktop", "tablet": "fa-tablet-screen-button"}
OS_ICON = {"Android": "fab fa-android", "iOS": "fab fa-apple", "Windows": "fab fa-windows", "macOS": "fab fa-apple", "Linux": "fab fa-linux",
           "ChromeOS": "fab fa-chrome", "HarmonyOS": "fas fa-mobile", "Boshqa": "fas fa-circle-question"}
IN_APP_LABEL = {"telegram": "Telegram", "instagram": "Instagram", "facebook": "Facebook", "": "Oddiy brauzer"}
IN_APP_ICON = {"telegram": "fab fa-telegram", "instagram": "fab fa-instagram", "facebook": "fab fa-facebook", "": "fas fa-globe"}
_BRANDS = (
    (re.compile(r"^SM-|SAMSUNG|Galaxy", re.I), "Samsung"),
    (re.compile(r"Redmi|POCO|Xiaomi|^Mi |^MI |^M\d{4}[A-Z]|^2[0-9]{3}[A-Z0-9]{4,}|^\d{5}[A-Z0-9]{3,}", re.I), "Xiaomi"),
    (re.compile(r"Pixel", re.I), "Google"),
    (re.compile(r"^RMX|realme", re.I), "Realme"),
    (re.compile(r"^CPH|OPPO", re.I), "OPPO"),
    (re.compile(r"vivo|^V2\d{3}", re.I), "vivo"),
    (re.compile(r"TECNO", re.I), "Tecno"),
    (re.compile(r"Infinix", re.I), "Infinix"),
    (re.compile(r"HONOR", re.I), "Honor"),
    (re.compile(r"HUAWEI|^[A-Z]{3}-[A-Z]{1,2}\d{2}", re.I), "Huawei"),
    (re.compile(r"OnePlus", re.I), "OnePlus"),
    (re.compile(r"moto|Motorola", re.I), "Motorola"),
    (re.compile(r"Nokia", re.I), "Nokia"),
    (re.compile(r"itel", re.I), "itel"),
    (re.compile(r"Lenovo", re.I), "Lenovo"),
    (re.compile(r"ZTE|Blade", re.I), "ZTE"),
    (re.compile(r"Nothing|^A0\d{2}$", re.I), "Nothing"),
)


def is_bot(ua: str) -> bool:
    return not ua or bool(_BOT.search(ua))


def _brand(model: str) -> str:
    return next((name for rx, name in _BRANDS if rx.search(model)), "") if model else ""


def classify(ua: str, hints: dict | None = None) -> dict:  # noqa: C901 -- one flat decision table, easier to read than split helpers
    """Device fields from a User-Agent plus optional browser hints (Client Hints model / platformVersion, touch, Mini App)."""
    ua, h = (ua or "")[:512], hints or {}
    os_name, os_ver = "Boshqa", ""
    if "HarmonyOS" in ua:
        os_name = "HarmonyOS"
    elif "Android" in ua:
        os_name = "Android"
        m = re.search(r"Android (\d+)", ua)
        os_ver = m.group(1) if m else ""
    elif re.search(r"iPhone|iPad|iPod", ua):
        os_name = "iOS"
        m = re.search(r"OS (\d+)[_.](\d+)", ua)
        os_ver = f"{m.group(1)}.{m.group(2)}" if m else ""
    elif "CrOS" in ua:
        os_name = "ChromeOS"
    elif "Windows" in ua:
        os_name = "Windows"
        m = re.search(r"Windows NT (\d+\.\d+)", ua)
        os_ver = {"10.0": "10/11", "6.3": "8.1", "6.2": "8", "6.1": "7"}.get(m.group(1), m.group(1)) if m else ""
    elif "Macintosh" in ua or "Mac OS X" in ua:
        os_name = "macOS"
    elif "Linux" in ua or "X11" in ua:
        os_name = "Linux"

    pv = str(h.get("pv") or "")  # Client Hints platformVersion -- the real one (Chrome's UA freezes Android at 10, Windows at NT 10.0)
    if pv and re.match(r"^\d+", pv):
        major = int(re.match(r"^(\d+)", pv).group(1))
        if os_name == "Windows":
            os_ver = "11" if major >= 13 else "10"
        elif os_name == "Android" and major:
            os_ver = str(major)

    if re.search(r"iPad|Tablet", ua) or (os_name == "Android" and "Mobile" not in ua):
        cls = "tablet"
    elif re.search(r"iPhone|iPod|Mobile|Android", ua):
        cls = "mobile"
    else:
        cls = "desktop"
    if os_name == "macOS" and str(h.get("tp") or "0").isdigit() and int(h.get("tp") or 0) > 1:  # iPadOS asks for the desktop site but has a touch screen
        os_name, cls = "iOS", "tablet"
    if str(h.get("m")).lower() in ("1", "true") and cls == "desktop":
        cls = "mobile"

    in_app = ""
    if str(h.get("tg") or "").lower() in ("1", "true") or "Telegram" in ua:
        in_app = "telegram"
    elif "Instagram" in ua:
        in_app = "instagram"
    elif re.search(r"FBAN|FBAV|FB_IAB", ua):
        in_app = "facebook"

    if in_app:
        browser = IN_APP_LABEL[in_app]
    elif "YaBrowser" in ua or "YaSearchBrowser" in ua:
        browser = "Yandex"
    elif "SamsungBrowser" in ua:
        browser = "Samsung Internet"
    elif "OPR/" in ua or "Opera" in ua or "OPX/" in ua:
        browser = "Opera"
    elif "Edg" in ua:
        browser = "Edge"
    elif "Firefox" in ua or "FxiOS" in ua:
        browser = "Firefox"
    elif "MiuiBrowser" in ua or "XiaoMi" in ua:
        browser = "Mi Browser"
    elif "CriOS" in ua or "Chrome/" in ua:
        browser = "Chrome"
    elif "Safari" in ua:
        browser = "Safari"
    elif os_name == "iOS":
        browser = "iOS ilova ichida"  # WKWebView of some app (no Safari token)
    else:
        browser = "Boshqa"

    model = str(h.get("md") or "").strip()[:64]
    if not model and os_name == "Android":
        m = re.search(r"Android [\d.]+; (?:[a-z]{2}[-_][a-zA-Z]{2}; )?([^;)]+?)(?: Build|\))", ua)
        model = m.group(1).strip() if m and m.group(1).strip() not in ("K", "wv") else ""
    brand = "Apple" if os_name in ("iOS", "macOS") else _brand(model)
    if os_name == "iOS":
        model = "iPad" if cls == "tablet" else "iPhone"

    screen = ""
    if h.get("w") and h.get("h"):
        try:
            screen = f"{int(h['w'])}x{int(h['h'])}"[:16]
        except (TypeError, ValueError):
            screen = ""
    return {"device_class": cls, "os": os_name, "os_version": os_ver[:24], "browser": browser, "in_app": in_app, "brand": brand,
            "model": model, "screen": screen, "user_agent": ua, "is_bot": is_bot(ua)}


def visitor_key(raw: str) -> str:
    return hashlib.sha256(f"nz-visitor:{raw}".encode()).hexdigest()


# ---------------------------------------------------------------- recording


def record_visit(raw_id: str, ua: str, hints: dict | None = None, when: datetime | None = None, source: str = "beacon") -> VisitorDevice:
    """Upsert the device and today's row; a returning browser keeps its first_seen and gains a day / a hit."""
    when = when or timezone.now()
    info, day = classify(ua, hints), timezone.localdate(when)
    with transaction.atomic():
        dev, created = VisitorDevice.objects.select_for_update().get_or_create(
            key=visitor_key(raw_id), defaults={**info, "source": source, "first_seen": when, "last_seen": when, "days": 1, "hits": 1})
        _vd, new_day = VisitorDay.objects.get_or_create(device=dev, day=day, defaults={"hits": 1})
        if created:
            return dev
        if not new_day:
            VisitorDay.objects.filter(device=dev, day=day).update(hits=F("hits") + 1)
        # keep what the browser told us before when this hit is less specific (no hints -> no model / screen)
        keep = {k: v for k, v in info.items() if v or k in ("in_app", "is_bot")}
        if not hints:
            keep.pop("in_app", None)
        VisitorDevice.objects.filter(pk=dev.pk).update(**keep, last_seen=max(when, dev.last_seen), hits=F("hits") + 1, days=F("days") + (1 if new_day else 0))
    return dev


# ---------------------------------------------------------------- statistics

PERIODS = (("1", "Bugun", 1), ("7", "7 kun", 7), ("30", "30 kun", 30), ("90", "90 kun", 90), ("all", "Hammasi", None))


def period_of(request) -> tuple[str, str, int | None]:
    p = (getattr(request, "nz_period", None) or request.GET.get("period") or "30") if request is not None else "30"
    return next((x for x in PERIODS if x[0] == p), PERIODS[2])


def _since(days: int | None):
    if not days:
        return None
    return timezone.localdate() - timedelta(days=days - 1)


def visitors_qs(days: int | None):
    qs = VisitorDevice.objects.filter(is_bot=False)
    start = _since(days)
    if start:
        qs = qs.filter(last_seen__gte=timezone.make_aware(datetime.combine(start, datetime.min.time())))
    return qs


def _share(rows: list[tuple[str, int]], total: int) -> list[dict]:
    return [{"key": k, "n": n, "pct": round(n * 100 / total, 1) if total else 0, "w": round(n * 100 / rows[0][1], 1) if rows and rows[0][1] else 0} for k, n in rows]


def stats(days: int | None) -> dict:
    qs, start = visitors_qs(days), _since(days)
    total = qs.count()

    def group(field, order=None, exclude_blank=False, limit=None):
        q = qs.exclude(**{field: ""}) if exclude_blank else qs
        counts = dict(q.values_list(field).annotate(n=Count("id")).values_list(field, "n"))
        rows = [(k, counts.get(k, 0)) for k in order] if order else sorted(counts.items(), key=lambda kv: -kv[1])
        rows = [r for r in rows if r[1]]
        if order:
            rows.sort(key=lambda kv: -kv[1])
        return rows[:limit] if limit else rows

    classes = dict(group("device_class"))
    phones = classes.get("mobile", 0) + classes.get("tablet", 0)
    days_qs = VisitorDay.objects.filter(device__is_bot=False)
    if start:
        days_qs = days_qs.filter(day__gte=start)
    agg = days_qs.aggregate(visits=Sum("hits"), device_days=Count("id"))
    new = qs.filter(first_seen__gte=timezone.make_aware(datetime.combine(start, datetime.min.time()))).count() if start else total

    versions = []
    for os_name in ("Android", "iOS", "Windows"):
        for ver, n in qs.filter(os=os_name).exclude(os_version="").values_list("os_version").annotate(n=Count("id")).values_list("os_version", "n").order_by("-n")[:4]:
            versions.append((f"{os_name} {ver}", n))
    versions.sort(key=lambda kv: -kv[1])

    trend_days = 14 if (days or 0) <= 7 and days else min(days or 60, 60)
    t0 = timezone.localdate() - timedelta(days=trend_days - 1)
    per_day: dict = {}
    for day, cls, n in (VisitorDay.objects.filter(device__is_bot=False, day__gte=t0).values_list("day", "device__device_class")
                        .annotate(n=Count("id")).values_list("day", "device__device_class", "n")):
        per_day.setdefault(day, {})[cls] = n
    trend = []
    for i in range(trend_days):
        d = t0 + timedelta(days=i)
        row = per_day.get(d, {})
        trend.append({"day": d, **{c: row.get(c, 0) for c in CLASS_ORDER}, "total": sum(row.values())})

    first = VisitorDay.objects.order_by("day").values_list("day", flat=True).first()
    return {
        "total": total, "new": new, "returning": max(total - new, 0),
        "visits": agg["visits"] or 0, "device_days": agg["device_days"] or 0,
        "classes": _share([(c, classes.get(c, 0)) for c in CLASS_ORDER], total),
        "os": _share(group("os", OS_ORDER), total),
        "browsers": _share(group("browser", limit=8), total),
        "in_app": _share(group("in_app"), total),
        "brands": _share(sorted(((b or "Aniqlanmagan", n) for b, n in qs.filter(device_class__in=("mobile", "tablet")).values_list("brand")
                                 .annotate(n=Count("id")).values_list("brand", "n")), key=lambda kv: (kv[0] == "Aniqlanmagan", -kv[1]))[:10],
                         phones),
        "versions": _share(versions[:10], total),
        "trend": trend, "since": first,
        "bots": VisitorDevice.objects.filter(is_bot=True).count(),
    }


# ---------------------------------------------------------------- panel HTML (Dashboard > Qurilmalar)


def _bars(rows: list[dict], label_of, icon_of, note: str = "") -> str:
    if not rows:
        return mark_safe('<p class="nzv-empty">Ma\'lumot yo\'q</p>')
    items = format_html_join("", '<li title="{} — {} ta qurilma ({}%)"><span class="nzv-bl"><i class="{}" aria-hidden="true"></i> {}</span>'
                                 '<span class="nzv-track"><i style="width:{}%"></i></span><b>{}%</b><small>{}</small></li>',
                             ((label_of(r["key"]), r["n"], r["pct"], icon_of(r["key"]), label_of(r["key"]), max(r["w"], 1.5), r["pct"], f"{r['n']:,}".replace(",", " "))
                              for r in rows))
    return format_html('<ul class="nzv-bars">{}</ul>{}', items, format_html('<p class="nzv-note">{}</p>', note) if note else "")


def _donut(classes: list[dict], total: int) -> str:
    stops, acc = [], 0.0
    for r in classes:
        if r["n"]:
            stops.append(f"var(--nzv-{r['key']}) {acc:.2f}% {acc + r['pct']:.2f}%")
            acc += r["pct"]
    grad = ", ".join(stops) or "var(--nz-border) 0 100%"
    legend = format_html_join("", '<li><span class="nzv-sw" style="background:var(--nzv-{})"></span><i class="fas {}" aria-hidden="true"></i>'
                                  '<span>{}</span><b>{}%</b><small>{} ta</small></li>',
                              ((r["key"], CLASS_ICON[r["key"]], CLASS_LABEL[r["key"]], r["pct"], f"{r['n']:,}".replace(",", " ")) for r in classes))
    mob = next((r["pct"] for r in classes if r["key"] == "mobile"), 0)
    return format_html('<div class="nzv-split"><div class="nzv-donut" style="background:conic-gradient({})" role="img" aria-label="Telefon {}%">'
                       '<span><b>{}%</b><small>telefondan</small></span></div><ul class="nzv-legend">{}</ul></div>',
                       mark_safe(grad), mob, mob, legend)


def _trend(trend: list[dict]) -> str:
    peak = max((t["total"] for t in trend), default=0) or 1
    cols = []
    for t in trend:
        segs = format_html_join("", '<i class="nzv-seg" style="height:{}%;background:var(--nzv-{})"></i>',
                                ((round(t[c] * 100 / peak, 2), c) for c in reversed(CLASS_ORDER) if t[c]))
        tip = f"{t['day']:%d.%m}: {t['total']} qurilma — telefon {t['mobile']}, kompyuter {t['desktop']}, planshet {t['tablet']}"
        cols.append(format_html('<div class="nzv-col" title="{}" tabindex="0"><div class="nzv-stack">{}</div><small>{}</small></div>', tip, segs,
                                f"{t['day']:%d}" if len(trend) <= 31 or t["day"].day in (1, 10, 20) else ""))
    legend = format_html_join("", '<span><i style="background:var(--nzv-{})"></i>{}</span>', ((c, CLASS_LABEL[c]) for c in CLASS_ORDER))
    return format_html('<div class="nzv-trend-head"><span>Kunlik noyob qurilmalar · eng ko\'p: <b>{}</b></span><span class="nzv-tl">{}</span></div>'
                       '<div class="nzv-trend">{}</div>', peak, legend, mark_safe("".join(cols)))


def panel_html(request, list_url: str = "") -> str:
    key, label, days = period_of(request)
    s = stats(days)
    q = request.GET.copy() if request is not None else {}
    tabs = []
    for k, lab, _d in PERIODS:
        qq = q.copy() if q else None
        if qq is not None:
            qq.pop("p", None)
            qq["period"] = k
        tabs.append(format_html('<a href="?{}" class="nzv-tab{}">{}</a>', qq.urlencode() if qq is not None else f"period={k}", " is-on" if k == key else "", lab))
    total = s["total"]
    if not total and not s["since"]:
        return mark_safe('<section class="nzp-card nzv"><header class="nzv-head"><h3><i class="fas fa-chart-pie" aria-hidden="true"></i> Tashrif buyurgan qurilmalar</h3></header>'
                           '<p class="nzv-empty">Hali tashrif ma\'lumoti yo\'q. Sayt ochilganda har bir qurilma shu yerda hisoblanadi.</p></section>')
    cls = {r["key"]: r for r in s["classes"]}
    head_kpis = format_html(
        '<div class="nzv-kpis"><div><small>Noyob qurilmalar</small><b>{}</b><span>{}</span></div>'
        '<div><small><i class="fas fa-mobile-screen-button" aria-hidden="true"></i> Telefon</small><b>{}%</b><span>{} ta</span></div>'
        '<div><small><i class="fas fa-desktop" aria-hidden="true"></i> Kompyuter</small><b>{}%</b><span>{} ta</span></div>'
        '<div><small><i class="fas fa-tablet-screen-button" aria-hidden="true"></i> Planshet</small><b>{}%</b><span>{} ta</span></div>'
        '<div><small>Tashriflar</small><b>{}</b><span>{} yangi · {} qaytgan</span></div></div>',
        f"{total:,}".replace(",", " "), label.lower(),
        cls["mobile"]["pct"], cls["mobile"]["n"], cls["desktop"]["pct"], cls["desktop"]["n"], cls["tablet"]["pct"], cls["tablet"]["n"],
        f"{s['visits']:,}".replace(",", " "), s["new"], s["returning"])

    os_bars = _bars(s["os"], lambda k: k, lambda k: OS_ICON.get(k, "fas fa-circle"))
    br_bars = _bars(s["browsers"], lambda k: k, lambda k: "fas fa-compass")
    app_bars = _bars(s["in_app"], lambda k: IN_APP_LABEL.get(k, k), lambda k: IN_APP_ICON.get(k, "fas fa-globe"),
                     "Telegram — Mini App va Telegram ichida ochilgan havolalar; Instagram / Facebook — ilova ichidagi brauzer.")
    brand_bars = _bars(s["brands"], lambda k: k, lambda k: "fas fa-mobile-screen",
                       "Telefon va planshetlar ichida. Android Chrome modelni yashiradi — model sayt kodi orqali aniqlanadi (yangi tashriflardan boshlab).")
    ver_bars = _bars(s["versions"], lambda k: k, lambda k: OS_ICON.get(k.split(" ")[0], "fas fa-code-branch"))
    since = f"{s['since']:%d.%m.%Y}" if s["since"] else "—"
    list_link = format_html('<a class="nzv-more" href="{}"><i class="fas fa-list" aria-hidden="true"></i> Barcha qurilmalar ro\'yxati</a>', list_url) if list_url else ""
    return format_html(
        '<section class="nzp-card nzv"><header class="nzv-head"><h3><i class="fas fa-chart-pie" aria-hidden="true"></i> Tashrif buyurgan qurilmalar</h3>'
        '<nav class="nzv-tabs" aria-label="Davr">{}</nav></header>{}'
        '<div class="nzv-grid">'
        '<div class="nzv-box nzv-box-split"><h4>Telefon yoki kompyuter</h4>{}</div>'
        '<div class="nzv-box"><h4>Operatsion tizim</h4>{}</div>'
        '<div class="nzv-box nzv-box-wide"><h4>Kunlik dinamika</h4>{}</div>'
        '<div class="nzv-box"><h4>Brauzer</h4>{}</div>'
        '<div class="nzv-box"><h4>Qayerdan ochilgan</h4>{}</div>'
        '<div class="nzv-box"><h4>Telefon brendi</h4>{}</div>'
        '<div class="nzv-box"><h4>Tizim versiyasi</h4>{}</div>'
        '</div><footer class="nzv-foot"><span>Hisob {} dan beri · har bir brauzer/telefon bir marta sanaladi · {} ta bot va server so\'rovi hisobga olinmadi.</span>{}</footer></section>',
        mark_safe("".join(tabs)), head_kpis, _donut(s["classes"], total), os_bars, _trend(s["trend"]), br_bars, app_bars, brand_bars, ver_bars,
        since, s["bots"], list_link)


def device_label(d: VisitorDevice) -> str:
    name = " ".join(x for x in (d.brand, d.model if d.model and d.model not in (d.brand,) else "") if x) or CLASS_LABEL.get(d.device_class, "")
    return name


