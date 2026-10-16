"""
Dashboard → Support: the call log (list + card) and the Kanban board (Yangi → O'ylab ko'radi → Qayta qo'ng'iroq →
Buyurtma berdi / Hal qilindi / Rad etdi). Creating and moving cases goes through services (notes, auto customer).
"""
from __future__ import annotations

import json

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin
from apps.support.infrastructure import services
from apps.support.infrastructure.models import OPEN_STATUSES, CaseChannel, CasePriority, CaseStatus, CaseTopic, SupportCase

STATUS_TONE = {"new": "#2563eb", "thinking": "#f59e0b", "callback": "#8b5cf6", "ordered": "#16a34a", "resolved": "#0d9488", "lost": "#94a3b8"}
STATUS_ICON = {"new": "fa-inbox", "thinking": "fa-hourglass-half", "callback": "fa-phone-volume", "ordered": "fa-bag-shopping", "resolved": "fa-circle-check", "lost": "fa-circle-xmark"}
CLOSED_DAYS = 7


def _staff(request) -> str:
    return request.user.get_full_name() or request.user.get_username()


class SupportCaseForm(forms.ModelForm):
    phone = forms.CharField(label="Telefon", max_length=20, widget=forms.TextInput(attrs={"placeholder": "+998 90 123 45 67", "inputmode": "tel", "autocomplete": "off"}))
    note = forms.CharField(label="Yangi izoh", required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Qo'ng'iroq natijasi, kelishuv…"}))

    class Meta:
        model = SupportCase
        fields = ("phone", "name", "topic", "channel", "status", "priority", "summary", "products", "next_contact_at", "order_number", "assigned_to")
        widgets = {"summary": forms.Textarea(attrs={"rows": 4, "placeholder": "Mijoz nima so'radi, nima taklif qilindi…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and not self.instance._state.adding:
            self.fields["phone"].disabled = True
            self.fields["phone"].initial = self.instance.phone
            self.fields["summary"].disabled = True

    def clean_phone(self):
        if self.instance and not self.instance._state.adding:
            return self.instance.phone
        try:
            return services.normalize_phone(self.cleaned_data["phone"])
        except services.SupportError as exc:
            raise forms.ValidationError(str(exc)) from exc


@admin.register(SupportCase)
class SupportCaseAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = SupportCaseForm
    list_display = ("number", "created_at")
    list_filter = ("topic", "channel", "priority")
    search_fields = ("number", "phone", "name", "summary", "customer__full_name")
    ordering = ("-created_at",)
    list_per_page = 40
    autocomplete_fields = ("products",)
    readonly_fields = ("history_panel", "customer_panel")
    fieldsets = (
        ("Mijoz", {"fields": ("phone", "name")}),
        ("Murojaat", {"fields": ("topic", "channel", "priority", "summary", "products")}),
        ("Natija", {"fields": ("status", "next_contact_at", "order_number", "assigned_to", "note")}),
    )
    excel_title = "Support murojaatlari"
    excel_columns = [Col("Raqam", "number", 12), Col("Sana", "created_at", 17), Col("Ism", "display_name", 22), Col("Telefon", "phone", 15),
                     Col("Mavzu", lambda c: c.get_topic_display(), 18), Col("Kanal", lambda c: c.get_channel_display(), 16), Col("Holat", lambda c: c.get_status_display(), 14),
                     Col("Keyingi aloqa", "next_contact_at", 17), Col("Mas'ul", "assigned_to", 18), Col("Mazmun", "summary", 60)]

    nz_icon, nz_tone, nz_title = "fa-headset", "#2563eb", "Support murojaatlari"
    nz_subtitle = "Qo'ng'iroqlar va murojaatlar: kim, nima haqida, natija va keyingi qadam. Ish uchun — Support paneli."
    nz_columns = (("Murojaat", ""), ("Mijoz", ""), ("Mavzu", ""), ("Keyingi aloqa", ""), ("Holat", "r"))
    nz_grid = "minmax(260px,2.4fr) minmax(170px,1.2fr) 150px 150px 130px"
    nz_search = "Raqam, telefon, ism yoki mazmun…"
    nz_empty = ("Murojaat yo'q", "«Yangi murojaat» yoki Support panelidan qo'ng'iroqni yozing.")
    hero_icon, hero_tone, hero_noun = "fa-headset", "#2563eb", "murojaat"

    def get_fieldsets(self, request, obj=None):
        fs = list(super().get_fieldsets(request, obj))
        if obj is not None:
            fs = [("Mijoz kartasi", {"classes": ("nzi-panel",), "fields": ("customer_panel",)})] + fs + [("Tarix", {"classes": ("nzi-panel",), "fields": ("history_panel",)})]
        return fs

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [path("board/", wrap(self.board_view), name="support_supportcase_board"),
                path("board/data.json", wrap(self.board_data), name="support_supportcase_board_data"),
                path("board/move/", wrap(self.board_move), name="support_supportcase_board_move"),
                path("board/create/", wrap(self.board_create), name="support_supportcase_board_create"),
                *super().get_urls()]

    # ---------------------------------------------------------------- list
    def lookup_allowed(self, lookup, value, request=None):
        return lookup == "status__exact" or super().lookup_allowed(lookup, value, request)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("customer")
        if getattr(request, "_nz_overdue", "") == "1":
            qs = qs.filter(status__in=OPEN_STATUSES, next_contact_at__lte=timezone.now())
        return qs

    def changelist_view(self, request, extra_context=None):
        if "overdue" in request.GET:  # custom filter, not a model field: hide it from the ChangeList
            request.GET = request.GET.copy()
            request._nz_overdue = request.GET.pop("overdue")[0]
        return super().changelist_view(request, extra_context)

    def nz_stats(self, request):
        now = timezone.now()
        k = SupportCase.objects.aggregate(open=Count("id", filter=Q(status__in=OPEN_STATUSES)), today=Count("id", filter=Q(created_at__date=timezone.localdate())),
                                          overdue=Count("id", filter=Q(status__in=OPEN_STATUSES, next_contact_at__lte=now)),
                                          won=Count("id", filter=Q(status="ordered")), closed=Count("id", filter=~Q(status__in=OPEN_STATUSES)))
        conv = round(k["won"] * 100 / k["closed"]) if k["closed"] else 0
        base = reverse("admin:support_supportcase_changelist")
        return [ui.stat_card("Ochiq", k["open"], "#2563eb", "fa-inbox", "ishlanmoqda", base + "?status__exact=new"),
                ui.stat_card("Bugun", k["today"], "#0ea5e9", "fa-phone", "yangi murojaat"),
                ui.stat_card("Qayta qo'ng'iroq vaqti o'tgan", k["overdue"], "#dc2626", "fa-clock", "hozir qo'ng'iroq qiling" if k["overdue"] else "hammasi vaqtida", base + "?overdue=1"),
                ui.stat_card("Buyurtmaga aylandi", f"{conv}%", "#16a34a", "fa-bag-shopping", f"{k['won']} ta yopilgan murojaatdan")]

    def nz_tabs(self, request):
        counts = dict(SupportCase.objects.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values()))] + [(v, label, counts.get(v, 0)) for v, label in CaseStatus.choices], STATUS_TONE)

    def nz_hero_actions(self, request):
        return [{"label": "Support paneli", "url": reverse("admin:support_supportcase_board"), "icon": "fa-table-columns", "primary": True},
                {"label": "Yangi murojaat", "url": reverse("admin:support_supportcase_add"), "icon": "fa-plus"}]

    def nz_row(self, c):
        late = c.status in OPEN_STATUSES and c.next_contact_at and c.next_contact_at <= timezone.now()
        nxt = format_html('<span style="color:{}">{}</span><small>{}</small>', "#dc2626" if late else "inherit", ui.local(c.next_contact_at, "%d.%m %H:%M"), "vaqti o'tdi" if late else ui.ago(c.next_contact_at)) if c.next_contact_at else ui.muted()
        text = c.summary if len(c.summary) <= 90 else c.summary[:87] + "…"
        return [format_html("<b>{}</b><small>{}</small>", c.number, text),
                format_html("<b>{}</b><small>{}</small>", c.display_name, c.phone),
                format_html("{}<small>{}</small>", c.get_topic_display(), c.get_channel_display()), nxt,
                format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE[c.status], c.get_status_display())]

    # ---------------------------------------------------------------- form
    def form_hero(self, request, obj):
        if obj is None:
            return {"title": "Yangi murojaat", "subtitle": "Telefon raqami bo'yicha mijoz topiladi yoki avtomatik yaratiladi. Ism kiritilmasa — «Noma'lum»."}
        return {"title": f"{obj.number} · {obj.display_name}", "subtitle": f"{obj.phone} · {obj.get_topic_display()} · {ui.local(obj.created_at)}",
                "icon": STATUS_ICON[obj.status], "tone": STATUS_TONE[obj.status],
                "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE[obj.status], obj.get_status_display())],
                "links": [{"label": "Support paneli", "url": reverse("admin:support_supportcase_board"), "icon": "fa-table-columns"},
                          {"label": "Qo'ng'iroq", "url": f"tel:{obj.phone}", "icon": "fa-phone", "primary": True}]}

    def save_model(self, request, obj, form, change):
        d = form.cleaned_data
        if not change:
            case = services.create_case(phone=d["phone"], name=d.get("name", ""), summary=d["summary"], topic=d["topic"], channel=d["channel"],
                                        status=d["status"], priority=d["priority"], next_contact_at=d.get("next_contact_at"), staff=_staff(request))
            obj.pk, obj.number = case.pk, case.number
            obj._state.adding = False
            SupportCase.objects.filter(pk=case.pk).update(order_number=d.get("order_number", ""), assigned_to=d.get("assigned_to") or _staff(request))
            return
        old = SupportCase.objects.get(pk=obj.pk)
        new_status = obj.status
        obj.status = old.status  # the status moves through the service (it writes the history note)
        super().save_model(request, obj, form, change)
        if new_status != old.status:
            services.move(obj, new_status, _staff(request), d.get("note", ""))
        elif d.get("note"):
            services.add_note(obj, d["note"], _staff(request))

    def save_related(self, request, form, formsets, change):
        form.instance = SupportCase.objects.get(pk=form.instance.pk)
        super().save_related(request, form, formsets, change)

    @admin.display(description="")
    def customer_panel(self, obj):
        from apps.ordering.infrastructure.models import OrderModel

        u = obj.customer
        orders = OrderModel.objects.filter(customer_id=u.id).count()
        cases = u.support_cases.count()
        profile = getattr(u, "support_profile", None)
        badge = ("Support yaratgan · bot orqali tasdiqlanmagan" if profile and not profile.confirmed_at else "Tasdiqlangan") if profile else "Saytda ro'yxatdan o'tgan"
        return format_html('<div class="nzi-panel-body"><p><b>{}</b> · {} · <span class="nzi-chip" style="--t:#64748b">{}</span></p><p>Buyurtmalar: <b>{}</b> · Murojaatlar: <b>{}</b> · Telegram: {}</p>'
                           '<p><a href="{}">Mijoz kartasi →</a></p></div>',
                           u.full_name or "Noma'lum", u.phone_number, badge, orders, cases, "ulangan" if u.telegram_user_id else "ulanmagan",
                           reverse("admin:identity_user_change", args=[u.pk]))

    @admin.display(description="")
    def history_panel(self, obj):
        icon = {"call": "fa-phone", "status": "fa-arrow-right", "note": "fa-note-sticky"}
        items = format_html_join("", '<li><span><i class="fas {}" aria-hidden="true"></i> {}</span><span class="nzi-when">{} · {}</span></li>',
                                 ((icon.get(n.kind, "fa-note-sticky"), n.text, n.author or "—", ui.local(n.created_at, "%d.%m.%Y %H:%M")) for n in obj.notes.all()))
        return format_html('<div class="nzi-panel-body"><ul class="nzi-items">{}</ul></div>', items)

    # ---------------------------------------------------------------- board
    def board_view(self, request):
        return render(request, "admin/support/board.html", {
            **self.admin_site.each_context(request), "title": "Support paneli",
            "topics": CaseTopic.choices, "channels": CaseChannel.choices, "priorities": CasePriority.choices,
            "data_url": reverse("admin:support_supportcase_board_data"), "move_url": reverse("admin:support_supportcase_board_move"),
            "create_url": reverse("admin:support_supportcase_board_create"), "list_url": reverse("admin:support_supportcase_changelist"),
        })

    def board_data(self, request):
        now = timezone.now()
        q = (request.GET.get("q") or "").strip()
        qs = SupportCase.objects.filter(Q(status__in=OPEN_STATUSES) | Q(updated_at__gte=now - timezone.timedelta(days=CLOSED_DAYS))).select_related("customer")
        if q:
            qs = qs.filter(Q(phone__icontains=q.replace(" ", "")) | Q(name__icontains=q) | Q(summary__icontains=q) | Q(number__icontains=q))
        if request.GET.get("topic"):
            qs = qs.filter(topic=request.GET["topic"])
        cols = []
        rows = list(qs.order_by("next_contact_at", "-created_at")[:400])
        for value, label in CaseStatus.choices:
            cards = [{
                "id": str(c.id), "number": c.number, "name": c.display_name, "phone": c.phone, "topic": c.get_topic_display(),
                "channel": c.get_channel_display(), "summary": c.summary[:160], "priority": c.priority,
                "next": c.next_contact_at.isoformat() if c.next_contact_at else None, "late": bool(c.status in OPEN_STATUSES and c.next_contact_at and c.next_contact_at <= now),
                "created": c.created_at.isoformat(), "url": reverse("admin:support_supportcase_change", args=[c.pk]),
            } for c in rows if c.status == value]
            cols.append({"key": value, "label": label, "color": STATUS_TONE[value], "icon": STATUS_ICON[value], "cards": cards, "open": value in OPEN_STATUSES})
        return JsonResponse({"columns": cols, "now": now.isoformat()})

    def board_move(self, request):
        if request.method != "POST" or not self.has_change_permission(request):
            return JsonResponse({"ok": False, "error": "Ruxsat yo'q"}, status=403)
        body = json.loads(request.body or b"{}")
        case = SupportCase.objects.filter(pk=body.get("id")).first()
        if case is None:
            return JsonResponse({"ok": False, "error": "Topilmadi"}, status=404)
        try:
            services.move(case, body.get("status"), _staff(request), (body.get("note") or "")[:500])
        except services.SupportError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True})

    def board_create(self, request):
        if request.method != "POST" or not self.has_add_permission(request):
            return JsonResponse({"ok": False, "error": "Ruxsat yo'q"}, status=403)
        body = json.loads(request.body or b"{}")
        next_at = None
        if body.get("next_contact_at"):
            from django.utils.dateparse import parse_datetime

            parsed = parse_datetime(body["next_contact_at"])
            next_at = timezone.make_aware(parsed) if parsed and timezone.is_naive(parsed) else parsed
        try:
            case = services.create_case(phone=body.get("phone", ""), name=body.get("name", ""), summary=body.get("summary", ""), topic=body.get("topic") or "product",
                                        channel=body.get("channel") or "call_in", status=body.get("status") or "new", priority=body.get("priority") or "normal",
                                        next_contact_at=next_at, staff=_staff(request))
        except services.SupportError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True, "number": case.number, "customer_new": bool(getattr(case.customer, "support_profile", None) and case.customer.support_cases.count() == 1)})

    def response_add(self, request, obj, post_url_continue=None):
        messages.success(request, f"{obj.number} murojaat yozildi.")
        return HttpResponseRedirect(reverse("admin:support_supportcase_change", args=[obj.pk]))
