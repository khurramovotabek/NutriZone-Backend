"""
Premium Dashboard for Do'konlar: list analytics (sales, stock, rating, open now), the ratings moderation view, and
the store form's human widgets -- phone list instead of JSON, region→city picker from the geo reference data,
a Leaflet map picker, a 7-day working-hours grid and special days without JSON.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

PHONE_RE = re.compile(r"^\+998\d{9}$")


# ------------------------------------------------------------------ numbers


def store_sales(days: int = 30) -> dict:
    """store_id -> {"revenue", "sales", "prev_revenue"} from completed POS sales (refunded units excluded, discounts off)."""
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    now = timezone.now()
    out: dict = {}

    def collect(start, end, key_rev, key_n):
        lines = (
            SaleLineItemModel.objects.filter(sale__status__in=("completed", "refunded"), sale__completed_at__gte=start, sale__completed_at__lt=end)
            .values("sale__branch_id").annotate(t=Sum((F("quantity") - F("refunded_quantity")) * F("unit_price_amount")))
        )
        for r in lines:
            out.setdefault(r["sale__branch_id"], {"revenue": Decimal(0), "sales": 0, "prev_revenue": Decimal(0)})[key_rev] += r["t"] or 0
        sales = SaleModel.objects.filter(status__in=("completed", "refunded"), completed_at__gte=start, completed_at__lt=end).values("branch_id").annotate(n=Count("id"), d=Sum("discount_amount"))
        for r in sales:
            row = out.setdefault(r["branch_id"], {"revenue": Decimal(0), "sales": 0, "prev_revenue": Decimal(0)})
            row[key_rev] -= r["d"] or 0
            if key_n:
                row[key_n] += r["n"]

    collect(now - timedelta(days=days), now, "revenue", "sales")
    collect(now - timedelta(days=days * 2), now - timedelta(days=days), "prev_revenue", None)
    return out


def stars(avg, count: int | None = None, size: str = ".85rem") -> str:
    if avg is None:
        return mark_safe('<span class="nzc-muted">Baho yo\'q</span>')
    full = int(round(float(avg)))
    s = "".join('<i class="fas fa-star" style="color:#f59e0b"></i>' if i < full else '<i class="far fa-star" style="color:#64748b"></i>' for i in range(5))
    c = f' <small class="nzc-muted">({count})</small>' if count is not None else ""
    return mark_safe(f'<span class="nzs-stars" style="font-size:{size};white-space:nowrap">{s} <b>{float(avg):.1f}</b>{c}</span>')


# ------------------------------------------------------------------ widgets


class PhoneListWidget(forms.Widget):
    """Several phone numbers as ordinary inputs (+998 XX XXX XX XX); stored as the JSON list the model expects."""

    def value_from_datadict(self, data, files, name):
        values = data.getlist(f"{name}__item") if hasattr(data, "getlist") else data.get(f"{name}__item", [])
        if not values and name in data:  # API / tests posting the raw JSON list
            return data.get(name)
        return json.dumps([v for v in values if v and v.strip()])

    def render(self, name, value, attrs=None, renderer=None):
        if isinstance(value, str):
            try:
                value = json.loads(value or "[]")
            except ValueError:
                value = [value]
        items = [v for v in (value or []) if v] or [""]
        rows = "".join(
            f'<div class="nzf-phone"><span class="nzf-prefix"><i class="fas fa-phone"></i></span><input type="tel" name="{name}__item" value="{escape(v)}" placeholder="+998 90 123 45 67" class="vTextField" autocomplete="off">'
            f'<button type="button" class="nzf-x" title="O\'chirish" onclick="var r=this.parentNode,l=r.parentNode;if(l.children.length>2)r.remove();else r.querySelector(\'input\').value=\'\'">×</button></div>'
            for v in items
        )
        return mark_safe(f'<div class="nzf-phones" data-name="{name}">{rows}<button type="button" class="nzf-add" onclick="var t=this.previousElementSibling.cloneNode(true);t.querySelector(\'input\').value=\'\';this.before(t);t.querySelector(\'input\').focus()"><i class="fas fa-plus"></i> Raqam qo\'shish</button></div>')


class CityWidget(forms.Widget):
    """Region → city dropdown from the geo reference data (grouped by viloyat); "Boshqa" keeps free text possible."""

    def value_from_datadict(self, data, files, name):
        v = data.get(name) or ""
        return (data.get(f"{name}__other") or "").strip() if v == "__other" else v

    def render(self, name, value, attrs=None, renderer=None):
        from apps.geo.infrastructure.models import Region

        value = value or ""
        groups, known = [], False
        regions = Region.objects.filter(status="active").prefetch_related("translations", "cities__translations")
        for r in sorted(regions, key=lambda r: (r.code != "TGCITYR", next((t.name for t in r.translations.all() if t.locale_code == "uz"), r.code))):
            rname = next((t.name for t in r.translations.all() if t.locale_code == "uz"), r.code)
            opts = []
            for c in sorted(r.cities.all(), key=lambda c: next((t.name for t in c.translations.all() if t.locale_code == "uz"), c.code)):
                cname = next((t.name for t in c.translations.all() if t.locale_code == "uz"), None)
                if not cname or c.is_deleted:
                    continue
                sel = cname == value
                known = known or sel
                opts.append(f'<option value="{escape(cname)}" data-lat="{c.center_latitude or ""}" data-lng="{c.center_longitude or ""}" data-region="{escape(rname)}"{" selected" if sel else ""}>{escape(cname)}</option>')
            if opts:
                groups.append(f'<optgroup label="{escape(rname)}">{"".join(opts)}</optgroup>')
        other = value and not known
        return mark_safe(
            f'<div class="nzf-city"><select name="{name}" id="id_{name}" class="nzf-select" onchange="this.parentNode.querySelector(\'input[name$=__other]\').hidden=this.value!==\'__other\';document.dispatchEvent(new CustomEvent(\'nz:city\',{{detail:this.selectedOptions[0]}}))">'
            f'<option value="">— Shaharni tanlang —</option>{"".join(groups)}<option value="__other"{" selected" if other else ""}>Boshqa (qo\'lda yozish)…</option></select>'
            f'<input type="text" name="{name}__other" value="{escape(value) if other else ""}" placeholder="Shahar nomi" class="vTextField"{"" if other else " hidden"}></div>'
        )


class SpecialDaysWidget(forms.Widget):
    """Holidays / special days: date + closed or open–close + note. Stored as the JSON list is_open_now() reads."""

    def value_from_datadict(self, data, files, name):
        if not hasattr(data, "getlist") or f"{name}__date" not in data:
            return data.get(name)
        dates, opens, closes, notes = data.getlist(f"{name}__date"), data.getlist(f"{name}__open"), data.getlist(f"{name}__close"), data.getlist(f"{name}__note")
        closed = set(data.getlist(f"{name}__closed"))
        rows = []
        for i, d in enumerate(dates):
            if not d:
                continue
            row = {"date": d, "closed": str(i) in closed}
            if not row["closed"]:
                row.update({"open": opens[i] if i < len(opens) else "", "close": closes[i] if i < len(closes) else ""})
            if i < len(notes) and notes[i].strip():
                row["note"] = notes[i].strip()[:80]
            rows.append(row)
        return json.dumps(rows)

    def render(self, name, value, attrs=None, renderer=None):
        if isinstance(value, str):
            try:
                value = json.loads(value or "[]")
            except ValueError:
                value = []
        rows = list(value or [])

        def row(i, r):
            closed = r.get("closed", True) if r else True
            return (
                f'<div class="nzf-sday"><input type="date" name="{name}__date" value="{escape(r.get("date", ""))}" class="vTextField">'
                f'<label class="nzf-chk"><input type="checkbox" name="{name}__closed" value="{i}"{" checked" if closed else ""} onchange="this.closest(\'.nzf-sday\').classList.toggle(\'is-closed\',this.checked)"> Dam olish</label>'
                f'<input type="time" name="{name}__open" value="{escape(r.get("open", ""))}"><span>—</span><input type="time" name="{name}__close" value="{escape(r.get("close", ""))}">'
                f'<input type="text" name="{name}__note" value="{escape(r.get("note", ""))}" placeholder="Masalan: Navro\'z" class="vTextField">'
                f'<button type="button" class="nzf-x" onclick="this.parentNode.remove()">×</button></div>'
            )

        html = "".join(row(i, r) for i, r in enumerate(rows))
        return mark_safe(
            f'<div class="nzf-sdays" data-next="{len(rows)}">{html}<template>{row("__i__", {})}</template>'
            f'<button type="button" class="nzf-add" onclick="var w=this.parentNode,n=+w.dataset.next;w.dataset.next=n+1;var d=document.createElement(\'div\');d.innerHTML=w.querySelector(\'template\').innerHTML.replace(/__i__/g,n);var el=d.firstChild;el.classList.add(\'is-closed\');this.before(el)"><i class="fas fa-calendar-plus"></i> Maxsus kun qo\'shish</button></div>'
            f'<script>document.querySelectorAll(".nzf-sday").forEach(function(r){{var c=r.querySelector("[type=checkbox]");if(c&&c.checked)r.classList.add("is-closed")}});</script>'
        )


def map_picker_html(obj) -> str:
    lat = obj.latitude if obj and obj.latitude is not None else ""
    lng = obj.longitude if obj and obj.longitude is not None else ""
    return format_html(
        '<div class="nzf-map-wrap"><div id="nzf-map" class="nzf-map" data-lat="{}" data-lng="{}"></div>'
        '<div class="nzf-map-bar"><span><i class="fas fa-hand-pointer"></i> Xaritada bosing yoki markerni suring — koordinatalar o\'zi yoziladi</span>'
        '<button type="button" class="nzf-add" id="nzf-locate"><i class="fas fa-location-crosshairs"></i> Mening joylashuvim</button></div></div>',
        lat, lng,
    )
