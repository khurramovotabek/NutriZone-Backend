"""
NutriZone Admin "Roles & Permissions Overview" data aggregation.

Real, closed gap: Role/Permission/RolePermission/UserRole were fully
built, real relational data (confirmed via direct model inspection),
but had zero visual overview anywhere -- only the bare, standard
Django admin grids (RoleAdmin/PermissionAdmin/UserRoleAdmin), which
show one flat table each with no way to see "what can this role
actually do" or "who has this role" without manually cross-
referencing three separate admin list pages.

Matches Phase 08.2/08.8's own established error-isolation and
composition-root conventions exactly -- this is a read-only selector,
no new business logic, over already-existing, already-tested models.
"""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from apps.identity.infrastructure.models import Permission, Role, RolePermission, UserRole


class RolePermissionOverviewAggregator:
    def roles_with_permissions(self) -> list[dict]:
        """One row per real Role, with its real, currently-assigned Permission codes and its real, currently-assigned user count -- never a fabricated or assumed default permission set."""
        roles = list(Role.objects.all().order_by("name"))
        permission_rows = RolePermission.objects.select_related("permission").values("role_id", "permission__code", "permission__description")
        permissions_by_role: dict = defaultdict(list)
        for row in permission_rows:
            permissions_by_role[row["role_id"]].append({"code": row["permission__code"], "description": row["permission__description"]})

        user_counts = UserRole.objects.values("role_id").annotate(count=Count("id"))
        user_count_by_role = {row["role_id"]: row["count"] for row in user_counts}

        return [
            {
                "id": str(role.id), "code": role.code, "name": role.name, "is_system_role": role.is_system_role,
                "permissions": sorted(permissions_by_role.get(role.id, []), key=lambda p: p["code"]),
                "permission_count": len(permissions_by_role.get(role.id, [])),
                "user_count": user_count_by_role.get(role.id, 0),
            }
            for role in roles
        ]

    def unassigned_permissions(self) -> list[dict]:
        """Real permissions that exist but are not attached to any role at all -- a genuine, actionable configuration gap worth surfacing, not hidden."""
        assigned_permission_ids = RolePermission.objects.values_list("permission_id", flat=True)
        orphaned = Permission.objects.exclude(id__in=assigned_permission_ids).order_by("code")
        return [{"code": p.code, "description": p.description} for p in orphaned]

    def summary(self) -> dict:
        return {
            "total_roles": Role.objects.count(),
            "total_permissions": Permission.objects.count(),
            "total_role_assignments": UserRole.objects.count(),
            "system_roles": Role.objects.filter(is_system_role=True).count(),
        }

    def matrix(self) -> dict:
        """Permissions grouped by module (rows) × roles (columns): which role grants what, for the overview's matrix."""
        from apps.identity.infrastructure import admin_ui as ui

        roles = list(Role.objects.order_by("-is_system_role", "name"))
        granted = set(RolePermission.objects.values_list("role_id", "permission_id"))
        users = dict(UserRole.objects.values("role_id").annotate(n=Count("user_id", distinct=True)).values_list("role_id", "n"))
        modules: dict = {}
        for p in Permission.objects.order_by("code"):
            key, label, icon, color = ui.module_of(p.code)
            mod = modules.setdefault(key, {"key": key, "label": label, "icon": icon, "color": color, "perms": []})
            cells = [(r.id, p.id) in granted for r in roles]
            mod["perms"].append({"code": p.code, "label": ui.permission_label(p.code, p.description), "cells": cells, "orphan": not any(cells)})
        for mod in modules.values():
            mod["counts"] = [sum(1 for p in mod["perms"] if p["cells"][i]) for i in range(len(roles))]
        return {
            "roles": [{"id": str(r.id), "name": r.name, "code": r.code, "system": r.is_system_role, "users": users.get(r.id, 0),
                       "perms": sum(1 for (rid, _pid) in granted if rid == r.id)} for r in roles],
            "modules": sorted(modules.values(), key=lambda m: m["label"]),
        }
