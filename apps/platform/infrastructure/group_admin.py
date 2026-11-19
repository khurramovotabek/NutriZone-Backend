"""
Dashboard → Autentifikatsiya → Guruhlar (staff roles): the stock Django pages replaced by the premium kit.

* List: what each role may do at a glance -- members, number of permissions, the sections it reaches and its
  level (faqat ko'rish / tahrir / to'liq), plus the staff accounts that sit in no role at all.
* Form: a permission matrix (section → model → ko'rish / qo'shish / o'zgartirish / o'chirish + special rights)
  with search and one-click "view everything here" toggles instead of a 600-line two-pane picker, and the
  role's members chosen on the same page.
* "Nusxa olish" duplicates a role with its permissions -- new roles usually start from an existing one.

The same matrix widget replaces the staff account form's "user permissions" picker (PermissionMatrixWidget).
"""
from __future__ import annotations

from collections import defaultdict

from django import forms
from django.apps import apps as django_apps
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat

CRUD = (("view", "Ko'rish"), ("add", "Qo'shish"), ("change", "O'zgartirish"), ("delete", "O'chirish"))
# framework internals nobody grants to a role -- shown last, folded
SYSTEM_APPS = ("admin", "contenttypes", "sessions", "token_blacklist", "django_celery_beat", "django_celery_results", "auth")
ASSET = f"{settings.STATIC_URL}admin/{{}}?v=2"


def _app_label(label: str) -> str:
    try:
        return str(django_apps.get_app_config(label).verbose_name)
    except LookupError:
        return label


def _app_icon(label: str) -> str:
    icons = (getattr(settings, "JAZZMIN_SETTINGS", {}) or {}).get("icons", {})
    return icons.get(label, "fas fa-layer-group")


def _tone(text: str) -> str:
    import hashlib

    return ui.tone(hashlib.md5(text.encode()).hexdigest())  # noqa: S324 - a colour, not security


def level_of(codenames) -> tuple[str, str]:
    """A role's overall reach from its permission codenames: (label, colour)."""
    codes = list(codenames)
    if not codes:
        return "Ruxsatsiz", "#94a3b8"
    if any(c.startswith("delete_") for c in codes):
        return "To'liq (o'chirish ham)", "#e11d48"
    if any(c.startswith(("add_", "change_")) for c in codes):
        return "Tahrirlash", "#d97706"
    return "Faqat ko'rish", "#16a34a"


class PermissionMatrixWidget(forms.CheckboxSelectMultiple):
    """The permission picker as a table: one row per model, a column per standard action, special rights as chips."""

    class Media:
        css = {"all": (ASSET.format("css/nutrizone-perm-matrix.css"),)}
        js = (ASSET.format("js/nutrizone-perm-matrix.js"),)

    def render(self, name, value, attrs=None, renderer=None):
        chosen = {str(v) for v in (value or [])}
        perms = Permission.objects.select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename")
        apps_map: dict[str, dict[str, dict]] = defaultdict(dict)
        for p in perms:
            ct = p.content_type
            model = ct.model_class()
            row = apps_map[ct.app_label].setdefault(ct.model, {
                "label": str(model._meta.verbose_name_plural) if model else ct.model, "crud": {}, "extra": []})
            action = p.codename.split("_", 1)[0]
            if action in dict(CRUD) and p.codename == f"{action}_{ct.model}":
                row["crud"][action] = p
            else:
                row["extra"].append(p)

        def box(p, text=""):
            on = str(p.pk) in chosen
            return format_html('<label class="nzpm-box{}" title="{}"><input type="checkbox" data-no-switch name="{}" value="{}"{}><span>{}</span></label>',
                               " has-text" if text else "", p.name, name, p.pk, mark_safe(" checked") if on else "", text)

        order = sorted(apps_map, key=lambda a: (a in SYSTEM_APPS, _app_label(a).lower()))
        sections = []
        for app in order:
            rows = apps_map[app]
            all_perms = [p for r in rows.values() for p in [*r["crud"].values(), *r["extra"]]]
            n_on = sum(1 for p in all_perms if str(p.pk) in chosen)
            body = []
            for r in sorted(rows.values(), key=lambda r: r["label"].lower()):
                cells = format_html_join("", "<td>{}</td>", ((box(r["crud"][a]) if a in r["crud"] else mark_safe('<span class="nzpm-none">—</span>'),) for a, _l in CRUD))
                extra = format_html_join(" ", "{}", ((box(p, p.name),) for p in r["extra"]))
                body.append(format_html('<tr data-search="{}"><th scope="row"><button type="button" class="nzpm-row" title="Qatorni yoqish / o\'chirish">{}</button></th>{}<td class="nzpm-extra">{}</td></tr>',
                                        f"{_app_label(app)} {r['label']}".lower(), r["label"], cells, extra))
            sections.append(format_html(
                '<details class="nzpm-app{}" data-app="{}"{}><summary><i class="{}" aria-hidden="true"></i><b>{}</b>'
                '<span class="nzpm-count" data-total="{}">{} / {}</span><span class="nzpm-tools">'
                '<button type="button" data-pm="view">Faqat ko\'rish</button><button type="button" data-pm="all">Hammasi</button><button type="button" data-pm="none">Tozalash</button>'
                '</span></summary><table class="nzpm-table"><thead><tr><th>Bo\'lim</th>{}<th>Maxsus huquqlar</th></tr></thead><tbody>{}</tbody></table></details>',
                " is-system" if app in SYSTEM_APPS else "", app, mark_safe(" open") if n_on and app not in SYSTEM_APPS else "",
                _app_icon(app), _app_label(app), len(all_perms), n_on, len(all_perms),
                format_html_join("", "<th>{}</th>", ((label,) for _a, label in CRUD)), mark_safe("".join(body))))
        return format_html(
            '<div class="nzpm" data-name="{}"><div class="nzpm-bar"><span class="nzpm-search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i>'
            '<input type="search" placeholder="Bo\'lim yoki model: buyurtma, ombor, chek…" aria-label="Ruxsatlarni qidirish"></span>'
            '<span class="nzpm-total"><b data-pm-total>{}</b> ta ruxsat tanlangan</span>'
            '<button type="button" class="nzpm-btn" data-pm-expand>Hammasini ochish</button></div>{}</div>',
            name, len(chosen), mark_safe("".join(sections)))

    def value_from_datadict(self, data, files, name):
        return data.getlist(name)


class GroupAdminForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(queryset=get_user_model().objects.none(), required=False, label="A'zolar (xodimlar)",
                                             widget=forms.CheckboxSelectMultiple(attrs={"class": "nzpm-members"}),
                                             help_text="Belgilangan xodimlar shu guruhning barcha ruxsatlarini oladi. Superuser'ga guruh shart emas.")

    class Meta:
        model = Group
        fields = ("name", "permissions")
        labels = {"name": "Guruh (rol) nomi", "permissions": "Ruxsatlar"}
        help_texts = {"name": "Masalan: Kassir, Sklad operatori, Kontent menejeri", "permissions": ""}
        widgets = {"permissions": PermissionMatrixWidget, "name": forms.TextInput(attrs={"class": "vTextField", "autocomplete": "off"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["members"].queryset = User.objects.filter(is_active=True, is_superuser=False).order_by("username")
        self.fields["members"].label_from_instance = lambda u: f"{u.get_full_name() or u.username} · {u.username}" + ("" if u.is_staff else " (dashboardga kirolmaydi)")
        if not self.fields["members"].queryset.exists():
            self.fields["members"].help_text = "Hali dashboard xodimi yo'q (superuser'larga guruh shart emas). «Xodimlar» sahifasida xodim qo'shing — keyin shu yerda belgilaysiz."
        if self.instance.pk:
            self.fields["members"].initial = list(self.instance.user_set.values_list("pk", flat=True))


class GroupAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = GroupAdminForm
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)
    actions = ["duplicate"]
    fieldsets = (
        ("Guruh", {"fields": ("name", "members")}),
        ("Ruxsatlar", {"fields": ("permissions",), "description": "Har bir bo'lim uchun nima qila olishini belgilang. «Faqat ko'rish» — xavfsiz boshlang'ich nuqta; "
                                                                   "o'chirish huquqini faqat kerakli rolga bering."}),
    )
    nz_icon, nz_tone, nz_title = "fa-user-shield", "#7c3aed", "Guruhlar (xodim rollari)"
    nz_subtitle = "Har bir rol — dashboardda nima ko'rish va o'zgartirish mumkinligi. Xodimga guruh berish shaxsiy ruxsatlardan ko'ra xavfsiz va tartibli."
    nz_columns = (("Rol", ""), ("A'zolar", ""), ("Bo'limlar", ""), ("Daraja", ""), ("Ruxsatlar", "r"))
    nz_grid = "minmax(220px,2fr) minmax(170px,1.3fr) minmax(220px,2.2fr) 170px 110px"
    nz_search = "Guruh nomi…"
    nz_empty = ("Guruh topilmadi", "«Yangi guruh» bilan rol yarating, so'ng xodimlarni biriktiring.")
    nz_sorts = (("Nomi", ""), ("Ko'p a'zoli", "-2"))
    hero_icon, hero_tone, hero_noun = "fa-user-shield", "#7c3aed", "guruh"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(nz_members=Count("user", distinct=True), nz_perms=Count("permissions", distinct=True))

    def nz_prepare(self, request, objs):
        ids = [g.pk for g in objs]
        self._codes, self._apps, self._people = defaultdict(list), defaultdict(set), defaultdict(list)
        for gid, code, app in Group.permissions.through.objects.filter(group_id__in=ids).values_list("group_id", "permission__codename", "permission__content_type__app_label"):
            self._codes[gid].append(code)
            self._apps[gid].add(app)
        User = get_user_model()
        for gid, uname, first, last in User.groups.through.objects.filter(group_id__in=ids).values_list("group_id", "user__username", "user__first_name", "user__last_name"):
            self._people[gid].append(f"{first} {last}".strip() or uname)

    def nz_stats(self, request):
        User = get_user_model()
        staff = User.objects.filter(is_active=True, is_staff=True, is_superuser=False)
        lonely = staff.annotate(g=Count("groups")).filter(g=0).count()
        direct = staff.annotate(p=Count("user_permissions")).filter(p__gt=0).count()
        base = reverse("admin:auth_user_changelist")
        return [ui.stat_card("Guruhlar", Group.objects.count(), "#7c3aed", "fa-user-shield", "xodim rollari"),
                ui.stat_card("Guruhdagi xodimlar", staff.filter(groups__isnull=False).distinct().count(), "#16a34a", "fa-users", f"{staff.count()} ta faol xodimdan", href=base),
                ui.stat_card("Guruhsiz xodimlar", lonely, "#f59e0b" if lonely else "#64748b", "fa-user-slash", "dashboardda hech narsa ko'rmaydi" if lonely else "hammasi rolga ega",
                             href=f"{base}?groups__isnull=True" if lonely else ""),
                ui.stat_card("Shaxsiy ruxsatli", direct, "#e11d48" if direct else "#64748b", "fa-key", "guruhga o'tkazgan ma'qul" if direct else "toza — hammasi guruh orqali")]

    def nz_hero_actions(self, request):
        return [{"label": "Xodimlar", "url": reverse("admin:auth_user_changelist"), "icon": "fa-users"},
                {"label": "Yangi guruh", "url": reverse("admin:auth_group_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, g):
        people = self._people.get(g.pk, [])
        avatars = format_html_join("", '<span class="nzi-av" style="--c:{};width:26px;height:26px;font-size:10px;margin-right:-6px" title="{}">{}</span>',
                                   ((_tone(p), p, ui.initials(p)) for p in people[:5]))
        members = format_html('<span style="display:inline-flex;align-items:center;gap:10px">{}<b style="margin-left:8px">{}</b><small class="nzi-muted">xodim</small></span>', avatars, len(people)) \
            if people else ui.muted("a'zo yo'q")
        apps = sorted(self._apps.get(g.pk, ()), key=lambda a: _app_label(a).lower())
        chips = format_html_join(" ", "{}", ((ui.chip(_app_label(a), "#0891b2"),) for a in apps[:4]))
        more = format_html(' <span class="nzi-muted">+{}</span>', len(apps) - 4) if len(apps) > 4 else ""
        level, color = level_of(self._codes.get(g.pk, []))
        return [format_html('<span class="nzi-user"><span class="nzi-av" style="--c:{}"><i class="fas fa-user-shield"></i></span><span><b>{}</b><small>{} bo\'lim</small></span></span>',
                            _tone(g.name), g.name, len(apps)),
                members, format_html("{}{}", chips, more) if apps else ui.muted(),
                format_html('<span class="nzi-pill" style="--t:{}">{}</span>', color, level), format_html("<b>{}</b>", g.nz_perms)]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Nom bering, a'zolarni belgilang va har bir bo'lim uchun ruxsatlarni tanlang"}
        codes = list(obj.permissions.values_list("codename", flat=True))
        apps = set(obj.permissions.values_list("content_type__app_label", flat=True))
        level, color = level_of(codes)
        return {"title": obj.name, "subtitle": "Xodim roli — a'zolar shu ruxsatlar bilan ishlaydi",
                "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', color, level)],
                "stats": [hero_stat("A'zolar", obj.user_set.count(), "#16a34a", "xodim", "fa-users"),
                          hero_stat("Ruxsatlar", len(codes), "#7c3aed", f"{Permission.objects.count()} tadan", "fa-key"),
                          hero_stat("Bo'limlar", len(apps), "#0891b2", "qamrab olingan", "fa-layer-group")]}

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.user_set.set(form.cleaned_data.get("members") or [])

    @admin.action(description="Nusxa olish (ruxsatlari bilan, a'zolarsiz)", permissions=["add"])
    def duplicate(self, request, queryset):
        made = []
        for g in queryset:
            name, n = f"{g.name} (nusxa)", 2
            while Group.objects.filter(name=name).exists():
                name, n = f"{g.name} (nusxa {n})", n + 1
            copy = Group.objects.create(name=name)
            copy.permissions.set(g.permissions.all())
            made.append(name)
        self.message_user(request, "Yaratildi: " + ", ".join(made), messages.SUCCESS)


def install() -> None:
    """Swap the stock Group admin for the premium one, and the staff form's permission picker for the matrix."""
    if admin.site.is_registered(Group):
        admin.site.unregister(Group)
    admin.site.register(Group, GroupAdmin)
    User = get_user_model()
    user_admin = admin.site._registry.get(User)
    if user_admin is not None:
        base = user_admin.formfield_for_manytomany

        def formfield_for_manytomany(db_field, request, **kwargs):
            if db_field.name == "user_permissions":
                kwargs["widget"] = PermissionMatrixWidget
                kwargs["help_text"] = "Faqat shu xodimga xos qo'shimcha huquq. Odatda guruh (rol) orqali bergan ma'qul."
            return base(db_field, request, **kwargs)

        user_admin.formfield_for_manytomany = formfield_for_manytomany


__all__ = ["GroupAdmin", "PermissionMatrixWidget", "install", "level_of"]
