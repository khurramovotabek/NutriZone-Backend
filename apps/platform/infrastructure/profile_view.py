"""Dashboard → Profil: the signed-in staff member's own page -- identity, role, activity feed, stats and quick edits."""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

TZ = ZoneInfo("Asia/Tashkent")
# The verb is a whole translatable sentence: word order differs between uz ("Mahsulot qo'shdi") and en ("Added product").
ACTION_META = {
    ADDITION: ("fa-plus", "#16a34a", gettext_lazy("%(model)s qo'shdi")),
    CHANGE: ("fa-pen", "#2563eb", gettext_lazy("%(model)s o'zgartirdi")),
    DELETION: ("fa-trash", "#dc2626", gettext_lazy("%(model)s o'chirdi")),
}


class ProfileForm(forms.Form):
    first_name = forms.CharField(label="Ism", max_length=150, required=False)
    last_name = forms.CharField(label="Familiya", max_length=150, required=False)
    email = forms.EmailField(label="Email", required=False)


def _local(dt, fmt="%d.%m.%Y %H:%M"):
    return timezone.localtime(dt, TZ).strftime(fmt) if dt else "—"


def profile_view(request):
    user = request.user
    if request.method == "POST":
        form = ProfileForm(request.POST)
        if form.is_valid():
            for f in ("first_name", "last_name", "email"):
                setattr(user, f, form.cleaned_data[f])
            user.save(update_fields=["first_name", "last_name", "email"])
            messages.success(request, "Profil yangilandi.")
            return HttpResponseRedirect(reverse("admin:nz_profile"))
    else:
        form = ProfileForm(initial={"first_name": user.first_name, "last_name": user.last_name, "email": user.email})

    logs = LogEntry.objects.filter(user=user).select_related("content_type")
    week = timezone.now() - timedelta(days=7)
    actor = user.get_full_name() or user.get_username()
    stats = {"actions": logs.count(), "week": logs.filter(action_time__gte=week).count()}
    try:
        from apps.stores.infrastructure.models import StockReceipt, StockTransfer

        stats["transfers"] = StockTransfer.objects.filter(created_by=actor).count()
        stats["receipts"] = StockReceipt.objects.filter(created_by=actor).count()
    except Exception:  # noqa: BLE001
        stats["transfers"] = stats["receipts"] = 0
    feed = []
    for e in logs.order_by("-action_time")[:15]:
        icon, tone, verb = ACTION_META.get(e.action_flag, ("fa-circle", "#64748b", "%(model)s"))
        model = e.content_type.name if e.content_type else ""
        try:
            url = e.get_admin_url()
        except Exception:  # noqa: BLE001
            url = ""
        feed.append({"icon": icon, "tone": tone, "title": str(verb) % {"model": model.capitalize()}, "object": e.object_repr, "when": _local(e.action_time), "url": url})
    name = user.get_full_name() or user.get_username()
    initials = "".join(p[0] for p in name.split()[:2]).upper() or "?"
    role = gettext("Superadmin") if user.is_superuser else gettext("Xodim")
    return render(request, "admin/profile.html", {
        **admin.site.each_context(request), "title": gettext("Profil"),
        "form": form, "stats": stats, "feed": feed, "initials": initials, "display_name": name, "role": role,
        "groups": list(user.groups.values_list("name", flat=True)),
        "joined": _local(user.date_joined, "%d.%m.%Y"), "last_login": _local(user.last_login),
    })
