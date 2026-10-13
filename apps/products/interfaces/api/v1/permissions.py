"""
Products API permission classes.

Reuses Identity's RBAC engine exactly: `common.permissions.
HasPermissionCode.resolver` is wired once, globally, at Django startup
by `apps.identity.apps.IdentityConfig.ready()` to Identity's
`CheckPermission` application service (Redis-cached, per-user
effective-permission-code resolution). This module never re-implements
permission checking -- every class below is a thin, named wrapper
calling that same resolver with a Products-specific permission code,
giving the distinctly-named classes this module's brief asks for
(CatalogViewPermission, CatalogManagePermission, ...) without
duplicating Identity's RBAC engine.

Permission codes follow the platform-wide `<context>.<resource>.
<action>` convention (Enterprise REST API Blueprint §14).
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class _ProductsPermission(BasePermission):
    """Base class -- subclasses set `permission_code`."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed, matching common.permissions.HasPermissionCode's own rule
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        from common.permissions import HasPermissionCode

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class CatalogViewPermission(_ProductsPermission):
    """Staff read access to admin catalog endpoints (list/detail/filters preview)."""

    permission_code = "products.product.view"


class CatalogManagePermission(_ProductsPermission):
    """Create/update product core fields, associations, content."""

    permission_code = "products.product.manage"


class CatalogPublishPermission(_ProductsPermission):
    """Publish/hide/restore -- a narrower grant than general manage, per Enterprise REST API Blueprint §14's principle that publish is a higher-blast-radius action than a routine edit."""

    permission_code = "products.product.publish"


class CatalogArchivePermission(_ProductsPermission):
    """Archive/delete -- the highest-blast-radius product action, kept separate from Publish."""

    permission_code = "products.product.archive"


class CatalogMediaPermission(_ProductsPermission):
    permission_code = "products.media.manage"


class CatalogSEOPermission(_ProductsPermission):
    permission_code = "products.seo.manage"


class VariantPermission(_ProductsPermission):
    permission_code = "products.variant.manage"


class CategoryPermission(_ProductsPermission):
    permission_code = "products.category.manage"


class BrandPermission(_ProductsPermission):
    permission_code = "products.brand.manage"
