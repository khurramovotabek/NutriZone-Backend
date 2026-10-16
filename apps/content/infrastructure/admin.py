"""
apps/content/infrastructure/admin.py

Blog dashboard pages on the shared premium kit (PremiumListMixin / PremiumFormMixin): a posts desk with
status tabs, KPI cards and cover thumbnails, and a category list with post counts. Cover uploads reuse the
existing media pipeline rather than a second image-storage mechanism.
"""
from __future__ import annotations

from django import forms
from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.content.infrastructure import models as orm
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.products.infrastructure.catalog_form_ui import media_url, storefront_url

STATUS_COLOR = {orm.BlogPostStatus.PUBLISHED: "#16a34a", orm.BlogPostStatus.DRAFT: "#f59e0b"}
STATUS_LABEL = {orm.BlogPostStatus.PUBLISHED: "Chop etilgan", orm.BlogPostStatus.DRAFT: "Qoralama"}


def _titled(base, title):
    class Titled(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = title

    return Titled


def _cover(post: orm.BlogPost) -> str:
    url = media_url(post.cover_image_storage_path, post.cover_image_thumbnail_paths, "small")
    if not url:
        return mark_safe('<span class="nz-thumb nz-thumb-empty"><i class="fas fa-image" aria-hidden="true"></i></span>')
    return format_html('<img src="{}" class="nz-thumb" alt="" loading="lazy">', url)


def _status_pill(status: str) -> str:
    return format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_COLOR.get(status, "#94a3b8"), STATUS_LABEL.get(status, status))


@admin.register(orm.BlogCategory)
class BlogCategoryAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    list_display = ("name", "sort_order")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")
    list_per_page = 25
    fields = ("name", "slug", "sort_order")

    nz_icon, nz_tone, nz_title = "fa-folder-tree", "#0891b2", "Blog bo'limlari"
    nz_subtitle = "Maqolalarni mavzular bo'yicha guruhlang. Tartib raqami saytdagi ketma-ketlikni belgilaydi."
    nz_columns = (("Bo'lim", ""), ("Tartib", "r"), ("Maqolalar", "r"))
    nz_grid = "minmax(260px,3fr) 90px 120px"
    nz_search = "Bo'lim nomi…"
    nz_empty = ("Bo'lim yo'q", "«Yangi bo'lim» bilan qo'shing.")
    nz_sorts = (("Tartib bo'yicha", ""), ("Nomi", "1"))
    hero_icon, hero_tone, hero_noun = "fa-folder-tree", "#0891b2", "bo'lim"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            nz_posts=Count("posts", distinct=True), nz_live=Count("posts", filter=Q(posts__status=orm.BlogPostStatus.PUBLISHED), distinct=True)
        )

    def nz_hero_actions(self, request):
        return [{"label": "Maqolalar", "url": reverse("admin:content_blogpost_changelist"), "icon": "fa-newspaper"},
                {"label": "Yangi bo'lim", "url": reverse("admin:content_blogcategory_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, c):
        return [format_html('<span class="nzi-user"><span class="nzi-av" style="--c:{}"><i class="fas fa-folder" aria-hidden="true"></i></span><span><b>{}</b><small>/{}</small></span></span>', "#0891b2", c.name, c.slug),
                format_html("<b>{}</b>", c.sort_order),
                format_html("<b>{}</b> <small class=\"nzi-muted\">· {} chop etilgan</small>", c.nz_posts, c.nz_live)]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Bo'lim nomini yozing — slug avtomatik to'ldiriladi"}
        posts = obj.posts.aggregate(n=Count("id"), live=Count("id", filter=Q(status=orm.BlogPostStatus.PUBLISHED)), views=Sum("view_count"))
        return {"title": obj.name, "subtitle": f"/{obj.slug}",
                "links": [{"label": "Maqolalari", "url": reverse("admin:content_blogpost_changelist") + f"?category__id__exact={obj.pk}", "icon": "fa-newspaper", "primary": True}],
                "stats": [hero_stat("Maqolalar", posts["n"], "#0891b2", f"{posts['live']} chop etilgan", "fa-newspaper"),
                          hero_stat("Ko'rishlar", posts["views"] or 0, "#4f46e5", "jami", "fa-eye")]}


class BlogPostAdminForm(forms.ModelForm):
    cover_image_upload = forms.ImageField(required=False, label="Muqova rasmi", help_text="JPEG, PNG yoki WebP. Kichik o'lchamlar avtomatik tayyorlanadi.")

    class Meta:
        model = orm.BlogPost
        fields = ["category", "title", "slug", "excerpt", "body", "status", "cover_image_upload"]  # cover_image_storage_path/cover_image_thumbnail_paths are internal implementation detail, never a real admin-editable field.
        labels = {"category": "Bo'lim", "title": "Sarlavha", "slug": "Slug (URL manzil)", "excerpt": "Qisqa matn", "body": "Matn", "status": "Holat"}
        help_texts = {"slug": "Sarlavhadan avtomatik to'ldiriladi: /blog/maqola-nomi", "excerpt": "Kartochka va qidiruv natijalarida ko'rinadi — 1–2 jumla, 300 belgigacha.",
                      "body": "Bo'sh qator — yangi blok. Nuqtasiz qisqa satr — sarlavha; «•» yoki «-» bilan boshlangan satrlar — ro'yxat; «Muhim:» bilan boshlangan blok — ajratilgan eslatma."}
        widgets = {"title": forms.TextInput(attrs={"class": "vTextField", "placeholder": "Masalan: Kreatin qanday ichiladi?", "autocomplete": "off"}),
                   "excerpt": forms.Textarea(attrs={"rows": 2, "placeholder": "Maqolaning qisqacha mazmuni…"}),
                   "body": forms.Textarea(attrs={"rows": 18, "placeholder": "Maqola matni…", "spellcheck": "true"})}


@admin.register(orm.BlogPost)
class BlogPostAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    excel_title = "Blog maqolalari"
    excel_select_related = ("category",)
    excel_columns = [Col("Sarlavha", "title", 40), Col("Kategoriya", lambda p: str(p.category) if p.category else "", 18), Col("Holat", "status", 12),
                     Col("Chop etilgan", "published_at", 17), Col("Ko'rishlar", "view_count", 11, number=True), Col("Slug", "slug", 30)]

    form = BlogPostAdminForm
    list_display = ("title", "published_at", "view_count")
    list_filter = (("category", _titled(admin.RelatedFieldListFilter, "Bo'lim")), ("published_at", _titled(admin.DateFieldListFilter, "Chop etilgan sana")))
    search_fields = ("title", "excerpt", "slug")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-published_at", "-created_at")
    list_per_page = 25
    readonly_fields = ("published_at", "view_count", "created_at", "updated_at")
    fieldsets = (
        ("Maqola", {"fields": ("title", "slug", "category", "excerpt", "body")}),
        ("Muqova va holat", {"fields": ("cover_image_upload", "status")}),
        ("Statistika", {"fields": ("published_at", "view_count", "created_at", "updated_at")}),
    )
    actions = ["publish_now", "unpublish"]

    nz_icon, nz_tone, nz_title = "fa-newspaper", "#4f46e5", "Blog maqolalari"
    nz_subtitle = "Sport ovqatlanishi bo'yicha maqolalar — foydali kontent saytga qidiruvdan mijoz olib keladi."
    nz_columns = (("Maqola", ""), ("Bo'lim", ""), ("Holat", ""), ("Chop etilgan", ""), ("Ko'rishlar", "r"))
    nz_grid = "minmax(320px,3fr) minmax(120px,1fr) 130px 150px 110px"
    nz_search = "Sarlavha yoki qisqa matn…"
    nz_empty = ("Maqola topilmadi", "Filtrlarni o'zgartiring yoki «Yangi maqola» bilan qo'shing.")
    nz_sorts = (("Eng yangi", ""), ("Ko'p o'qilgan", "-3"), ("Sarlavha", "1"))
    hero_icon, hero_tone, hero_noun = "fa-newspaper", "#4f46e5", "maqola"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category")

    def lookup_allowed(self, lookup, value, request=None):
        return lookup == "status__exact" or super().lookup_allowed(lookup, value, request)

    def nz_stats(self, request):
        agg = orm.BlogPost.objects.aggregate(n=Count("id"), live=Count("id", filter=Q(status=orm.BlogPostStatus.PUBLISHED)),
                                             draft=Count("id", filter=Q(status=orm.BlogPostStatus.DRAFT)), views=Sum("view_count"))
        top = orm.BlogPost.objects.filter(status=orm.BlogPostStatus.PUBLISHED).order_by("-view_count").first()
        base = reverse("admin:content_blogpost_changelist")
        return [ui.stat_card("Jami maqolalar", agg["n"], "#4f46e5", "fa-newspaper", href=base),
                ui.stat_card("Chop etilgan", agg["live"], "#16a34a", "fa-circle-check", href=f"{base}?status__exact=published"),
                ui.stat_card("Qoralama", agg["draft"], "#f59e0b", "fa-pen-ruler", "tugatilishi kerak" if agg["draft"] else "", href=f"{base}?status__exact=draft"),
                ui.stat_card("Ko'rishlar", agg["views"] or 0, "#0891b2", "fa-eye", f"eng ko'p: {top.title[:28]}" if top and top.view_count else "")]

    def nz_tabs(self, request):
        counts = dict(orm.BlogPost.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Barchasi", sum(counts.values()))] + [(v, STATUS_LABEL[v], counts.get(v, 0)) for v in orm.BlogPostStatus.values],
                           {str(k): c for k, c in STATUS_COLOR.items()})

    def nz_hero_actions(self, request):
        return [{"label": "Bo'limlar", "url": reverse("admin:content_blogcategory_changelist"), "icon": "fa-folder-tree"},
                {"label": "Yangi maqola", "url": reverse("admin:content_blogpost_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, p):
        excerpt = p.excerpt if len(p.excerpt) <= 110 else p.excerpt[:107].rstrip() + "…"
        return [format_html('<span class="nzi-user">{}<span><b>{}</b><small>{}</small></span></span>', _cover(p), p.title, excerpt or f"/{p.slug}"),
                ui.chip(p.category.name, "#0891b2", "fa-folder") if p.category else ui.muted(),
                _status_pill(p.status),
                format_html("<small>{}</small>", ui.local(p.published_at, "%d.%m.%Y")) if p.published_at else ui.muted(),
                format_html("<b>{}</b>", p.view_count)]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Sarlavha, qisqa matn va muqova — kartochkada aynan shular ko'rinadi"}
        site = storefront_url(f"/blog/{obj.slug}") if obj.status == orm.BlogPostStatus.PUBLISHED else ""
        words = len(obj.body.split())
        return {"title": obj.title, "subtitle": obj.excerpt[:160], "image": media_url(obj.cover_image_storage_path, obj.cover_image_thumbnail_paths),
                "chips": [_status_pill(obj.status)] + ([ui.chip(obj.category.name, "#0891b2", "fa-folder")] if obj.category else []),
                "links": [{"label": "Saytda ko'rish", "url": site, "icon": "fa-arrow-up-right-from-square", "external": True, "primary": True}] if site else [],
                "stats": [hero_stat("Ko'rishlar", obj.view_count, "#0891b2", "marta o'qilgan", "fa-eye"),
                          hero_stat("Hajmi", words, "#4f46e5", f"so'z · ~{max(1, round(words / 200))} daqiqa", "fa-align-left"),
                          hero_stat("Chop etilgan", ui.local(obj.published_at, "%d.%m.%Y") if obj.published_at else "—", "#16a34a", ui.ago(obj.published_at) if obj.published_at else "hali yo'q", "fa-calendar")]}

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("cover_image_upload")
        if uploaded:
            from apps.products.infrastructure.composition import build_media_pipeline
            from core.media import MediaType, MediaUploadRequest

            result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
            if result.is_failure:
                raise forms.ValidationError(result.errors[0].message)
            processed = result.value
            obj.cover_image_storage_path = processed.storage_path
            obj.cover_image_thumbnail_paths = processed.thumbnail_paths
        if obj.status == orm.BlogPostStatus.PUBLISHED and obj.published_at is None:
            obj.published_at = django_timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description="Hozir chop etish")
    def publish_now(self, request, queryset):
        updated = 0
        for post in queryset:
            if post.status != orm.BlogPostStatus.PUBLISHED:
                post.status = orm.BlogPostStatus.PUBLISHED
                post.published_at = post.published_at or django_timezone.now()
                post.save(update_fields=["status", "published_at"])
                updated += 1
        self.message_user(request, f"{updated} ta maqola chop etildi.")

    @admin.action(description="Qoralamaga qaytarish (saytdan yashirish)")
    def unpublish(self, request, queryset):
        self.message_user(request, f"{queryset.filter(status=orm.BlogPostStatus.PUBLISHED).update(status=orm.BlogPostStatus.DRAFT)} ta maqola yashirildi.")
