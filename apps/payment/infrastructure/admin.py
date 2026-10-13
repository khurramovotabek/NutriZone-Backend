"""
Dashboard → To'lovlar.

  To'lov tizimlari  (PaymentProviderConfig)  cards per method: status, mode, volume; settings page per
                                              method with encrypted secrets, callback URLs to paste into
                                              the merchant cabinet, setup steps and a connection self-test
  Tranzaksiyalar    (PaymentModel)           KPIs, status tabs, filters; a transaction card with the
                                              full provider conversation (callback journal)
  Callback jurnali  (PaymentCallbackLog)     every request a provider sent and what we answered

Secrets are write-only here: the form shows a masked hint, an empty field keeps the stored value.
"""
from __future__ import annotations

import base64
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _

from apps.payment.infrastructure.crypto import decrypt_secrets, encrypt_secrets, mask
from apps.payment.infrastructure.models import (
    PaymentCallbackLog,
    PaymentModel,
    PaymentProviderConfig,
    PaymentReconciliationIssue,
    PaymentSettings,
    PaymentStatusChoices,
    ReconciliationStatus,
)
from apps.payment.infrastructure.providers import registry
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin

STATUS_STYLE = {
    "created": (_("Yaratildi"), "#64748b", "fa-circle-dot"),
    "pending": (_("Kutilmoqda"), "#f59e0b", "fa-hourglass-half"),
    "succeeded": (_("To'landi"), "#10b981", "fa-circle-check"),
    "failed": (_("Xato"), "#e11d48", "fa-circle-xmark"),
    "cancelled": (_("Bekor qilindi"), "#94a3b8", "fa-ban"),
    "refunded": (_("Qaytarildi"), "#8b5cf6", "fa-rotate-left"),
}
PROVIDER_STATUS = {
    "active": (_("Faol"), "#10b981", "fa-circle-check"),
    "disabled": (_("O'chirilgan"), "#64748b", "fa-power-off"),
    "not_configured": (_("Sozlanmagan"), "#f59e0b", "fa-triangle-exclamation"),
}


def _money(v) -> str:
    return f"{int(round(v or 0)):,}".replace(",", " ")


def _logo(key: str) -> str:
    from django.templatetags.static import static

    return static(f"admin/img/payments/{key}.svg")


def _public_base(request) -> str:
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return base or request.build_absolute_uri("/").rstrip("/")


def _style(status: str):
    label, color, icon = STATUS_STYLE.get(status, (status, "#64748b", "fa-circle"))
    return {"key": status, "label": label, "color": color, "icon": icon}


def _volume(qs) -> dict:
    agg = qs.aggregate(n=Count("id"), s=Sum("amount"))
    return {"count": agg["n"] or 0, "sum": agg["s"] or Decimal(0)}


# ====================================================================== providers


class ProviderForm:
    """Validates and applies one provider's settings page (plain class -- the fields come from the registry spec)."""

    def __init__(self, state: registry.ProviderState, row: PaymentProviderConfig, data=None) -> None:
        self.state, self.row, self.data = state, row, data
        self.errors: dict[str, str] = {}

    def fields(self) -> list[dict]:
        stored = decrypt_secrets(self.row.secrets_encrypted)
        out = []
        for f in self.state.spec.fields:
            value = (self.data.get(f.key, "") if self.data is not None and not f.secret else (self.row.settings_public or {}).get(f.key, ""))
            out.append({
                "key": f.key, "label": f.label, "help": f.help, "secret": f.secret, "required": f.required, "placeholder": f.placeholder or f.default,
                "value": value if not f.secret else "", "hint": mask(stored.get(f.key, "")) if f.secret else "", "has_value": bool(stored.get(f.key)),
                "choices": [(c, registry.provider_label(c)) for c in f.choices], "error": self.errors.get(f.key, ""),
                "default": f.default,
            })
        return out

    def is_valid(self) -> bool:
        d = self.data
        for key in ("min_amount", "max_amount"):
            raw = (d.get(key) or "").replace(" ", "")
            if raw:
                try:
                    if Decimal(raw) < 0:
                        raise InvalidOperation
                except InvalidOperation:
                    self.errors[key] = _t("Enter a valid amount.")
        for f in self.state.spec.fields:
            raw = (d.get(f.key) or "").strip()
            if f.choices and raw and raw not in f.choices:
                self.errors[f.key] = _t("Choose one of the options.")
            if f.key in ("service_id", "merchant_id") and self.state.key in ("click", "uzum") and raw and not raw.isdigit():
                self.errors[f.key] = _t("Only digits.")
            if f.key == "checkout_url" and raw and "{order}" not in raw:
                self.errors[f.key] = _t("The template must contain {order}.")
        return not self.errors

    def save(self, user) -> list[str]:
        """Applies the form; returns the names of what changed (for the audit message, never values)."""
        d, row, changed = self.data, self.row, []
        public = dict(row.settings_public or {})
        secrets = decrypt_secrets(row.secrets_encrypted)
        for f in self.state.spec.fields:
            if f.secret:
                new = (d.get(f.key) or "").strip()
                if d.get(f"clear_{f.key}"):
                    if secrets.pop(f.key, None):
                        changed.append(str(f.label))
                elif new and new != secrets.get(f.key):
                    secrets[f.key] = new
                    changed.append(str(f.label))
            else:
                new = (d.get(f.key) or "").strip()
                if new != (public.get(f.key) or ""):
                    public[f.key] = new
                    changed.append(str(f.label))
        enabled, test = bool(d.get("is_enabled")), bool(d.get("is_test_mode"))
        if enabled != row.is_enabled:
            changed.append(_t("Holat"))
        if test != row.is_test_mode and self.state.spec.supports_test:
            changed.append(_t("Test rejimi"))
        mn = Decimal((d.get("min_amount") or "0").replace(" ", "") or "0")
        mx_raw = (d.get("max_amount") or "").replace(" ", "")
        mx = Decimal(mx_raw) if mx_raw else None
        if mn != row.min_amount or mx != row.max_amount:
            changed.append(_t("Limitlar"))
        row.settings_public, row.secrets_encrypted = public, encrypt_secrets(secrets)
        row.is_enabled, row.is_test_mode, row.min_amount, row.max_amount = enabled, test if self.state.spec.supports_test else False, mn, mx
        row.updated_by = user if getattr(user, "is_authenticated", False) else None
        row.save()
        return changed


@admin.register(PaymentProviderConfig)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ("provider", "is_enabled", "is_test_mode")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("<str:key>/selftest/", v(self.selftest_view), name="payment_paymentproviderconfig_selftest"),
            path("automation/", v(self.automation_view), name="payment_paymentproviderconfig_automation"),
            *super().get_urls(),
        ]

    def automation_view(self, request):
        """Saves the unpaid-order reminder / auto-cancel / reconciliation settings card."""
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied
        cfg = PaymentSettings.load()
        try:
            minutes = max(5, min(24 * 60, int(request.POST.get("reminder_after_minutes") or cfg.reminder_after_minutes)))
            hours = max(1, min(7 * 24, int(request.POST.get("auto_cancel_after_hours") or cfg.auto_cancel_after_hours)))
        except ValueError:
            messages.error(request, _t("Daqiqa va soat butun son bo'lishi kerak."))
            return HttpResponseRedirect(reverse("admin:payment_paymentproviderconfig_changelist"))
        if hours * 60 <= minutes:
            messages.error(request, _t("Bekor qilish muddati eslatmadan keyin bo'lishi kerak."))
            return HttpResponseRedirect(reverse("admin:payment_paymentproviderconfig_changelist"))
        cfg.reminder_enabled = bool(request.POST.get("reminder_enabled"))
        cfg.auto_cancel_enabled = bool(request.POST.get("auto_cancel_enabled"))
        cfg.reconcile_enabled = bool(request.POST.get("reconcile_enabled"))
        cfg.reminder_after_minutes, cfg.auto_cancel_after_hours = minutes, hours
        cfg.save()
        messages.success(request, _t("Avtomatlashtirish sozlamalari saqlandi."))
        return HttpResponseRedirect(reverse("admin:payment_paymentproviderconfig_changelist"))

    # ------------------------------------------------------------------ overview
    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        now = timezone.now()
        today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        month = now - timedelta(days=30)
        paid = PaymentModel.objects.filter(status=PaymentStatusChoices.SUCCEEDED).exclude(provider="cash")
        attempts = PaymentModel.objects.filter(created_at__gte=month).exclude(provider="cash").exclude(provider_reference__isnull=True)
        month_paid = attempts.filter(status=PaymentStatusChoices.SUCCEEDED).count()
        cards = []
        for state in registry.all_states():
            row = PaymentProviderConfig.objects.filter(provider=state.key).first()
            status = state.status
            label, color, icon = PROVIDER_STATUS[status]
            method_q = Q(method=state.key) | (Q(method="", provider=state.key))
            vol = _volume(paid.filter(method_q, paid_at__gte=month))
            cards.append({
                "key": state.key, "name": state.spec.name, "tagline": state.spec.tagline, "color": state.spec.color, "logo": _logo(state.key),
                "status": {"key": status, "label": label, "color": color, "icon": icon}, "online": state.spec.online, "test": state.test_mode and state.spec.supports_test,
                "missing": len(state.missing) if state.key not in registry.CARD_BRANDS else 0, "route": registry.provider_label(state.route) if state.route else "",
                "volume": _money(vol["sum"]), "count": vol["count"], "last_callback": row.last_callback_at if row else None,
                "url": reverse("admin:payment_paymentproviderconfig_change", args=[row.pk]) if row else "",
            })
        active = [c for c in cards if c["status"]["key"] == "active"]
        from apps.payment.infrastructure import automation

        extra = {
            "title": _t("To'lov tizimlari"), "cards": cards, "auto": PaymentSettings.load(), "recon": reconciliation_banner(),
            "awaiting": sum(1 for _ in automation.awaiting_orders()), "can_change": self.has_change_permission(request),
            "kpi": {
                "today": _money(_volume(paid.filter(paid_at__gte=today))["sum"]), "month": _money(_volume(paid.filter(paid_at__gte=month))["sum"]),
                "month_count": paid.filter(paid_at__gte=month).count(), "success": round(month_paid * 100 / attempts.count()) if attempts.count() else None,
                "active": len(active), "total": len(cards), "pending": PaymentModel.objects.filter(status=PaymentStatusChoices.PENDING).count(),
                "errors": PaymentCallbackLog.objects.filter(created_at__gte=now - timedelta(days=1), error_code__isnull=False).exclude(error_code=0).count(),
            },
        }
        return render(request, "admin/payment/providers.html", {**self.admin_site.each_context(request), "opts": self.model._meta, **extra, **(extra_context or {})})

    # ------------------------------------------------------------------ settings page
    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        row = get_object_or_404(PaymentProviderConfig, pk=object_id)
        state = registry.load(row.provider)
        can_change = self.has_change_permission(request, row)
        form = ProviderForm(state, row, request.POST if request.method == "POST" else None)
        if request.method == "POST":
            if not can_change:
                raise PermissionDenied
            if form.is_valid():
                changed = form.save(request.user)
                fresh = registry.load(row.provider)
                if changed:
                    messages.success(request, _t("%(name)s saqlandi: %(what)s.") % {"name": state.spec.name, "what": ", ".join(changed)})
                else:
                    messages.info(request, _t("Hech narsa o'zgarmadi."))
                if fresh.enabled and fresh.status != "active":
                    messages.warning(request, _t("Yoqilgan, lekin hali to'liq sozlanmagan — mijozlarga «Tez kunda» ko'rinadi."))
                return HttpResponseRedirect(request.path)
        base = _public_base(request)
        logs = PaymentCallbackLog.objects.filter(provider=registry.acquirer_for(row.provider) if row.provider in registry.CARD_BRANDS else row.provider)[:8]
        status = state.status
        label, color, icon = PROVIDER_STATUS[status]
        ctx = {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": str(state.spec.name), "row": row, "spec": state.spec, "state": state,
            "fields": form.fields(), "form_errors": form.errors, "can_change": can_change, "logo": _logo(row.provider),
            "status": {"key": status, "label": label, "color": color, "icon": icon},
            "callbacks": [(lbl, f"{base}{p}") for lbl, p in state.spec.callbacks],
            "missing": [str(next(f.label for f in state.spec.fields if f.key == k)) for k in state.missing] if row.provider not in registry.CARD_BRANDS else [],
            "logs": [{"l": lg, "ok": not lg.error_code, "when": timezone.localtime(lg.created_at).strftime("%d.%m %H:%M:%S")} for lg in logs],
            "route_state": registry.load(state.route) if state.route else None,
            "acquirers": [(k, registry.provider_label(k), registry.load(k).status) for k in registry.ACQUIRERS],
            "min_amount": row.min_amount.normalize() if row.min_amount is not None else "", "max_amount": row.max_amount.normalize() if row.max_amount else "",
            "post": request.POST if request.method == "POST" else None,
            "selftest_url": reverse("admin:payment_paymentproviderconfig_selftest", args=[row.provider]) if row.provider in registry.ACQUIRERS else "",
            "updated_by": row.updated_by, "updated_at": row.updated_at,
        }
        return render(request, "admin/payment/provider_form.html", ctx)

    # ------------------------------------------------------------------ connection self-test
    def selftest_view(self, request, key: str):
        """
        Calls our own callback handler in-process exactly as the provider would, signed with the stored
        credentials, for a non-existent order. "Order not found" proves the endpoint, the signature/auth and
        the stored secrets all work; an auth/signature error means the secrets don't match.
        """
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied
        if key not in registry.ACQUIRERS:
            return JsonResponse({"ok": False, "message": _t("Bu usul uchun test yo'q.")})
        state = registry.load(key)
        if state.missing:
            return JsonResponse({"ok": False, "message": _t("Avval majburiy maydonlarni to'ldiring.")})
        probe = "NZ-SELFTEST-0000"
        if key == "payme":
            from apps.payment.infrastructure.providers import payme

            secret = state.value("test_key") if state.test_mode else state.value("key")
            auth = "Basic " + base64.b64encode(f"Paycom:{secret}".encode()).decode()
            answer, _p, _o = payme.handle({"id": 1, "method": "CheckPerformTransaction", "params": {"amount": 100000, "account": {state.value("account_field"): probe}}}, auth)
            code = (answer.get("error") or {}).get("code")
            ok = code == payme.ERR_ORDER
        elif key == "click":
            from apps.payment.infrastructure.providers import click

            data = {"click_trans_id": "1", "service_id": state.value("service_id"), "click_paydoc_id": "1", "merchant_trans_id": probe, "amount": "1000.00",
                    "action": "0", "error": "0", "error_note": "", "sign_time": timezone.now().strftime("%Y-%m-%d %H:%M:%S")}
            data["sign_string"] = click.signature(state, data, with_prepare_id=False)
            answer, _p = click.prepare(data)
            code = answer.get("error")
            ok = code == click.ERR_ORDER
        else:
            from apps.payment.infrastructure.providers import uzum

            auth = "Basic " + base64.b64encode(f"{state.value('login')}:{state.value('password')}".encode()).decode()
            answer, _p, _o, _s = uzum.handle("check", {"serviceId": state.value("service_id"), "timestamp": 0, "params": {uzum.ORDER_PARAM: probe}}, auth)
            code = answer.get("errorCode")
            ok = code == uzum.ERR_ORDER
        return JsonResponse({
            "ok": ok, "code": code,
            "message": _t("Ulanish ishlayapti: endpoint, imzo va kalitlar to'g'ri.") if ok else _t("Kutilmagan javob — kalitlarni tekshiring (kod %s).") % code,
            "answer": json.dumps(answer, ensure_ascii=False, indent=2)[:1500],
        })


# ====================================================================== transactions


class TxnStatusFilter(admin.SimpleListFilter):
    title = _("Holat")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [(k, v[0]) for k, v in STATUS_STYLE.items()]

    def queryset(self, request, queryset):
        return queryset.filter(status=self.value()) if self.value() else queryset


@admin.register(PaymentModel)
class PaymentTransactionAdmin(ExcelExportMixin, admin.ModelAdmin):
    excel_title = "To'lovlar"
    excel_columns = [
        Col("Sana", "created_at", 17), Col("To'langan", "paid_at", 17), Col("Buyurtma", "order_number", 18),
        Col("Mijoz", lambda p: p.x_customer[0], 24), Col("Telefon", lambda p: p.x_customer[1], 16),
        Col("Tizim", "provider", 12), Col("Usul", "method", 12), Col("Holat", lambda p: str(STATUS_STYLE.get(p.status, (p.status,))[0]), 14),
        Col("Summa (so'm)", "amount", 15, money=True), Col("Provayder ID", "provider_reference", 26), Col("Xato sababi", "failure_reason", 28),
        Col("Sinov", "is_test", 8),
    ]

    def excel_prepare(self, objs):
        who = xl.people(p.customer_id for p in objs)
        for p in objs:
            p.x_customer = who.get(p.customer_id, ("", ""))

    list_display = ("order_number", "provider", "amount", "status", "created_at")
    list_filter = (TxnStatusFilter, "provider", "method", "is_test")
    search_fields = ("order_number", "provider_reference")
    list_per_page = 30
    ordering = ("-created_at",)
    change_list_template = "admin/payment/transactions.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        v = self.admin_site.admin_view
        return [path("<uuid:pk>/cancel/", v(self.cancel_view), name="payment_paymentmodel_cancel"), *super().get_urls()]

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        rows = list(cl.result_list)
        users = _customers({r.customer_id for r in rows})
        for p in rows:
            key = p.method or p.provider
            p.nz = {"style": _style(p.status), "logo": _logo(key if key in registry.SPECS else "cash"), "method": registry.provider_label(key),
                    "via": registry.provider_label(p.provider) if p.method in registry.CARD_BRANDS else "", "amount": _money(p.amount),
                    "user": users.get(p.customer_id), "when": timezone.localtime(p.created_at).strftime("%d.%m.%Y %H:%M"),
                    "paid": timezone.localtime(p.paid_at).strftime("%d.%m %H:%M") if p.paid_at else ""}
        return cl

    def changelist_view(self, request, extra_context=None):
        now = timezone.now()
        today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        qs = PaymentModel.objects.exclude(provider="cash")
        paid = qs.filter(status=PaymentStatusChoices.SUCCEEDED)
        week = now - timedelta(days=7)
        tried = qs.filter(created_at__gte=week).exclude(provider_reference__isnull=True)
        counts = dict(qs.values_list("status").annotate(n=Count("id")))
        current = request.GET.get("status", "")
        tabs = [("", _t("Barchasi"), "#64748b", "fa-layer-group", sum(counts.values()))] + [(k, str(v[0]), v[1], v[2], counts.get(k, 0)) for k, v in STATUS_STYLE.items()]
        providers = [(k, registry.provider_label(k)) for k in registry.ACQUIRERS]
        extra = {
            "title": _t("Tranzaksiyalar"), "recon": reconciliation_banner(), "tabs": tabs, "current": current, "q": request.GET.get("q", ""), "provider": request.GET.get("provider__exact", ""), "providers": providers,
            "kpi": {
                "today": _money(_volume(paid.filter(paid_at__gte=today))["sum"]), "today_count": paid.filter(paid_at__gte=today).count(),
                "week": _money(_volume(paid.filter(paid_at__gte=week))["sum"]), "avg": _money((_volume(paid)["sum"] / paid.count()) if paid.count() else 0),
                "success": round(tried.filter(status=PaymentStatusChoices.SUCCEEDED).count() * 100 / tried.count()) if tried.count() else None,
                "pending": counts.get("pending", 0), "refunded": _money(_volume(qs.filter(status=PaymentStatusChoices.REFUNDED))["sum"]),
            },
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        p = get_object_or_404(PaymentModel, pk=object_id)
        from apps.ordering.infrastructure.models import OrderModel

        order = OrderModel.objects.filter(id=p.order_id).only("id", "order_number", "status").first()
        user = _customers({p.customer_id}).get(p.customer_id)
        key = p.method or p.provider
        logs = list(PaymentCallbackLog.objects.filter(Q(payment=p) | Q(order_number=p.order_number, provider=p.provider)).order_by("created_at")[:60]) if p.order_number else list(p.callbacks.order_by("created_at"))
        state_names = {1: _t("Yaratilgan (1)"), 2: _t("Bajarilgan (2)"), -1: _t("Bajarilmasdan bekor (-1)"), -2: _t("Bajarilgandan keyin bekor (-2)")}

        def ms(v):
            return timezone.localtime(timezone.datetime.fromtimestamp(v / 1000, tz=timezone.get_current_timezone())).strftime("%d.%m.%Y %H:%M:%S") if v else "—"

        facts = [
            (_t("Provayder ID"), p.provider_reference.split(":", 1)[1] if p.provider_reference else "—"),
            (_t("Bizning ID"), str(p.pk)),
            (_t("Usul"), registry.provider_label(key) + (f" → {registry.provider_label(p.provider)}" if p.method in registry.CARD_BRANDS else "")),
            (_t("Provayder holati"), state_names.get(p.provider_state, "—")),
            (_t("Yaratilgan"), timezone.localtime(p.created_at).strftime("%d.%m.%Y %H:%M:%S")),
            (_t("To'langan"), timezone.localtime(p.paid_at).strftime("%d.%m.%Y %H:%M:%S") if p.paid_at else "—"),
            (_t("Bekor qilingan"), timezone.localtime(p.cancelled_at).strftime("%d.%m.%Y %H:%M:%S") if p.cancelled_at else "—"),
        ]
        if p.provider == "payme":
            facts += [("create_time", ms(p.provider_created_at)), ("perform_time", ms(p.provider_performed_at)), ("cancel_time", ms(p.provider_cancelled_at))]
            if p.cancel_reason is not None:
                facts.append((_t("Bekor sababi"), str(p.cancel_reason)))
        if p.prepare_id:
            facts.append(("merchant_prepare_id", str(p.prepare_id)))
        if p.failure_reason:
            facts.append((_t("Izoh"), p.failure_reason))
        timeline = [{
            "l": lg, "ok": not lg.error_code, "when": timezone.localtime(lg.created_at).strftime("%d.%m.%Y %H:%M:%S"),
            "req": json.dumps(lg.request, ensure_ascii=False, indent=2)[:4000], "res": json.dumps(lg.response, ensure_ascii=False, indent=2)[:4000],
        } for lg in logs]
        return render(request, "admin/payment/transaction_detail.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": p.order_number or str(p.pk), "p": p, "order": order, "customer": user,
            "style": _style(p.status), "logo": _logo(key if key in registry.SPECS else "cash"), "amount": _money(p.amount), "facts": facts, "timeline": timeline,
            "can_cancel": p.status == PaymentStatusChoices.CREATED and not p.provider_reference and self.has_change_permission(request, p),
            "order_url": reverse("admin:ordering_ordermodel_change", args=[order.pk]) if order else "",
        })

    def cancel_view(self, request, pk):
        """Closes a checkout attempt the customer never paid (no provider transaction yet)."""
        if request.method != "POST" or not self.has_change_permission(request):
            raise PermissionDenied
        from apps.payment.infrastructure import service

        p = get_object_or_404(PaymentModel, pk=pk)
        if p.status == PaymentStatusChoices.CREATED and not p.provider_reference:
            service.mark_cancelled(p, f"Dashboard: {request.user.get_username()}")
            messages.success(request, _t("Urinish bekor qilindi."))
        else:
            messages.error(request, _t("Provayderda boshlangan tranzaksiyani faqat provayder bekor qiladi."))
        return HttpResponseRedirect(reverse("admin:payment_paymentmodel_change", args=[pk]))


def _customers(ids) -> dict:
    from apps.identity.infrastructure.models import User

    return {u.id: u for u in User.objects.filter(id__in={i for i in ids if i}).only("id", "full_name", "phone_number")}


# ====================================================================== callback journal


@admin.register(PaymentCallbackLog)
class PaymentCallbackLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "provider", "method", "error_code")
    list_filter = ("provider",)
    search_fields = ("order_number", "method")
    list_per_page = 40
    change_list_template = "admin/payment/callbacks.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.GET.get("errors") == "1":
            qs = qs.filter(error_code__isnull=False).exclude(error_code=0)
        return qs

    def get_changelist_instance(self, request):
        request.GET = request.GET.copy()
        errors_only = request.GET.pop("errors", None)
        cl = super().get_changelist_instance(request)
        if errors_only:
            request.GET["errors"] = errors_only[0]
        for lg in cl.result_list:
            lg.nz = {"ok": not lg.error_code, "logo": _logo(lg.provider), "name": registry.provider_label(lg.provider),
                     "when": timezone.localtime(lg.created_at).strftime("%d.%m.%Y %H:%M:%S"),
                     "req": json.dumps(lg.request, ensure_ascii=False, indent=2)[:4000], "res": json.dumps(lg.response, ensure_ascii=False, indent=2)[:4000]}
        return cl

    def changelist_view(self, request, extra_context=None):
        day = timezone.now() - timedelta(days=1)
        extra = {
            "title": _t("Callback jurnali"), "recon": reconciliation_banner(), "errors_only": request.GET.get("errors") == "1", "provider": request.GET.get("provider__exact", ""),
            "providers": [(k, registry.provider_label(k)) for k in registry.ACQUIRERS], "q": request.GET.get("q", ""),
            "kpi": {"day": PaymentCallbackLog.objects.filter(created_at__gte=day).count(),
                    "errors": PaymentCallbackLog.objects.filter(created_at__gte=day, error_code__isnull=False).exclude(error_code=0).count()},
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})



# ====================================================================== reconciliation


ISSUE_STYLE = {"critical": ("#e11d48", "fa-circle-exclamation"), "warning": ("#f59e0b", "fa-triangle-exclamation"), "info": ("#0ea5e9", "fa-circle-info")}


def reconciliation_banner() -> dict:
    open_qs = PaymentReconciliationIssue.objects.filter(status=ReconciliationStatus.OPEN)
    return {"critical": open_qs.filter(severity="critical").count(), "total": open_qs.count(), "last": PaymentSettings.load().last_reconciled_at}


@admin.register(PaymentReconciliationIssue)
class ReconciliationAdmin(admin.ModelAdmin):
    list_display = ("kind", "severity", "status", "order_number", "created_at")
    list_filter = ("status", "severity", "provider")
    search_fields = ("order_number", "kind")
    list_per_page = 30
    change_list_template = "admin/payment/reconciliation.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path("run/", v(self.run_view), name="payment_paymentreconciliationissue_run"),
            path("<int:pk>/close/", v(self.close_view), name="payment_paymentreconciliationissue_close"),
            *super().get_urls(),
        ]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("payment", "resolved_by")
        if "status__exact" not in request.GET and "all" not in request.GET:
            qs = qs.filter(status=ReconciliationStatus.OPEN)
        return qs

    def get_changelist_instance(self, request):
        request.GET = request.GET.copy()
        show_all = request.GET.pop("all", None)
        cl = super().get_changelist_instance(request)
        if show_all:
            request.GET["all"] = show_all[0]
        from apps.payment.infrastructure.reconcile import KINDS

        for i in cl.result_list:
            _sev, title, advice = KINDS.get(i.kind, ("info", i.kind, ""))
            color, icon = ISSUE_STYLE.get(i.severity, ("#64748b", "fa-circle"))
            i.nz = {"title": title, "advice": advice, "color": color, "icon": icon, "when": timezone.localtime(i.created_at).strftime("%d.%m.%Y %H:%M"),
                    "amount": _money(i.amount) if i.amount is not None else "", "details": json.dumps(i.details, ensure_ascii=False)[:300] if i.details else "",
                    "logo": _logo(i.provider) if i.provider in registry.SPECS else ""}
        return cl

    def changelist_view(self, request, extra_context=None):
        cfg = PaymentSettings.load()
        open_qs = PaymentReconciliationIssue.objects.filter(status=ReconciliationStatus.OPEN)
        extra = {
            "title": _t("Solishtirish"), "cfg": cfg, "summary": cfg.last_reconcile_summary or {}, "show_all": "all" in request.GET or "status__exact" in request.GET,
            "kpi": {"critical": open_qs.filter(severity="critical").count(), "warning": open_qs.filter(severity="warning").count(),
                    "resolved": PaymentReconciliationIssue.objects.exclude(status=ReconciliationStatus.OPEN).count(),
                    "amount": _money(open_qs.filter(severity="critical").aggregate(s=Sum("amount"))["s"])},
            "can_change": request.user.has_perm("payment.change_paymentreconciliationissue"),
        }
        return super().changelist_view(request, {**extra, **(extra_context or {})})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("admin:payment_paymentreconciliationissue_changelist"))

    def run_view(self, request):
        if request.method != "POST" or not request.user.has_perm("payment.change_paymentreconciliationissue"):
            raise PermissionDenied
        from apps.payment.infrastructure import reconcile

        summary = reconcile.run()
        messages.success(request, _t("Tekshiruv tugadi: %(n)s ta to'lov, %(o)s ta ochiq muammo.") % {"n": summary["checked"], "o": summary["open"]})
        return HttpResponseRedirect(reverse("admin:payment_paymentreconciliationissue_changelist"))

    def close_view(self, request, pk):
        if request.method != "POST" or not request.user.has_perm("payment.change_paymentreconciliationissue"):
            raise PermissionDenied
        issue = get_object_or_404(PaymentReconciliationIssue, pk=pk)
        issue.status = ReconciliationStatus.IGNORED if request.POST.get("to") == "ignored" else ReconciliationStatus.RESOLVED
        issue.resolved_at, issue.resolved_by = timezone.now(), request.user
        issue.resolution_note = (request.POST.get("note") or "").strip()[:255]
        issue.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_note"])
        messages.success(request, _t("Belgilandi."))
        return HttpResponseRedirect(reverse("admin:payment_paymentreconciliationissue_changelist"))
