"""apps/content/interfaces/api/v1/urls.py"""
from __future__ import annotations

from django.urls import path

from apps.content.interfaces.api.v1 import views

app_name = "content"

urlpatterns = [
    path("categories", views.BlogCategoryListView.as_view(), name="blog-category-list"),
    path("posts", views.BlogPostListView.as_view(), name="blog-post-list"),
    path("posts/<slug:slug>", views.BlogPostDetailView.as_view(), name="blog-post-detail"),
]
