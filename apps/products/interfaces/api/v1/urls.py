"""
Products `/api/v1/products/...` + `/api/v1/admin/products/...` URL
routing. Included from `config/urls/v1.py`. Kept RESTful per Enterprise
REST API Blueprint §3 -- resources are nouns, actions are POST-verbed
sub-paths only where no plain CRUD verb fits (publish/hide/archive/
restore/duplicate/clone), matching `apps/identity/interfaces/api/v1/
urls.py`'s pattern.
"""
from __future__ import annotations

from django.urls import path

from apps.products.interfaces.api.v1 import views, wishlist_views

app_name = "products"

urlpatterns = [
    # --- Public ---
    path("products", views.ProductListView.as_view(), name="products-list"),
    path("wishlist", wishlist_views.WishlistListView.as_view(), name="wishlist-list"),
    path("wishlist/<str:product_id>", wishlist_views.WishlistItemView.as_view(), name="wishlist-item"),
    path("products/search", views.ProductSearchView.as_view(), name="products-search"),
    path("products/search/popular", views.PopularSearchesView.as_view(), name="products-search-popular"),
    path("products/best-sellers", views.BestSellersView.as_view(), name="products-best-sellers"),
    path("products/goals", views.GoalListView.as_view(), name="products-goals"),
    path("products/recommendations", views.PersonalizedRecommendationsView.as_view(), name="products-personalized-recommendations"),
    path("products/recommendations/for-cart", views.CartRecommendationsView.as_view(), name="products-cart-recommendations"),
    path("products/variants", views.VariantDisplayView.as_view(), name="products-variant-display"),
    path("products/<str:slug>", views.ProductDetailView.as_view(), name="products-detail"),
    path("products/<str:slug>/recommendations", views.ProductRecommendationsView.as_view(), name="products-recommendations"),
    path("categories", views.CategoryListView.as_view(), name="categories-list"),
    path("categories/tree", views.CategoryTreeView.as_view(), name="categories-tree"),
    path("categories/<uuid:category_id>", views.CategoryDetailView.as_view(), name="categories-detail"),
    path("brands", views.BrandListView.as_view(), name="brands-list"),
    path("flavours", views.FlavourListView.as_view(), name="flavours-list"),
    path("packages", views.PackageListView.as_view(), name="packages-list"),
    path("tags", views.TagListView.as_view(), name="tags-list"),
    path("catalog/filters", views.CatalogFiltersView.as_view(), name="catalog-filters"),
    # --- Admin: product lifecycle ---
    path("admin/products", views.AdminProductListCreateView.as_view(), name="admin-products-list-create"),
    path("admin/products/statistics", views.ProductStatisticsView.as_view(), name="admin-products-statistics"),
    path("admin/products/top", views.TopProductsView.as_view(), name="admin-products-top"),
    path("admin/products/<str:product_id>", views.AdminProductDetailView.as_view(), name="admin-products-detail"),
    path("admin/products/<str:product_id>/publish", views.AdminProductPublishView.as_view(), name="admin-products-publish"),
    path("admin/products/<str:product_id>/hide", views.AdminProductHideView.as_view(), name="admin-products-hide"),
    path("admin/products/<str:product_id>/archive", views.AdminProductArchiveView.as_view(), name="admin-products-archive"),
    path("admin/products/<str:product_id>/restore", views.AdminProductRestoreView.as_view(), name="admin-products-restore"),
    path("admin/products/<str:product_id>/duplicate", views.AdminProductDuplicateView.as_view(), name="admin-products-duplicate"),
    path("admin/products/<str:product_id>/clone", views.AdminProductCloneView.as_view(), name="admin-products-clone"),
    # --- Admin: variants ---
    path("admin/products/<str:product_id>/variants", views.AdminVariantListCreateView.as_view(), name="admin-variants-create"),
    path("admin/products/<str:product_id>/variants/<str:variant_id>", views.AdminVariantDetailView.as_view(), name="admin-variants-detail"),
    path("admin/products/<str:product_id>/variants/<str:variant_id>/default", views.AdminVariantSetDefaultView.as_view(), name="admin-variants-set-default"),
    # --- Admin: media ---
    path("admin/products/<str:product_id>/images", views.AdminImageUploadView.as_view(), name="admin-images-upload"),
    path("admin/products/<str:product_id>/images/<str:image_id>", views.AdminImageDeleteView.as_view(), name="admin-images-delete"),
    path("admin/products/<str:product_id>/videos", views.AdminVideoUploadView.as_view(), name="admin-videos-upload"),
    path("admin/products/<str:product_id>/videos/<str:video_id>", views.AdminVideoDeleteView.as_view(), name="admin-videos-delete"),
    path("admin/products/<str:product_id>/documents", views.AdminDocumentUploadView.as_view(), name="admin-documents-upload"),
    path("admin/products/<str:product_id>/documents/<str:document_id>", views.AdminDocumentDeleteView.as_view(), name="admin-documents-delete"),
    # --- Admin: content ---
    path("admin/products/<str:product_id>/nutrition", views.AdminNutritionView.as_view(), name="admin-nutrition"),
    path("admin/products/<str:product_id>/ingredients", views.AdminIngredientsView.as_view(), name="admin-ingredients"),
    path("admin/products/<str:product_id>/warnings", views.AdminWarningsView.as_view(), name="admin-warnings"),
    path("admin/products/<str:product_id>/directions", views.AdminDirectionsView.as_view(), name="admin-directions"),
    path("admin/products/<str:product_id>/seo", views.AdminSEOView.as_view(), name="admin-seo"),
    # --- Admin: relations ---
    path("admin/products/<str:product_id>/brand", views.AdminAssignBrandView.as_view(), name="admin-assign-brand"),
    path("admin/products/<str:product_id>/category", views.AdminAssignCategoryView.as_view(), name="admin-assign-category"),
    path("admin/products/<str:product_id>/tags", views.AdminAssignTagsView.as_view(), name="admin-assign-tags"),
    path("admin/products/<str:product_id>/flavours", views.AdminAssignFlavoursView.as_view(), name="admin-assign-flavours"),
]
