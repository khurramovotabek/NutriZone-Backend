"""
apps/platform/infrastructure/admin.py

Site settings, banners and contact messages. Feature flags are
deliberately not registered here (product decision: no dashboard page
for them -- they stay governed via the API).
"""
from __future__ import annotations


from django import forms
from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from apps.platform.infrastructure import models as orm


def _direct_thumbnail_html(storage_path: str, thumbnail_paths: dict) -> str:
    """Media Asset architecture removal (per explicit product decision): takes an entity's own storage_path/thumbnail_paths fields directly, with no ProductMediaAsset FK/lookup involved at all -- same pattern as Product/Category/BrandAdmin's own equivalent helper (apps/products/infrastructure/admin.py)."""
    if not storage_path:
        return mark_safe('<div class="nz-thumb nz-thumb-empty"><i class="fas fa-image" aria-hidden="true"></i></div>')
    path = thumbnail_paths.get("small") or storage_path
    url = f"{settings.MEDIA_URL}{path}" if not path.startswith(("http://", "https://")) else path
    return format_html('<img src="{}" class="nz-thumb" alt="">', url)


def get_site_settings() -> orm.SiteSettings:
    """The single, safe entry point every consumer (context processor, templates, future storefront integration) should use -- get_or_create is safe under concurrent creation because SiteSettings' own fixed primary key (id=1) prevents a second row from ever being inserted at the database level."""
    settings_obj, _ = orm.SiteSettings.objects.get_or_create(pk=1)
    return settings_obj


@admin.register(orm.SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton-safe: no add (only the id=1 row from get_site_settings() is ever used), no delete (the dashboard should never be left without a settings row)."""

    fieldsets = (
        ("General", {"fields": ("site_name", "short_name", "default_language")}),
        ("Branding", {"fields": ("logo", "logo_preview", "favicon", "favicon_preview", "primary_color", "primary_color_swatch", "secondary_color", "accent_color")}),
        ("Contact", {"fields": ("support_phone", "support_email", "address", "working_hours", "telegram_username", "telegram_channel_url", "instagram_url")}),
    )
    readonly_fields = ("logo_preview", "favicon_preview", "primary_color_swatch", "updated_at")

    def primary_color_swatch(self, obj):
        from django.utils.html import format_html

        if not obj or not obj.primary_color:
            return "—"
        return format_html('<span style="display:inline-block;width:24px;height:24px;border-radius:4px;border:1px solid var(--nz-border);background:{};vertical-align:middle;"></span> {}', obj.primary_color, obj.primary_color)

    primary_color_swatch.short_description = "Ko'rinishi"

    def has_add_permission(self, request) -> bool:
        return not orm.SiteSettings.objects.exists()

    # The sidebar's "Site Settings" entry opens the single premium settings page instead of a bare change form.
    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect

        return redirect("admin:nz_settings_overview")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from django.shortcuts import redirect

        return redirect("admin:nz_settings_overview")

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def logo_preview(self, obj):
        from django.utils.html import format_html

        if obj and obj.logo:
            return format_html('<img src="{}" style="max-height: 60px;" alt="Logo preview">', obj.logo.url)
        return "(no logo uploaded)"

    logo_preview.short_description = "Ko'rinishi"

    def favicon_preview(self, obj):
        from django.utils.html import format_html

        if obj and obj.favicon:
            return format_html('<img src="{}" style="max-height: 32px;" alt="Favicon preview">', obj.favicon.url)
        return "(no favicon uploaded)"

    favicon_preview.short_description = "Ko'rinishi"


class BannerAdminForm(forms.ModelForm):
    image_upload = forms.ImageField(required=False, label="Rasm yuklash", help_text="JPEG, PNG yoki WebP. Saqlanganda avtomatik optimallashtiriladi (WebP + kichik nusxalar).")
    # Explicit field (not left to the model's own required=True) so a form
    # submission that omits it -- e.g. an older client/test -- still saves
    # the model's own default instead of failing validation.
    duration_seconds = forms.IntegerField(
        required=False, min_value=3, max_value=300, initial=45,
        label="Ko'rsatish davomiyligi (soniya)",
        help_text="Bosh sahifa slayderida banner keyingisiga o'tguncha necha soniya turadi (3–300).",
    )

    class Meta:
        model = orm.Banner
        fields = ["title", "subtitle", "cta_text", "title_ru", "subtitle_ru", "cta_text_ru", "title_en", "subtitle_en", "cta_text_en", "cta_url", "duration_seconds", "sort_order", "is_active", "image_upload"]  # image_storage_path/image_thumbnail_paths are internal implementation detail, never a real admin-editable field.

    def clean_duration_seconds(self):
        return self.cleaned_data.get("duration_seconds") or 45


def _media_url(path: str) -> str:
    if not path:
        return ""
    return path if path.startswith(("http://", "https://")) else f"{settings.MEDIA_URL}{path}"


def _require_post_with_change_permission(admin_obj, request):
    """Shared guard for the small JSON endpoints below: POST only, change permission required."""
    from django.http import JsonResponse

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    if not admin_obj.has_change_permission(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    return None


@admin.register(orm.Banner)
class BannerAdmin(admin.ModelAdmin):
    """Premium gallery changelist (templates/admin/platform/banner/): cards with live on/off toggles and drag-to-reorder, backed by the two JSON endpoints in get_urls()."""

    form = BannerAdminForm
    list_display = ("image_display", "title", "duration_seconds", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle")
    list_per_page = 48
    readonly_fields = ("id", "image_display", "created_at", "updated_at")
    actions = ("activate_selected", "deactivate_selected")

    def get_urls(self):
        from django.urls import path

        info = self.opts.app_label, self.opts.model_name
        return [
            path("<uuid:pk>/toggle/", self.admin_site.admin_view(self.toggle_view), name="%s_%s_toggle" % info),
            path("reorder/", self.admin_site.admin_view(self.reorder_view), name="%s_%s_reorder" % info),
        ] + super().get_urls()

    def toggle_view(self, request, pk):
        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        denied = _require_post_with_change_permission(self, request)
        if denied:
            return denied
        banner = get_object_or_404(orm.Banner, pk=pk)
        banner.is_active = not banner.is_active
        banner.save(update_fields=["is_active", "updated_at"])
        self.log_change(request, banner, [{"changed": {"fields": ["Is active"]}}])
        return JsonResponse({"ok": True, "is_active": banner.is_active, "active_count": orm.Banner.objects.filter(is_active=True).count()})

    def reorder_view(self, request):
        """Body: {"ids": [...]} in the new display order. Rewrites sort_order as 10, 20, 30... so a later manual edit can slot a banner in between."""
        import json

        from django.db import transaction
        from django.http import JsonResponse

        denied = _require_post_with_change_permission(self, request)
        if denied:
            return denied
        try:
            ids = [str(i) for i in json.loads(request.body or b"{}").get("ids", [])]
        except (ValueError, AttributeError):
            return JsonResponse({"ok": False, "error": "invalid body"}, status=400)
        banners = {str(b.pk): b for b in orm.Banner.objects.filter(pk__in=ids)}
        with transaction.atomic():
            for index, banner_id in enumerate(ids, start=1):
                banner = banners.get(banner_id)
                if banner and banner.sort_order != index * 10:
                    banner.sort_order = index * 10
                    banner.save(update_fields=["sort_order", "updated_at"])
                    self.log_change(request, banner, [{"changed": {"fields": ["Sort order"]}}])
        return JsonResponse({"ok": True})

    @admin.action(description=_("Show selected banners"))
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, ngettext("%(n)d banner is now shown.", "%(n)d banners are now shown.", updated) % {"n": updated})

    @admin.action(description=_("Hide selected banners"))
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, ngettext("%(n)d banner is now hidden.", "%(n)d banners are now hidden.", updated) % {"n": updated})

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        for banner in cl.result_list:  # iterating fills the queryset's result cache, so the template sees these attributes
            thumbs = banner.image_thumbnail_paths or {}
            banner.nz_image = _media_url(thumbs.get("medium") or thumbs.get("large") or banner.image_storage_path)
        return cl

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Count, Q, Sum

        agg = orm.Banner.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            no_image=Count("id", filter=Q(image_storage_path="")),
            cycle=Sum("duration_seconds", filter=Q(is_active=True)),
        )
        agg["hidden"] = agg["total"] - agg["active"]
        agg["cycle"] = agg["cycle"] or 0
        extra = {"nz_banner_stats": agg, "nz_filter_active": request.GET.get("is_active__exact", ""), "nz_can_change": self.has_change_permission(request)}
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra = {"nz_active_count": orm.Banner.objects.filter(is_active=True).count()}
        if object_id:
            banner = orm.Banner.objects.filter(pk=object_id).first()
            if banner:
                thumbs = banner.image_thumbnail_paths or {}
                extra["nz_banner_image"] = _media_url(thumbs.get("large") or banner.image_storage_path)
        return super().changeform_view(request, object_id, form_url, {**extra, **(extra_context or {})})

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        form = context["adminform"].form
        context["nz_banner_langs"] = [(code, label, form[f"title_{code}"], form[f"subtitle_{code}"], form[f"cta_text_{code}"]) for code, label in (("ru", "Русский"), ("en", "English"))]
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("image_upload")
        if uploaded:
            from apps.products.infrastructure.composition import build_media_pipeline
            from core.media import MediaType, MediaUploadRequest

            result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
            if result.is_failure:
                raise forms.ValidationError(result.errors[0].message)
            processed = result.value
            obj.image_storage_path = processed.storage_path
            obj.image_thumbnail_paths = processed.thumbnail_paths
        super().save_model(request, obj, form, change)

    def image_display(self, obj: orm.Banner) -> str:
        return _direct_thumbnail_html(obj.image_storage_path, obj.image_thumbnail_paths)

    image_display.short_description = ""


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


@admin.register(orm.ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    """Real, product-required capability: lets a store manager review and triage public Contact page submissions. Name/email/subject/message are the customer's own words -- never editable by an admin; only status is.

    Presented as an inbox (templates/admin/platform/contactmessage/): status tabs, bulk triage actions, and a reading view that marks a new message as read when it is opened."""

    list_display = ("name", "email", "subject", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "email", "subject", "message")
    list_per_page = 25
    readonly_fields = ("id", "name", "email", "subject", "message", "created_at", "updated_at")
    fields = ("name", "email", "subject", "message", "status", "created_at", "updated_at")
    actions = ("mark_read", "mark_replied", "mark_new")

    def has_add_permission(self, request):
        return False  # a contact message is only ever created by a real public form submission, never fabricated by an admin.

    def _set_status(self, request, queryset, status):
        from django.utils import timezone

        updated = queryset.exclude(status=status).update(status=status, updated_at=timezone.now())
        label = orm.ContactMessageStatus(status).label
        self.message_user(request, ngettext("%(n)d message marked as “%(status)s”.", "%(n)d messages marked as “%(status)s”.", updated) % {"n": updated, "status": label})

    @admin.action(description=_("Mark as read"))
    def mark_read(self, request, queryset):
        self._set_status(request, queryset, orm.ContactMessageStatus.READ)

    @admin.action(description=_("Mark as replied"))
    def mark_replied(self, request, queryset):
        self._set_status(request, queryset, orm.ContactMessageStatus.REPLIED)

    @admin.action(description=_("Mark as new"))
    def mark_new(self, request, queryset):
        self._set_status(request, queryset, orm.ContactMessageStatus.NEW)

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        for msg in cl.result_list:
            msg.nz_initials = _initials(msg.name)
        return cl

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Count

        counts = dict(orm.ContactMessage.objects.values_list("status").annotate(n=Count("id")))
        current = request.GET.get("status__exact", "")
        icons = {"new": ("fa-envelope", "#3b82f6"), "read": ("fa-envelope-open", "#f59e0b"), "replied": ("fa-reply", "#10b981")}
        tabs = [{"key": "", "label": _("All"), "n": sum(counts.values()), "icon": "fa-inbox", "color": "#64748b", "on": not current}]
        for value, label in orm.ContactMessageStatus.choices:
            icon, color = icons.get(value, ("fa-circle", "#64748b"))
            tabs.append({"key": value, "label": label, "n": counts.get(value, 0), "icon": icon, "color": color, "on": current == value})
        extra = {"nz_inbox_tabs": tabs, "nz_inbox_query": request.GET.get("q", ""), "nz_inbox_status": current}
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from urllib.parse import quote

        from django.urls import reverse
        from django.utils import timezone

        msg = orm.ContactMessage.objects.filter(pk=object_id).first()
        extra = {}
        if msg:
            # Opening a new message is reading it -- the inbox badge should reflect that without a manual step.
            if request.method == "GET" and msg.status == orm.ContactMessageStatus.NEW and self.has_change_permission(request, msg):
                orm.ContactMessage.objects.filter(pk=msg.pk).update(status=orm.ContactMessageStatus.READ, updated_at=timezone.now())
                extra["nz_auto_read"] = True

            def url_of(m):
                return reverse("admin:platform_contactmessage_change", args=[m.pk]) if m else ""

            newer = orm.ContactMessage.objects.filter(created_at__gt=msg.created_at).order_by("created_at").first()
            older = orm.ContactMessage.objects.filter(created_at__lt=msg.created_at).order_by("-created_at").first()
            subject = msg.subject or str(_("Your message to NutriZone"))
            extra.update({
                "nz_initials": _initials(msg.name),
                "nz_reply_href": f"mailto:{msg.email}?subject={quote('Re: ' + subject)}",
                "nz_newer_url": url_of(newer),
                "nz_older_url": url_of(older),
                "nz_history": [
                    {"url": url_of(m), "subject": m.subject, "status": m.status, "status_label": m.get_status_display(), "created_at": m.created_at}
                    for m in orm.ContactMessage.objects.filter(email__iexact=msg.email).exclude(pk=msg.pk).order_by("-created_at")[:5]
                ],
                "nz_status_choices": orm.ContactMessageStatus.choices,
            })
        return super().change_view(request, object_id, form_url, {**extra, **(extra_context or {})})


def _connect_branding_invalidation() -> None:
    from django.db.models.signals import post_save

    from apps.platform.infrastructure.branding import invalidate

    post_save.connect(invalidate, sender=orm.SiteSettings, dispatch_uid="platform.branding_invalidate")


_connect_branding_invalidation()


def _profile_first_auth_user_admin() -> None:
    """Opening your own staff account goes to the Profil page (?full=1 keeps Django's full permission form)."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    from datetime import timedelta

    from django.db.models import Count, Q
    from django.utils import timezone
    from django.utils.html import format_html

    from apps.platform.infrastructure import premium_admin as ui

    User = get_user_model()

    def _titled(base, title):
        class Titled(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.title = title

        return Titled

    class StaffUserAdmin(ui.PremiumListMixin, DjangoUserAdmin):
        """Dashboard staff accounts on the premium list -- superusers and long-unused logins stand out, since every one is a way in."""

        list_display = ("username", "date_joined", "last_login")
        list_filter = (("is_superuser", _titled(admin.BooleanFieldListFilter, "Superuser")), ("is_active", _titled(admin.BooleanFieldListFilter, "Faol")),
                       ("groups", _titled(admin.RelatedFieldListFilter, "Guruh")))
        ordering = ("-is_superuser", "-last_login")
        nz_icon, nz_tone, nz_title = "fa-user-shield", "#4f46e5", "Dashboard xodimlari"
        nz_subtitle = "Dashboardga kira oladigan akkauntlar. Ishlatilmayotgan va ortiqcha superuser akkauntlarini o'chirib qo'ying — har biri tizimga kirish yo'li."
        nz_columns = (("Xodim", ""), ("Rol", ""), ("Holat", ""), ("Qo'shilgan", ""), ("Oxirgi kirish", "r"))
        nz_grid = "minmax(260px,3fr) 150px 120px 130px 170px"
        nz_search = "Login, ism yoki email…"
        nz_empty = ("Xodim topilmadi", "")
        nz_sorts = (("Rol bo'yicha", ""), ("Yaqinda kirgan", "-3"), ("Yangi qo'shilgan", "-2"), ("Login", "1"))
        STALE_DAYS = 30

        def _stale_q(self):
            cutoff = timezone.now() - timedelta(days=self.STALE_DAYS)
            return Q(is_active=True) & (Q(last_login__isnull=True) | Q(last_login__lt=cutoff))

        def get_queryset(self, request):
            qs = super().get_queryset(request).annotate(nz_groups=Count("groups", distinct=True))
            if request.GET.get("nz") == "stale":
                qs = qs.filter(self._stale_q())
            return qs

        def get_changelist(self, request, **kwargs):
            from django.contrib.admin.views.main import ChangeList

            class _CL(ChangeList):
                def get_filters_params(self, params=None):  # `nz` is the KPI/tab shortcut, applied in get_queryset
                    out = super().get_filters_params(params)
                    out.pop("nz", None)
                    return out

            return _CL

        def nz_stats(self, request):
            week = timezone.now() - timedelta(days=7)
            agg = User.objects.aggregate(n=Count("id"), su=Count("id", filter=Q(is_superuser=True, is_active=True)), active=Count("id", filter=Q(is_active=True)),
                                         recent=Count("id", filter=Q(last_login__gte=week)), stale=Count("id", filter=self._stale_q()))
            base = reverse("admin:auth_user_changelist")
            return [ui.stat_card("Jami xodimlar", agg["n"], "#4f46e5", "fa-users", f"{agg['active']} faol", href=base),
                    ui.stat_card("Superuser", agg["su"], "#e11d48" if agg["su"] > 2 else "#9333ea", "fa-crown", "to'liq huquq — kam bo'lgani ma'qul", href=f"{base}?is_superuser__exact=1"),
                    ui.stat_card("7 kunda kirgan", agg["recent"], "#16a34a", "fa-right-to-bracket"),
                    ui.stat_card("Ishlatilmayapti", agg["stale"], "#f59e0b" if agg["stale"] else "#64748b", "fa-user-clock", f"{self.STALE_DAYS}+ kun kirmagan faol akkaunt", href=f"{base}?nz=stale")]

        def nz_tabs(self, request):
            return ui.tabs_for(request, "nz", [("", "Barchasi", User.objects.count()), ("stale", "Ishlatilmayapti", User.objects.filter(self._stale_q()).count())], {"stale": "#f59e0b"})

        def nz_hero_actions(self, request):
            return [{"label": "Mening profilim", "url": reverse("admin:nz_profile"), "icon": "fa-id-badge"},
                    {"label": "Yangi xodim", "url": reverse("admin:auth_user_add"), "icon": "fa-plus", "primary": True}]

        def nz_row(self, u):
            name = u.get_full_name()
            sub = " · ".join(x for x in (name if name else "", u.email) if x) or "ism kiritilmagan"
            if u.is_superuser:
                role = ui.chip("Superuser", "#9333ea", "fa-crown")
            elif u.is_staff:
                role = ui.chip(f"Xodim · {u.nz_groups} guruh", "#0891b2", "fa-user-tie")
            else:
                role = ui.chip("Dashboardga kirolmaydi", "#94a3b8", "fa-ban")
            stale = u.is_active and (u.last_login is None or u.last_login < timezone.now() - timedelta(days=self.STALE_DAYS))
            state = format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#f59e0b" if stale else ("#16a34a" if u.is_active else "#94a3b8"),
                                "Ishlatilmayapti" if stale else ("Faol" if u.is_active else "Bloklangan"))
            last = format_html("<b>{}</b><br><small class=\"nzi-muted\">{}</small>", ui.ago(u.last_login), ui.local(u.last_login)) if u.last_login else ui.muted("hech qachon")
            return [format_html('<span class="nzi-user"><span class="nzi-av" style="--c:{}">{}</span><span><b>{}</b><small>{}</small></span></span>',
                                ui.tone(f"{u.pk:06x}"), ui.initials(name or u.username), u.username, sub),
                    role, state, format_html("<small>{}</small>", ui.local(u.date_joined, "%d.%m.%Y")), last]

        def change_view(self, request, object_id, form_url="", extra_context=None):
            if str(object_id) == str(request.user.pk) and request.method == "GET" and "full" not in request.GET:
                return HttpResponseRedirect(reverse("admin:nz_profile"))
            return super().change_view(request, object_id, form_url, extra_context)

    if admin.site.is_registered(User):
        current = admin.site._registry[User].__class__
        if current is DjangoUserAdmin:
            admin.site.unregister(User)
            admin.site.register(User, StaffUserAdmin)


_profile_first_auth_user_admin()
