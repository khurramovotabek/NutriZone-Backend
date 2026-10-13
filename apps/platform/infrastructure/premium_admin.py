"""
Premium admin building blocks shared by the dashboard sections (Identity, Loyalty, ...): one list layout
(templates/admin/premium/list.html via PremiumListMixin), KPI / tab / chip helpers and customer cells
(avatar + name + phone). Presentation only -- no business logic.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.html import format_html

TZ = ZoneInfo("Asia/Tashkent")
ASSET_V = "11"  # cache-buster for the section stylesheets (nz_css) -- bump after editing one
AVATAR_TONES = ["#2563eb", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#db2777", "#4f46e5", "#0d9488"]


def local(dt, fmt: str = "%d.%m.%Y %H:%M") -> str:
    return timezone.localtime(dt, TZ).strftime(fmt) if dt else "—"


def ago(dt) -> str:
    """"3 daqiqa oldin" / "2 kun oldin" -- or "… keyin" for a time in the future."""
    if dt is None:
        return "—"
    seconds = int((timezone.now() - dt).total_seconds())
    future = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        return "hozirgina"
    for size, unit in ((31536000, "yil"), (2592000, "oy"), (604800, "hafta"), (86400, "kun"), (3600, "soat"), (60, "daqiqa")):
        if seconds >= size:
            return f"{seconds // size} {unit} {'keyin' if future else 'oldin'}"
    return "hozirgina"


def initials(name: str) -> str:
    return "".join(p[0] for p in (name or "").split()[:2]).upper() or "#"


def tone(key) -> str:
    return AVATAR_TONES[int(str(key).replace("-", "")[:6], 16) % len(AVATAR_TONES)]


def avatar_url(user) -> str | None:
    """The newest uploaded avatar (expects `avatar_assets` prefetched newest-first when called per row)."""
    latest = next(iter(user.avatar_assets.all()), None) if user is not None else None
    if latest is None or not latest.storage_path:
        return None
    path = (latest.thumbnail_paths or {}).get("small") or latest.storage_path
    return path if path.startswith(("http://", "https://")) else f"{settings.MEDIA_URL}{path}"


def avatar(user, size: str = "") -> str:
    if user is None:
        return format_html('<span class="nzi-av {}" style="--c:#64748b"><i class="fas fa-user-slash" aria-hidden="true"></i></span>', size)
    url = avatar_url(user)
    if url:
        return format_html('<span class="nzi-av {}"><img src="{}" alt=""></span>', size, url)
    return format_html('<span class="nzi-av {}" style="--c:{}">{}</span>', size, tone(user.id), initials(user.full_name))


def user_cell(user, href: str = "") -> str:
    """Avatar + name + phone, linking to the user's card."""
    if user is None:
        return format_html('<span class="nzi-user">{}<span><b>{}</b></span></span>', avatar(None), "O'chirilgan foydalanuvchi")
    sub = " · ".join(x for x in (user.phone_number, f"@{user.username}" if user.username else "") if x)
    return format_html('<span class="nzi-user">{}<span><b>{}</b><small>{}</small></span></span>', avatar(user), user.full_name or "Ismsiz foydalanuvchi", sub)


# ---------------------------------------------------------------- premium change list


class PremiumListMixin:
    """
    One premium list layout for every dashboard section (templates/admin/premium/list.html): hero, clickable
    KPI cards, status tabs, the admin's own filters as compact selects, search, card-like rows and bulk actions.
    A ModelAdmin sets the nz_* attributes and implements `nz_row(obj)` (cell HTML) -- sorting, filtering,
    pagination and actions stay the stock ChangeList machinery.
    """

    change_list_template = "admin/premium/list.html"
    nz_icon = "fa-users"
    nz_tone = "#6366f1"
    nz_title = ""
    nz_subtitle = ""
    nz_columns: tuple = ()  # (label, css class) -- "r" right-aligns
    nz_grid = ""  # CSS grid-template-columns for the rows
    nz_search = "Qidirish…"
    nz_empty = ("Hali yozuv yo'q", "")
    nz_sorts: tuple = ()  # (label, value of the `o` parameter)
    nz_css: tuple = ()  # extra stylesheets (static paths) for this page
    nz_layout = "table"  # "gallery": cards -- the first cell is the media, the rest its caption lines

    def nz_row(self, obj) -> list:  # pragma: no cover - overridden
        return []

    def nz_href(self, obj) -> str:
        from django.urls import reverse

        opts = self.model._meta
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])

    def nz_stats(self, request) -> list[dict]:
        return []

    def nz_tabs(self, request) -> list[dict]:
        return []

    def nz_hero_actions(self, request) -> list[dict]:
        return []

    def nz_prepare(self, request, objs) -> None:
        """Bulk-load whatever the rows need (one pass over the page) before nz_row runs."""

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)  # deletes go through each page's own service-backed action
        return actions

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        rows = list(cl.result_list)
        self.nz_prepare(request, rows)
        for r in rows:
            r.nz_cells = self.nz_row(r)
            r.nz_link = self.nz_href(r)
        cl.nz_rows = rows
        return cl

    def changelist_view(self, request, extra_context=None):
        params = request.GET.copy()
        params.pop("p", None)

        def tab_url(**kv):
            q = params.copy()
            for k, v in kv.items():
                q.pop(k, None)
                if v not in (None, ""):
                    q[k] = v
            return "?" + q.urlencode() if q else "?"

        actions = [{"name": name, "label": str(desc)} for name, (_f, _n, desc) in self.get_actions(request).items()]
        nz = {
            "icon": self.nz_icon, "tone": self.nz_tone, "title": self.nz_title or self.model._meta.verbose_name_plural, "subtitle": self.nz_subtitle,
            "columns": self.nz_columns, "grid": self.nz_grid, "search": self.nz_search, "empty": self.nz_empty,
            "stats": self.nz_stats(request), "tabs": self.nz_tabs(request), "hero_actions": self.nz_hero_actions(request), "actions": actions,
            "sorts": [{"label": label, "url": tab_url(o=o), "on": params.get("o", "") == o} for label, o in self.nz_sorts],
            "tab_url": tab_url, "can_add": self.has_add_permission(request), "css": self.nz_css, "asset_v": ASSET_V, "layout": self.nz_layout,
        }
        return super().changelist_view(request, {**(extra_context or {}), "nz": nz, "title": nz["title"]})


def tabs_for(request, param: str, options, color_of=None) -> list[dict]:
    """Status tabs for one GET parameter: options = [(value or "", label, count)]."""
    params = request.GET.copy()
    params.pop("p", None)
    current = params.get(param, "")
    out = []
    for value, label, n in options:
        q = params.copy()
        q.pop(param, None)
        if value:
            q[param] = value
        out.append({"label": label, "n": n, "url": "?" + q.urlencode() if q else "?", "on": current == value,
                    "color": (color_of or {}).get(value, "#6366f1")})
    return out


def stat_card(label: str, value, tone: str, icon: str, sub: str = "", href: str = "") -> dict:
    return {"label": label, "value": value, "tone": tone, "icon": icon, "sub": sub, "href": href}


def chip(text: str, color: str = "#64748b", icon: str = "") -> str:
    if icon:
        return format_html('<span class="nzi-chip" style="--t:{}"><i class="fas {}" aria-hidden="true"></i> {}</span>', color, icon, text)
    return format_html('<span class="nzi-chip" style="--t:{}">{}</span>', color, text)


def muted(text: str = "—") -> str:
    return format_html('<span class="nzi-muted">{}</span>', text)


# ---------------------------------------------------------------- premium add / change form


def _catalog_form():
    from apps.products.infrastructure.catalog_form_ui import CatalogFormMixin

    return CatalogFormMixin


class PremiumFormMixin(_catalog_form()):
    """
    The catalog's premium form chrome (hero + section bar + cards, CatalogFormMixin) for any section: implement
    `form_hero(request, obj)`; fieldsets with class "nzi-panel" render read-only HTML panels full width.
    """

    change_form_template = "admin/premium/form.html"
    nz_css: tuple = ()

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["nz_css"], context["nz_asset_v"] = self.nz_css, ASSET_V
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)


def hero_stat(label: str, value, tone: str, sub: str = "", icon: str = "") -> dict:
    return {"label": label, "value": value, "tone": tone, "sub": sub, "icon": icon}
