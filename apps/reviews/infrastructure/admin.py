"""
Dashboard → Sharhlar: the moderation desk for customer reviews and their photos / videos.

Every status change goes through the reviews Application Services (Approve + Publish, Reject with a reason, Hide
with a reason) -- loaded through the repository, checked by the aggregate's lifecycle, staged as an event and
audited. Review text is the customer's own words: staff never edit it here and never create reviews by hand.

`product_id` / `customer_id` are plain cross-module UUIDs (no FK, see models.py), so names / images are batch-loaded
once per page. Lists use the shared premium layout; the media page is a gallery.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.reviews.infrastructure import models as orm
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from common.exceptions import DomainException
from common.utils import DEFAULT_LOCALE

STATUS = {  # status -> (label, colour, icon)
    "draft": ("Qoralama", "#94a3b8", "fa-pen"), "pending_moderation": ("Moderatsiya kutmoqda", "#d97706", "fa-hourglass-half"),
    "approved": ("Tasdiqlangan, saytda emas", "#0ea5e9", "fa-circle-check"), "published": ("Saytda", "#16a34a", "fa-globe"),
    "rejected": ("Rad etilgan", "#dc2626", "fa-ban"), "hidden": ("Yashirilgan", "#64748b", "fa-eye-slash"), "withdrawn": ("Mijoz qaytarib olgan", "#94a3b8", "fa-rotate-left"),
}
REJECT = {"spam": "Spam / reklama", "offensive_content": "Haqoratli so'zlar", "off_topic": "Mahsulotga aloqasiz", "policy_violation": "Qoidaga zid", "other": "Boshqa sabab"}
HIDE = {"customer_complaint": "Shikoyat tushdi", "policy_violation": "Qoidaga zid", "legal_request": "Huquqiy talab", "other": "Boshqa sabab"}


def _media_url(path: str) -> str:
    return path if not path or path.startswith(("http://", "https://")) else f"{settings.MEDIA_URL}{path}"


def _products(ids) -> dict:
    """product_id -> {"name", "image", "url"} (one query for names, one for images)."""
    from apps.products.infrastructure.models import Product, ProductMedia, ProductTranslation

    ids = list({i for i in ids if i})
    out: dict = {pid: {"name": "", "image": "", "url": reverse("admin:products_product_change", args=[pid])} for pid in Product._base_manager.filter(id__in=ids).values_list("id", flat=True)}
    for row in ProductTranslation.objects.filter(product_id__in=out).values("product_id", "locale_code", "name"):
        if row["locale_code"] == DEFAULT_LOCALE or not out[row["product_id"]]["name"]:
            out[row["product_id"]]["name"] = row["name"]
    for m in ProductMedia.objects.filter(product_id__in=out).order_by("product_id", "sort_order").values("product_id", "storage_path", "thumbnail_paths"):
        if not out[m["product_id"]]["image"]:
            out[m["product_id"]]["image"] = _media_url((m["thumbnail_paths"] or {}).get("small") or m["storage_path"])
    return out


def _customers(ids) -> dict:
    from django.db.models import Prefetch

    from apps.identity.infrastructure.models import User, UserAvatarAsset

    return {u.id: u for u in User._base_manager.filter(id__in=list({i for i in ids if i})).prefetch_related(Prefetch("avatar_assets", queryset=UserAvatarAsset.objects.order_by("-created_at")))}


def stars(rating: int) -> str:
    return format_html('<span class="nzr-stars" aria-label="{} / 5">{}<span class="off">{}</span></span>', rating, "★" * rating, "★" * (5 - rating))


def status_pill(status: str) -> str:
    label, color, icon = STATUS.get(status, (status, "#64748b", "fa-circle"))
    return format_html('<span class="nzi-pill" style="--t:{}">{}</span>', color, label)


def product_cell(p: dict | None) -> str:
    if not p:
        return format_html('<span class="nzr-prod"><span class="ph"><i class="fas fa-box" aria-hidden="true"></i></span><span><b>{}</b></span></span>', "O'chirilgan mahsulot")
    img = format_html('<img src="{}" alt="">', p["image"]) if p["image"] else mark_safe('<span class="ph"><i class="fas fa-box" aria-hidden="true"></i></span>')
    return format_html('<span class="nzr-prod">{}<span><b>{}</b></span></span>', img, p["name"] or "Nomsiz mahsulot")


def media_thumb(m) -> str:
    if m.media_type == "video":
        return format_html('<video src="{}#t=0.5" preload="metadata" muted playsinline></video><span class="nzr-play"><i class="fas fa-play" aria-hidden="true"></i></span>', _media_url(m.url))
    return format_html('<img src="{}" alt="Sharh rasmi">', _media_url(m.url))


def _btn(url: str, label: str, icon: str, kind: str = "", confirm: str = "") -> str:
    return format_html('<button type="submit" class="nzi-act {}" formaction="{}" formnovalidate data-nzi-confirm="{}"><i class="fas {}" aria-hidden="true"></i> {}</button>', kind, url, confirm, icon, label)


def _titled(base, title):
    return type(f"{base.__name__}_{title}", (base,), {"__init__": lambda self, *a, **k: (base.__init__(self, *a, **k), setattr(self, "title", title))[0]})


# ---------------------------------------------------------------- moderation (services only)


def moderate(review_id, action: str, reason: str = "", actor=None) -> None:
    """approve (approve + publish), publish, reject <reason>, hide <reason> -- each through its Application Service."""
    from apps.reviews.infrastructure import composition as c

    now = timezone.now()
    review = orm.ReviewModel.objects.get(pk=review_id)
    if action == "approve":
        if review.status == "pending_moderation":
            c.build_approve_review(actor).execute(review.pk, now)
        c.build_publish_review(actor).execute(review.pk, now)
    elif action == "publish":
        c.build_publish_review(actor).execute(review.pk, now)
    elif action == "reject":
        c.build_reject_review(actor).execute(review.pk, reason if reason in REJECT else "other", now)
    elif action == "hide":
        c.build_hide_review(actor).execute(review.pk, reason if reason in HIDE else "other")
    else:
        raise ValueError(action)


class MediaFilter(admin.SimpleListFilter):
    title = "Rasm / video"
    parameter_name = "media"

    def lookups(self, request, model_admin):
        return [("1", "Rasmli / videoli"), ("0", "Faqat matn")]

    def queryset(self, request, queryset):
        has = Exists(orm.ReviewMediaModel.objects.filter(review=OuterRef("pk")))
        return queryset.filter(has) if self.value() == "1" else queryset.filter(~has) if self.value() == "0" else queryset


class RatingFilter(admin.SimpleListFilter):
    title = "Baho"
    parameter_name = "stars"

    def lookups(self, request, model_admin):
        return [("5", "★★★★★"), ("4", "★★★★"), ("3", "★★★"), ("low", "1–2 ★ (salbiy)")]

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(rating__lte=2)
        return queryset.filter(rating=int(self.value())) if self.value() in ("3", "4", "5") else queryset


@admin.register(orm.ReviewModel)
class ReviewAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    excel_title = "Sharhlar"
    excel_columns = [
        Col("Sana", "created_at", 17), Col("Mahsulot", lambda r: r.x_product, 34), Col("Mijoz", lambda r: r.x_customer[0], 22),
        Col("Telefon", lambda r: r.x_customer[1], 16), Col("Baho", "rating", 7, number=True), Col("Sarlavha", "title", 26), Col("Matn", "body", 60),
        Col("Holat", "status", 12), Col("Tasdiqlangan xarid", "verified_purchase", 10), Col("Nashr", "published_at", 17),
    ]

    def excel_prepare(self, objs):
        from apps.products.infrastructure.models import ProductTranslation

        names: dict = {}
        for t in ProductTranslation.objects.filter(product_id__in={r.product_id for r in objs}).values("product_id", "locale_code", "name"):
            if t["locale_code"] == "uz" or t["product_id"] not in names:
                names[t["product_id"]] = t["name"]
        who = xl.people(r.customer_id for r in objs)
        for r in objs:
            r.x_product, r.x_customer = names.get(r.product_id, ""), who.get(r.customer_id, ("", ""))

    """Sharhlar: the moderation queue -- approve & publish, reject or hide with a reason; the card shows the full text, media and timeline."""

    list_display = ("rating", "created_at")
    list_filter = (RatingFilter, MediaFilter, ("verified_purchase", _titled(admin.BooleanFieldListFilter, "Tasdiqlangan xarid")))
    search_fields = ("title", "body")
    ordering = ("-created_at",)
    list_per_page = 30
    actions = ["approve_selected", "reject_spam", "reject_offensive", "reject_off_topic", "hide_complaint"]
    readonly_fields = ("review_panel", "media_panel", "moderation_panel")
    fieldsets = (
        ("Sharh", {"classes": ("nzi-panel",), "fields": ("review_panel",)}),
        ("Rasm va videolar", {"classes": ("nzi-panel",), "fields": ("media_panel",)}),
        ("Moderatsiya", {"classes": ("nzi-panel",), "fields": ("moderation_panel",)}),
    )

    nz_icon, nz_tone, nz_title = "fa-star", "#eab308", "Sharhlar"
    nz_subtitle = "Mijozlar sharhlari: tekshiring, saytga chiqaring yoki sabab ko'rsatib rad eting. Faqat «Saytda» holatidagi sharhlar mahsulot sahifasida va bosh sahifada ko'rinadi."
    nz_columns = (("Mahsulot", ""), ("Mijoz", ""), ("Baho", ""), ("Sharh", ""), ("Media", ""), ("Sana", ""), ("Holat", "r"))
    nz_grid = "minmax(190px,1.4fr) minmax(170px,1.2fr) 100px minmax(240px,2.4fr) 120px 100px 170px"
    nz_search = "Sharh matni yoki sarlavha…"
    nz_empty = ("Hali sharh yo'q", "Mijoz xarid qilgan mahsulotiga sharh qoldirganda shu yerda paydo bo'ladi.")
    nz_sorts = (("Yangilari", ""), ("Eskilari", "2"), ("Past baho", "1"), ("Yuqori baho", "-1"))
    nz_css = ("admin/css/nutrizone-reviews.css",)
    hero_icon, hero_tone = "fa-star", "#eab308"

    def has_add_permission(self, request) -> bool:
        return False  # reviews are written by customers who bought the product

    def has_delete_permission(self, request, obj=None) -> bool:
        return False  # hide instead -- the history stays

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("media_items")

    # ---------------------------------------------------------------- list

    def nz_stats(self, request):
        k = orm.ReviewModel.objects.aggregate(
            pending=Count("id", filter=Q(status="pending_moderation")), approved=Count("id", filter=Q(status="approved")),
            published=Count("id", filter=Q(status="published")), avg=Avg("rating", filter=Q(status="published")), low=Count("id", filter=Q(rating__lte=2)),
        )
        with_media = orm.ReviewModel.objects.filter(Exists(orm.ReviewMediaModel.objects.filter(review=OuterRef("pk")))).count()
        return [
            ui.stat_card("Moderatsiya kutmoqda", k["pending"], "#d97706" if k["pending"] else "#16a34a", "fa-hourglass-half", "tekshirish kerak" if k["pending"] else "navbat bo'sh", "?status__exact=pending_moderation"),
            ui.stat_card("Tasdiqlangan, saytda emas", k["approved"], "#0ea5e9" if k["approved"] else "#64748b", "fa-circle-exclamation", "«Saytga chiqarish»ni bosing" if k["approved"] else "hammasi chiqarilgan", "?status__exact=approved"),
            ui.stat_card("Saytda", k["published"], "#16a34a", "fa-globe", f"o'rtacha {k['avg']:.1f} ★" if k["avg"] else "hali yo'q", "?status__exact=published"),
            ui.stat_card("Rasm / videoli", with_media, "#9333ea", "fa-images", "eng ishonchli sharhlar", "?media=1"),
            ui.stat_card("Salbiy (1–2 ★)", k["low"], "#dc2626" if k["low"] else "#64748b", "fa-face-frown", "mijoz bilan bog'laning", "?stars=low"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.ReviewModel.objects.values_list("status").annotate(n=Count("id")))
        order = ["pending_moderation", "approved", "published", "rejected", "hidden", "draft", "withdrawn"]
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values()))] + [(s, STATUS[s][0].split(",")[0], counts[s]) for s in order if counts.get(s)],
                           {s: v[1] for s, v in STATUS.items()})

    def nz_hero_actions(self, request):
        return [{"label": "Rasm va videolar", "url": reverse("admin:reviews_reviewmediamodel_changelist"), "icon": "fa-images"}]

    def nz_prepare(self, request, objs):
        self._p, self._c = _products([r.product_id for r in objs]), _customers([r.customer_id for r in objs])

    def nz_row(self, r):
        media = list(r.media_items.all())
        thumbs = format_html_join("", '<span class="nzr-mini">{}</span>', ((media_thumb(m),) for m in media[:3]))
        title = format_html("<b>{}</b>", r.title) if r.title else ""
        body = r.body if len(r.body) <= 140 else r.body[:137].rstrip() + "…"
        verified = format_html('<small class="nzr-verified"><i class="fas fa-circle-check" aria-hidden="true"></i> {}</small>', "tasdiqlangan xarid") if r.verified_purchase else ""
        return [
            product_cell(self._p.get(r.product_id)), ui.user_cell(self._c.get(r.customer_id)), stars(r.rating),
            format_html('<span class="nzr-text">{}<span>{}</span></span>', title, body),
            format_html('<span class="nzr-thumbs">{}{}</span>', thumbs, format_html("<small>+{}</small>", len(media) - 3) if len(media) > 3 else "") if media else ui.muted(),
            format_html('<span title="{}">{}</span><small>{}</small>', ui.local(r.created_at), ui.local(r.created_at, "%d.%m.%Y"), ui.ago(r.submitted_at or r.created_at)),
            format_html("{}{}", status_pill(r.status), verified),
        ]

    # ---------------------------------------------------------------- bulk actions

    def _bulk(self, request, queryset, action, reason=""):
        done, skipped = 0, 0
        for r in queryset:
            try:
                moderate(r.pk, action, reason)
                done += 1
            except DomainException:
                skipped += 1
        msg = f"{done} ta sharh yangilandi."
        if skipped:
            msg += f" {skipped} tasi bu holatda o'zgartirib bo'lmaydi (masalan, qoralama yoki allaqachon yashirilgan)."
        self.message_user(request, msg, messages.SUCCESS if done else messages.WARNING)

    @admin.action(description="Tasdiqlash va saytga chiqarish", permissions=["change"])
    def approve_selected(self, request, queryset):
        self._bulk(request, queryset, "approve")

    @admin.action(description="Rad etish: spam", permissions=["change"])
    def reject_spam(self, request, queryset):
        self._bulk(request, queryset, "reject", "spam")

    @admin.action(description="Rad etish: haqoratli", permissions=["change"])
    def reject_offensive(self, request, queryset):
        self._bulk(request, queryset, "reject", "offensive_content")

    @admin.action(description="Rad etish: aloqasiz", permissions=["change"])
    def reject_off_topic(self, request, queryset):
        self._bulk(request, queryset, "reject", "off_topic")

    @admin.action(description="Saytdan yashirish (shikoyat)", permissions=["change"])
    def hide_complaint(self, request, queryset):
        self._bulk(request, queryset, "hide", "customer_complaint")

    # ---------------------------------------------------------------- the review card

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra = {"show_save": False, "show_save_and_continue": False, "show_save_and_add_another": False, "show_delete": False}
        return super().changeform_view(request, object_id, form_url, {**(extra_context or {}), **extra})

    def form_hero(self, request, obj):
        p = _products([obj.product_id]).get(obj.product_id)
        c = _customers([obj.customer_id]).get(obj.customer_id)
        label, color, icon = STATUS.get(obj.status, (obj.status, "#64748b", "fa-circle"))
        agg = orm.ReviewModel.objects.filter(product_id=obj.product_id, status="published").aggregate(n=Count("id"), avg=Avg("rating"))
        mine = orm.ReviewModel.objects.filter(customer_id=obj.customer_id).count()
        chips = [status_pill(obj.status), stars(obj.rating)]
        if obj.verified_purchase:
            chips.append(ui.chip("Tasdiqlangan xarid", "#16a34a", "fa-circle-check"))
        return {
            "title": obj.title or (p["name"] if p else "Sharh"), "subtitle": f"{p['name'] if p else 'O‘chirilgan mahsulot'} · {(c.full_name or c.phone_number) if c else 'o‘chirilgan mijoz'}",
            "image": p["image"] if p else "", "icon": "fa-star", "tone": color, "chips": chips,
            "stats": [
                hero_stat("Baho", f"{obj.rating} / 5", "#eab308", "mijoz bahosi", "fa-star"),
                hero_stat("Mahsulot reytingi", f"{agg['avg']:.1f} ★" if agg["avg"] else "—", "#16a34a", f"{agg['n']} ta saytdagi sharh", "fa-chart-simple"),
                hero_stat("Media", len(obj.media_items.all()), "#9333ea", "rasm / video", "fa-images"),
                hero_stat("Mijoz sharhlari", mine, "#2563eb", "jami yozgan", "fa-comments"),
            ],
            "links": [l for l in (
                {"label": "Mahsulot", "url": p["url"], "icon": "fa-box"} if p else None,
                {"label": "Mijoz", "url": reverse("admin:identity_user_change", args=[c.pk]), "icon": "fa-user"} if c else None,
            ) if l],
        }

    @admin.display(description="")
    def review_panel(self, obj):
        c = _customers([obj.customer_id]).get(obj.customer_id)
        return format_html(
            '<div class="nzr-review"><header>{}{}</header>{}<blockquote>{}</blockquote></div>',
            ui.user_cell(c), stars(obj.rating), format_html("<h4>{}</h4>", obj.title) if obj.title else "", obj.body,
        )

    @admin.display(description="")
    def media_panel(self, obj):
        media = list(obj.media_items.all())
        if not media:
            return format_html('<p class="nzi-none">{}</p>', "Mijoz rasm yoki video qo'shmagan.")
        return format_html('<div class="nzr-gallery">{}</div>', format_html_join("", '<a href="{}" target="_blank" rel="noopener" class="nzr-shot">{}<small>{}</small></a>', (
            (_media_url(m.url), media_thumb(m), ui.local(m.uploaded_at)) for m in media)))

    @admin.display(description="")
    def moderation_panel(self, obj):
        def url(action):
            return reverse("admin:reviews_review_moderate", args=[obj.pk, action])

        reasons = {"reject": REJECT, "hide": HIDE}
        buttons = []
        if obj.status in ("pending_moderation", "approved"):
            buttons.append(_btn(url("approve"), "Tasdiqlash va saytga chiqarish", "fa-globe", "primary"))
        if obj.status == "pending_moderation":
            buttons.append(format_html('<span class="nzr-reason"><select name="nz_reason_reject" aria-label="Rad etish sababi">{}</select>{}</span>',
                                       format_html_join("", '<option value="{}">{}</option>', reasons["reject"].items()), _btn(url("reject"), "Rad etish", "fa-ban", "danger")))
        if obj.status == "published":
            buttons.append(format_html('<span class="nzr-reason"><select name="nz_reason_hide" aria-label="Yashirish sababi">{}</select>{}</span>',
                                       format_html_join("", '<option value="{}">{}</option>', reasons["hide"].items()), _btn(url("hide"), "Saytdan yashirish", "fa-eye-slash", "danger", "Sharh saytdan olib tashlanadi. Davom etilsinmi?")))
        timeline = [(ui.local(obj.created_at), "Yozildi", "#94a3b8"), (ui.local(obj.submitted_at), "Moderatsiyaga yuborildi", "#d97706") if obj.submitted_at else None,
                    (ui.local(obj.moderated_at), "Tekshirildi", "#0ea5e9") if obj.moderated_at else None, (ui.local(obj.published_at), "Saytga chiqdi" if obj.status == "published" else "Oldin saytda bo'lgan (o'zgartirilgach qayta tekshiruvga tushdi)", "#16a34a" if obj.status == "published" else "#94a3b8") if obj.published_at else None]
        steps = format_html_join("", '<li style="--t:{}"><b>{}</b><small>{}</small></li>', ((t[2], t[1], t[0]) for t in timeline if t))
        hint = {"draft": "Mijoz sharhni hali yubormagan — moderatsiya qilib bo'lmaydi.", "rejected": "Rad etilgan sharh saytda ko'rinmaydi.", "hidden": "Yashirilgan sharh saytda ko'rinmaydi.",
                "withdrawn": "Mijoz sharhini o'zi qaytarib olgan."}.get(obj.status, "")
        return format_html('<div class="nzi-panel-body"><ol class="nzr-timeline">{}</ol>{}{}</div>', steps,
                           format_html('<div class="nzi-actions">{}</div>', format_html_join("", "{}", ((b,) for b in buttons))) if buttons else "",
                           format_html('<p class="nzi-help">{}</p>', hint) if hint else "")

    def get_urls(self):
        return [path("<uuid:pk>/nz/<str:action>/", self.admin_site.admin_view(self.moderate_view), name="reviews_review_moderate"), *super().get_urls()]

    def moderate_view(self, request, pk, action):
        if request.method != "POST" or not self.has_change_permission(request) or action not in ("approve", "publish", "reject", "hide"):
            raise PermissionDenied
        review = get_object_or_404(orm.ReviewModel, pk=pk)
        reason = request.POST.get(f"nz_reason_{action}", "")
        try:
            moderate(review.pk, action, reason)
        except DomainException as exc:
            messages.error(request, f"Bajarib bo'lmadi: {exc}")
        else:
            messages.success(request, {"approve": "Sharh saytga chiqarildi.", "publish": "Sharh saytga chiqarildi.", "reject": "Sharh rad etildi.", "hide": "Sharh saytdan yashirildi."}[action])
        return HttpResponseRedirect(reverse("admin:reviews_reviewmodel_change", args=[review.pk]))


@admin.register(orm.ReviewMediaModel)
class ReviewMediaAdmin(PremiumListMixin, admin.ModelAdmin):
    """Rasm va videolar: every photo / video customers attached, as a gallery; a card opens its review for moderation."""

    list_display = ("uploaded_at",)
    list_filter = (("media_type", _titled(admin.ChoicesFieldListFilter, "Turi")),)
    list_select_related = ("review",)
    ordering = ("-uploaded_at",)
    list_per_page = 48
    search_fields = ("review__title", "review__body")

    nz_icon, nz_tone, nz_title = "fa-images", "#9333ea", "Sharh rasmlari va videolari"
    nz_subtitle = "Mijozlar sharhga biriktirgan rasm va videolar. Rasmni bosing — sharhni ochib, saytga chiqarish yoki yashirish mumkin."
    nz_layout = "gallery"
    nz_search = "Sharh matni bo'yicha…"
    nz_empty = ("Hali rasm yoki video yo'q", "Mijoz sharhga rasm qo'shganda shu yerda paydo bo'ladi.")
    nz_columns = (("Media", ""),)
    nz_css = ("admin/css/nutrizone-reviews.css",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def nz_stats(self, request):
        k = orm.ReviewMediaModel.objects.aggregate(n=Count("id"), img=Count("id", filter=Q(media_type="image")), vid=Count("id", filter=Q(media_type="video")),
                                                   live=Count("id", filter=Q(review__status="published")))
        return [
            ui.stat_card("Jami", k["n"], "#9333ea", "fa-images", f"{orm.ReviewMediaModel.objects.values('review_id').distinct().count()} ta sharhda"),
            ui.stat_card("Rasmlar", k["img"], "#2563eb", "fa-image", "", "?media_type__exact=image"),
            ui.stat_card("Videolar", k["vid"], "#db2777", "fa-film", "", "?media_type__exact=video"),
            ui.stat_card("Saytda ko'rinadi", k["live"], "#16a34a", "fa-globe", "sharhi chop etilgan", "?review__status__exact=published"),
        ]

    def nz_tabs(self, request):
        counts = dict(orm.ReviewMediaModel.objects.values_list("review__status").annotate(n=Count("id")))
        return ui.tabs_for(request, "review__status__exact", [("", "Hammasi", sum(counts.values()))] + [(s, STATUS[s][0].split(",")[0], n) for s, n in counts.items()],
                           {s: v[1] for s, v in STATUS.items()})

    def lookup_allowed(self, lookup, value, request=None):
        return lookup == "review__status__exact" or super().lookup_allowed(lookup, value, request)

    def nz_hero_actions(self, request):
        return [{"label": "Sharhlar", "url": reverse("admin:reviews_reviewmodel_changelist"), "icon": "fa-star"}]

    def nz_prepare(self, request, objs):
        self._p = _products([m.review.product_id for m in objs])

    def nz_href(self, obj):
        return reverse("admin:reviews_reviewmodel_change", args=[obj.review_id])

    def nz_row(self, m):
        p = self._p.get(m.review.product_id)
        return [
            format_html("{}{}", media_thumb(m), format_html('<span class="nzr-badge">{}</span>', "VIDEO") if m.media_type == "video" else ""),
            format_html("<b>{}</b>", p["name"] if p else "O'chirilgan mahsulot"),
            format_html("{} {}", stars(m.review.rating), status_pill(m.review.status)),
            format_html("<small>{}</small>", ui.local(m.uploaded_at)),
        ]

