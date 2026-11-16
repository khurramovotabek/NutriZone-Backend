"""Moliya dashboard: accounts, categories and operations on the premium kit; the report pages live in views.py."""
from __future__ import annotations

from django import forms
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.finance.infrastructure import ledger
from apps.finance.infrastructure.models import (
    SOURCES, AccountKind, Category, CategoryKind, MoneyAccount, Transaction, TxKind,
)
from apps.finance.infrastructure.views import install, money
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin

install()

FIN_CSS = ("admin/css/nutrizone-finance.css",)
KIND_ICON = {"cash": "fa-money-bill-wave", "bank": "fa-building-columns", "card": "fa-credit-card", "online": "fa-mobile-screen", "other": "fa-wallet"}
TX_STYLE = {"income": ("#16a34a", "fa-arrow-down", "Kirim"), "expense": ("#dc2626", "fa-arrow-up", "Xarajat"), "transfer": ("#2563eb", "fa-right-left", "O'tkazma")}


def _hero_links(active: str = "") -> list[dict]:
    return [{"label": "Moliya paneli", "url": reverse("admin:nz_finance"), "icon": "fa-gauge-high"}]


# ---------------------------------------------------------------- accounts


class MoneyAccountForm(forms.ModelForm):
    sources = forms.MultipleChoiceField(label="Avtomatik tushum va to'lovlar", required=False, widget=forms.CheckboxSelectMultiple,
                                        choices=[(k, str(v[0])) for k, v in SOURCES.items()],
                                        help_text="Tizim o'zi biladigan pul: kassa savdosi, sayt to'lovlari, yetkazib beruvchilarga to'lovlar va ish haqi. Har bir manba faqat bitta hisobga tushadi.")

    class Meta:
        model = MoneyAccount
        fields = ("name", "kind", "store", "sources", "opening_balance", "opening_date", "color", "note", "is_active", "sort_order")
        widgets = {"color": forms.TextInput(attrs={"type": "color"}), "opening_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean_sources(self):
        return list(self.cleaned_data.get("sources") or [])


@admin.register(MoneyAccount)
class MoneyAccountAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = MoneyAccountForm
    list_display = ("name", "kind", "opening_date", "is_active")
    search_fields = ("name", "note")
    list_filter = ("kind", "is_active")
    ordering = ("sort_order", "name")
    actions = None
    fieldsets = (
        ("Hisob", {"fields": ("name", "kind", "store", "color", "sort_order", "is_active", "note")}),
        ("Boshlang'ich holat", {"fields": ("opening_balance", "opening_date")}),
        ("Avtomatik harakatlar", {"fields": ("sources",)}),
    )
    nz_icon, nz_tone, nz_title = "fa-wallet", "#2563eb", "Hisoblar"
    nz_subtitle = "Kassalar, bank hisoblari va kartalar. Qoldiq = boshlang'ich qoldiq + avtomatik tushumlar + qo'lda kiritilgan operatsiyalar."
    nz_columns = (("Hisob", ""), ("Turi", ""), ("Avtomatik manbalar", ""), ("Bu oy kirim", "r"), ("Bu oy chiqim", "r"), ("Ulushi", ""), ("Qoldiq", "r"))
    nz_grid = "minmax(220px,2fr) 130px minmax(200px,2fr) 125px 125px 110px 150px"
    excel_title = "Moliya hisoblari"
    excel_columns = [Col("Hisob", "name", 26), Col("Turi", lambda a: a.get_kind_display(), 16), Col("Filial", lambda a: a.store.name if a.store else "", 20),
                     Col("Avtomatik manbalar", lambda a: ", ".join(str(SOURCES[s][0]) for s in (a.sources or []) if s in SOURCES), 44),
                     Col("Boshlangan", "opening_date", 12), Col("Boshlang'ich qoldiq", "opening_balance", 17, money=True),
                     Col("Bu oy kirim", lambda a: a._x.get("in_month"), 15, money=True), Col("Bu oy chiqim", lambda a: a._x.get("out_month"), 15, money=True),
                     Col("Qoldiq", lambda a: a._x.get("balance"), 17, money=True), Col("Faol", "is_active", 8)]

    def excel_prepare(self, objs):
        bal = ledger.balances(None, [o for o in objs if o.is_active]) if objs else {}
        for o in objs:
            o._x = bal.get(o.id, {})
    nz_search = "Hisob nomi…"
    nz_empty = ("Hali hisob yo'q", "«Qo'shish» bilan birinchi kassa yoki bank hisobini oching.")
    nz_css = FIN_CSS

    def get_changeform_initial_data(self, request):
        return {"opening_date": timezone.localdate(), **super().get_changeform_initial_data(request)}

    def nz_hero_actions(self, request):
        return _hero_links()

    def nz_prepare(self, request, objs):
        self._bal = ledger.balances(None, [o for o in objs if o.is_active]) if objs else {}
        self._share_total = sum((max(b["balance"], 0) for b in self._bal.values()), 0)

    def nz_stats(self, request):
        accounts = list(MoneyAccount.objects.filter(is_active=True))
        bal = ledger.balances(None, accounts)
        total = sum((b["balance"] for b in bal.values()), 0)
        cash = sum((bal[a.id]["balance"] for a in accounts if a.kind == AccountKind.CASH), 0)
        inn = sum((b["in_month"] for b in bal.values()), 0)
        out = sum((b["out_month"] for b in bal.values()), 0)
        cash_pct = round(cash * 100 / total) if total else 0
        return [ui.stat_card("Jami pul", money(total), "#2563eb", "fa-sack-dollar", f"{len(accounts)} ta faol hisob"),
                ui.stat_card("Naqd kassalarda", money(cash), "#16a34a", "fa-money-bill-wave", f"jami pulning {cash_pct}%"),
                ui.stat_card("Bank va kartalarda", money(total - cash), "#7c3aed", "fa-building-columns", f"jami pulning {100 - cash_pct}%" if total else ""),
                ui.stat_card("Bu oy sof harakat", money(inn - out), "#0d9488" if inn >= out else "#dc2626", "fa-arrow-right-arrow-left", f"+{money(inn)} / −{money(out)}")]

    def nz_row(self, a):
        b = getattr(self, "_bal", {}).get(a.id)
        name = format_html('<span class="nzf-acc"><i class="fas {}" style="--c:{}"></i><span><b>{}</b><small>{}</small></span></span>',
                           KIND_ICON.get(a.kind, "fa-wallet"), a.color, a.name, a.store.name if a.store else (a.note or f"{a.opening_date:%d.%m.%Y} dan"))
        src = format_html_join_chips([str(SOURCES[s][0]).split(": ")[-1] for s in (a.sources or []) if s in SOURCES]) or ui.muted("Faqat qo'lda")
        if not a.is_active:
            return [name, ui.chip("Yopilgan", "#94a3b8"), src, ui.muted(), ui.muted(), ui.muted(), ui.muted()]
        bal = b["balance"] if b else 0
        total = getattr(self, "_share_total", 0)
        pct = round(bal * 100 / total) if total and bal > 0 else 0
        share = format_html('<span class="nzf-rowshare" style="--c:{}"><span class="nzf-bar"><i style="width:{}%"></i></span><small>{}%</small></span>', a.color, pct, pct)
        return [name, a.get_kind_display(), src, format_html('<span class="nzf-in">+{}</span>', money(b["in_month"])) if b else ui.muted(),
                format_html('<span class="nzf-out">−{}</span>', money(b["out_month"])) if b else ui.muted(), share,
                format_html('<b class="nzf-bal{}">{}</b>', " is-neg" if bal < 0 else "", money(bal))]

    def nz_href(self, obj):
        return reverse("admin:nz_finance_statement", args=[obj.pk])

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Kassa, bank hisobi yoki karta. Boshlang'ich qoldiq va sana — hozirgi haqiqiy pul bilan boshlang."}
        b = ledger.balances(None, [obj]).get(obj.id, {"balance": obj.opening_balance})
        return {"title": obj.name, "subtitle": f"Hisob qoldig'i: {money(b['balance'])} so'm", "chips": [ui.chip(obj.get_kind_display(), obj.color, KIND_ICON.get(obj.kind, "fa-wallet"))]}

    def has_delete_permission(self, request, obj=None):
        return False  # close an account (Faol off) instead -- its history stays


def format_html_join_chips(items) -> str:
    return mark_safe("".join(str(ui.chip(t, "#0ea5e9")) for t in items))


# ---------------------------------------------------------------- categories


@admin.register(Category)
class CategoryAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    list_display = ("name", "kind", "section", "is_active")
    search_fields = ("name",)
    list_filter = ("kind", "section", "is_active")
    ordering = ("kind", "sort_order", "name")
    actions = None
    fieldsets = ((None, {"fields": ("name", "kind", "section", "icon", "color", "sort_order", "is_active")}),)
    nz_icon, nz_tone, nz_title = "fa-tags", "#0ea5e9", "Moliya moddalari"
    nz_subtitle = "Xarajat va kirim turlari: ijara, kommunal, marketing, soliq… Har biri Foyda va zarar hisobotida o'z qatoriga tushadi."
    nz_columns = (("Modda", ""), ("Turi", ""), ("Hisobotda", ""), ("Holat", ""), ("O'tgan oy", "r"), ("6 oy o'rtacha", "r"), ("Bu oy", "r"))
    nz_grid = "minmax(220px,2fr) 110px minmax(180px,1.4fr) 100px 130px 130px 160px"
    excel_title = "Moliya moddalari"
    excel_columns = [Col("Modda", "name", 28), Col("Turi", lambda c: c.get_kind_display(), 12), Col("Hisobotda", lambda c: c.get_section_display(), 26),
                     Col("Faol", "is_active", 8), Col("Bu oy", lambda c: c._x[0], 15, money=True), Col("O'tgan oy", lambda c: c._x[1], 15, money=True),
                     Col("6 oy jami", lambda c: c._x[2], 16, money=True), Col("6 oy o'rtacha", lambda c: c._x[3], 16, money=True)]

    @staticmethod
    def _periods():
        from datetime import timedelta

        from apps.finance.infrastructure import pnl

        today = timezone.localdate()
        m0 = today.replace(day=1)
        prev0 = pnl.months_back(m0, 2)[0]
        m6 = pnl.months_back(m0, 7)[0]
        return (ledger.manual_totals(m0, today), ledger.manual_totals(prev0, m0 - timedelta(days=1)), ledger.manual_totals(m6, m0 - timedelta(days=1)))

    def excel_prepare(self, objs):
        cur, prev, six = self._periods()
        for c in objs:
            k = (c.kind, c.id)
            c._x = (cur.get(k) or 0, prev.get(k) or 0, six.get(k) or 0, round((six.get(k) or 0) / 6))
    nz_search = "Modda nomi…"
    nz_css = FIN_CSS

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "color":
            kwargs["widget"] = forms.TextInput(attrs={"type": "color"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def nz_hero_actions(self, request):
        return _hero_links()

    def nz_stats(self, request):
        cur, prev, _six = self._periods()
        exp = sum((v for (k, _c), v in cur.items() if k == CategoryKind.EXPENSE), 0)
        pexp = sum((v for (k, _c), v in prev.items() if k == CategoryKind.EXPENSE), 0)
        inc = sum((v for (k, _c), v in cur.items() if k == CategoryKind.INCOME), 0)
        used = len({c for (_k, c) in cur})
        delta = f"o'tgan oy: {money(pexp)}" if pexp else ""
        return [ui.stat_card("Bu oy xarajat (qo'lda)", money(exp), "#dc2626", "fa-arrow-up", delta),
                ui.stat_card("Bu oy kirim (qo'lda)", money(inc), "#16a34a", "fa-arrow-down"),
                ui.stat_card("Ishlatilgan moddalar", f"{used} / {Category.objects.filter(is_active=True).count()}", "#0ea5e9", "fa-tags", "bu oy operatsiyasi bor")]

    def nz_tabs(self, request):
        counts = dict(Category.objects.values_list("kind").annotate(n=Count("id")))
        return ui.tabs_for(request, "kind__exact", [("", "Hammasi", sum(counts.values())), ("expense", "Xarajat", counts.get("expense", 0)), ("income", "Kirim", counts.get("income", 0))],
                           {"expense": "#dc2626", "income": "#16a34a"})

    def nz_prepare(self, request, objs):
        self._month, self._prev, self._six = self._periods()

    def nz_row(self, c):
        name = format_html('<span class="nzf-acc"><i class="fas {}" style="--c:{}"></i><span><b>{}</b></span></span>', c.icon, c.color, c.name)
        kind = ui.chip(c.get_kind_display(), "#16a34a" if c.kind == CategoryKind.INCOME else "#dc2626")
        state = ui.chip("Faol", "#16a34a") if c.is_active else ui.chip("O'chirilgan", "#94a3b8")
        k = (c.kind, c.id)
        v, prev, six = getattr(self, "_month", {}).get(k), getattr(self, "_prev", {}).get(k), getattr(self, "_six", {}).get(k)
        avg = six / 6 if six else None
        trend = ""
        if v and prev:
            ch = round((v - prev) * 100 / prev)
            bad = ch > 0 if c.kind == CategoryKind.EXPENSE else ch < 0
            trend = format_html(' <span class="nzf-delta {}">{}{}%</span>', "is-bad" if bad else "is-good", "+" if ch > 0 else "", ch)
        return [name, kind, c.get_section_display(), state, money(prev) if prev else ui.muted(), money(avg) if avg else ui.muted(),
                format_html("<b>{}</b>{}", money(v), trend) if v else ui.muted()]

    def form_hero(self, request, obj):
        return {"title": obj.name if obj else "", "subtitle": "Modda — operatsiyani guruhlash uchun. «Hisobotdagi o'rni» Foyda va zarar qatorini belgilaydi."}

    def has_delete_permission(self, request, obj=None):
        return bool(obj) and not obj.transactions.exists() and super().has_delete_permission(request, obj)


# ---------------------------------------------------------------- operations


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ("kind", "occurred_on", "amount", "account", "to_account", "category", "store", "counterparty", "reference", "note")
        widgets = {"occurred_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), "amount": forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "account" in self.fields:
            self.fields["account"].queryset = MoneyAccount.objects.filter(is_active=True)
            self.fields["to_account"].queryset = MoneyAccount.objects.filter(is_active=True)
            self.fields["category"].queryset = Category.objects.filter(is_active=True)
            self.fields["category"].required = False
            import json

            self.fields["category"].widget.attrs["data-kinds"] = json.dumps({str(c.pk): c.kind for c in Category.objects.filter(is_active=True)})

    def clean_amount(self):
        v = self.cleaned_data.get("amount")
        if v is not None and v <= 0:
            raise forms.ValidationError("Summa noldan katta bo'lishi kerak.")
        return v

    def clean(self):
        data = super().clean()
        if data.get("occurred_on") and data["occurred_on"] > timezone.localdate():
            self.add_error("occurred_on", "Kelajakdagi sana bo'lmaydi.")
        acc = data.get("account")
        if acc and data.get("occurred_on") and data["occurred_on"] < acc.opening_date:
            self.add_error("occurred_on", f"«{acc.name}» hisobi {acc.opening_date:%d.%m.%Y} dan boshlangan.")
        return data


@admin.register(Transaction)
class TransactionAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = TransactionForm
    list_display = ("number", "occurred_on", "kind", "account", "category", "amount")
    search_fields = ("number", "counterparty", "note", "reference")
    list_filter = ("kind", "account", "category", "store")
    date_hierarchy = "occurred_on"
    ordering = ("-occurred_on", "-created_at")
    list_select_related = ("account", "to_account", "category", "store")
    list_per_page = 50
    actions = None
    nz_icon, nz_tone, nz_title = "fa-right-left", "#7c3aed", "Operatsiyalar"
    nz_subtitle = "Qo'lda kiritilgan kirim, xarajat va hisoblar orasidagi o'tkazmalar. Savdo, yetkazib beruvchilarga to'lov va ish haqi avtomatik hisoblanadi."
    nz_columns = (("Operatsiya", ""), ("Sana", ""), ("Hisob", ""), ("Modda / kontragent", ""), ("Kim kiritdi", ""), ("Summa", "r"))
    nz_grid = "minmax(170px,1.2fr) 110px minmax(160px,1.3fr) minmax(200px,2fr) 140px 150px"
    nz_search = "Raqam, kontragent, izoh…"
    nz_empty = ("Operatsiya yo'q", "«Qo'shish» bilan birinchi xarajat yoki kirimni kiriting.")
    nz_sorts = (("Yangi", ""), ("Katta summa", "-6"), ("Eski", "2"))
    nz_css = FIN_CSS
    excel_title = "Moliya operatsiyalari"
    excel_columns = [Col("Raqam", "number", 12), Col("Sana", "occurred_on", 12), Col("Turi", lambda t: t.get_kind_display(), 12), Col("Hisob", "account.name", 22),
                     Col("Qaysi hisobga", lambda t: t.to_account.name if t.to_account else "", 22), Col("Modda", lambda t: t.category.name if t.category else "", 22),
                     Col("Filial", lambda t: t.store.name if t.store else "", 18), Col("Kontragent", "counterparty", 22), Col("Izoh", "note", 30),
                     Col("Summa", "amount", 16, money=True), Col("Bekor qilingan", lambda t: "Ha" if t.voided_at else "", 10), Col("Kiritdi", "created_by", 16)]

    def get_fieldsets(self, request, obj=None):
        sets = [("Operatsiya", {"fields": ("kind", "occurred_on", "amount", "account", "to_account")}),
                ("Tafsilotlar", {"fields": ("category", "store", "counterparty", "reference", "note")})]
        if obj is not None:
            sets.append(("Bekor qilish", {"fields": ("void_panel",), "classes": ("nzi-panel",)}))
        return sets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        locked = ("kind", "amount", "account", "to_account", "occurred_on", "void_panel")  # money facts: void and re-enter instead of rewriting history
        return locked + (("category", "store", "counterparty", "reference", "note") if obj.voided_at else ())

    @admin.display(description="")
    def void_panel(self, obj):
        if obj is None:
            return ""
        if obj.voided_at:
            return format_html('<div class="nzf-void is-done"><i class="fas fa-ban"></i> {} da bekor qilingan ({}). Sabab: <b>{}</b></div>',
                               timezone.localtime(obj.voided_at).strftime("%d.%m.%Y %H:%M"), obj.voided_by or "—", obj.void_reason)
        return format_html(
            '<div class="nzf-void"><p>Xato kiritilgan operatsiya o\'chirilmaydi — bekor qilinadi: u hech bir qoldiq va hisobotga kirmaydi, tarixda esa qoladi.</p>'
            '<div class="nzf-void-row"><input name="reason" maxlength="255" placeholder="Sabab: masalan, summa xato kiritildi">'
            '<button type="submit" class="nzf-void-btn" formaction="{}" formnovalidate data-nzi-confirm="Operatsiyani bekor qilasizmi?"><i class="fas fa-ban"></i> Bekor qilish</button></div></div>',
            reverse("admin:nz_finance_void", args=[obj.pk]))

    def get_changeform_initial_data(self, request):
        data = super().get_changeform_initial_data(request)
        data.setdefault("occurred_on", timezone.localdate())
        if request.GET.get("kind") in TxKind.values:
            data["kind"] = request.GET["kind"]
        first = MoneyAccount.objects.filter(is_active=True).order_by("sort_order", "name").first()
        if first and "account" not in data:
            data["account"] = first.pk
        return data

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.get_full_name() or request.user.get_username()
            for _attempt in range(5):
                last = Transaction.objects.aggregate(m=Max("number"))["m"]
                obj.number = f"FO-{(int(last.split('-')[1]) + 1) if last else 1:06d}"
                try:
                    with transaction.atomic():
                        obj.save()
                    return
                except IntegrityError:
                    continue
            raise IntegrityError("Could not allocate an operation number")
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False  # void instead -- the money history stays complete

    def nz_hero_actions(self, request):
        add = reverse("admin:finance_transaction_add")
        out = _hero_links()
        if self.has_add_permission(request):
            out += [{"label": "Kirim", "url": f"{add}?kind=income", "icon": "fa-arrow-down"},
                    {"label": "O'tkazma", "url": f"{add}?kind=transfer", "icon": "fa-right-left"},
                    {"label": "Xarajat", "url": f"{add}?kind=expense", "icon": "fa-plus", "primary": True}]
        return out

    def nz_tabs(self, request):
        counts = dict(Transaction.objects.filter(voided_at__isnull=True).values_list("kind").annotate(n=Count("id")))
        return ui.tabs_for(request, "kind__exact", [("", "Hammasi", sum(counts.values())), ("expense", "Xarajat", counts.get("expense", 0)),
                                                    ("income", "Kirim", counts.get("income", 0)), ("transfer", "O'tkazma", counts.get("transfer", 0))],
                           {"expense": "#dc2626", "income": "#16a34a", "transfer": "#2563eb"})

    def nz_stats(self, request):
        today = timezone.localdate()
        m0 = today.replace(day=1)
        live = Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=m0)
        agg = live.aggregate(e=Sum("amount", filter=Q(kind="expense")), i=Sum("amount", filter=Q(kind="income")), n=Count("id"))
        top = (live.filter(kind="expense").values("category__name").annotate(s=Sum("amount")).order_by("-s").first())
        from datetime import timedelta

        from apps.finance.infrastructure import insights, pnl

        prev0 = pnl.months_back(m0, 2)[0]
        prev_end = min(prev0 + timedelta(days=today.day - 1), m0 - timedelta(days=1))
        pexp = Transaction.objects.filter(voided_at__isnull=True, kind="expense", occurred_on__gte=prev0, occurred_on__lte=prev_end).aggregate(s=Sum("amount"))["s"] or 0
        ch = insights.pct_change(agg["e"] or 0, pexp)
        voided = Transaction.objects.filter(voided_at__isnull=False, occurred_on__gte=m0).count()
        per_day = (agg["e"] or 0) / today.day
        return [ui.stat_card("Bu oy xarajat", money(agg["e"] or 0), "#dc2626", "fa-arrow-up",
                             f"o'tgan oy shu kunlari: {money(pexp)}" + (f" ({'+' if ch > 0 else ''}{ch}%)" if ch is not None else "")),
                ui.stat_card("Kunlik o'rtacha xarajat", money(per_day), "#f59e0b", "fa-calendar-day", f"{agg['n']} ta operatsiya bu oy"),
                ui.stat_card("Bu oy kirim (qo'lda)", money(agg["i"] or 0), "#16a34a", "fa-arrow-down"),
                ui.stat_card("Eng katta modda", top["category__name"] if top else "—", "#7c3aed", "fa-chart-pie", money(top["s"]) if top else ""),
                ui.stat_card("Bekor qilingan", voided, "#94a3b8", "fa-ban", "bu oy · hisobga kirmaydi")]

    def nz_row(self, t):
        color, icon, label = TX_STYLE[t.kind]
        num = format_html('<span class="nzf-acc"><i class="fas {}" style="--c:{}"></i><span><b>{}</b><small>{}</small></span></span>', icon, color, t.number, label)
        acc = format_html("{} → {}", t.account.name, t.to_account.name) if t.kind == TxKind.TRANSFER and t.to_account else t.account.name
        what = format_html("<b>{}</b>{}", t.category.name if t.category else "O'tkazma",
                           format_html("<br><small>{}</small>", " · ".join(p for p in (t.counterparty, t.note) if p)) if (t.counterparty or t.note) else "")
        sign = {"income": "+", "expense": "−", "transfer": ""}[t.kind]
        amount = format_html('<b class="nzf-amt is-{}">{}{}</b>', t.kind, sign, money(t.amount))
        if t.voided_at:
            amount = format_html('<s class="nzi-muted">{}</s> {}', money(t.amount), ui.chip("Bekor", "#94a3b8"))
        return [num, f"{t.occurred_on:%d.%m.%Y}", acc, what, t.created_by or ui.muted(), amount]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Kirim, xarajat yoki hisoblar orasida o'tkazma. Sotuv, yetkazib beruvchiga to'lov va ish haqini bu yerga kiritmang — ular avtomatik hisoblanadi."}
        color, icon, label = TX_STYLE[obj.kind]
        chips = [ui.chip(label, color, icon)]
        if obj.voided_at:
            chips.append(ui.chip(f"Bekor qilingan: {obj.void_reason}", "#94a3b8", "fa-ban"))
        return {"title": f"{obj.number} · {money(obj.amount)} so'm", "subtitle": f"{obj.occurred_on:%d.%m.%Y} · {obj.account} · kiritdi: {obj.created_by or '—'}", "chips": chips}

    @property
    def media(self):
        from django.conf import settings

        return super().media + forms.Media(js=(f"{settings.STATIC_URL}admin/js/nutrizone-finance.js?v=1",))

