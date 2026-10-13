"""
Reviews `/api/v1/reviews/...` URL routing.
"""
from __future__ import annotations

from django.urls import path

from apps.reviews.interfaces.api.v1 import views

app_name = "reviews"

urlpatterns = [
    path("", views.CreateReviewView.as_view(), name="review-create"),
    path("statistics", views.ReviewStatisticsView.as_view(), name="review-statistics"),
    path("featured", views.FeaturedReviewsView.as_view(), name="review-featured"),
    path("products/<str:product_id>", views.ProductReviewListView.as_view(), name="product-review-list"),
    path("products/<str:product_id>/public", views.PublicProductReviewListView.as_view(), name="product-review-list-public"),
    path("customers/<str:customer_id>", views.CustomerReviewListView.as_view(), name="customer-review-list"),
    path("admin", views.AdminReviewListView.as_view(), name="admin-review-list"),
    path("<str:review_id>", views.ReviewDetailView.as_view(), name="review-detail"),
    path("<str:review_id>/submit", views.SubmitReviewView.as_view(), name="review-submit"),
    path("<str:review_id>/edit", views.EditReviewView.as_view(), name="review-edit"),
    path("<str:review_id>/approve", views.ApproveReviewView.as_view(), name="review-approve"),
    path("<str:review_id>/reject", views.RejectReviewView.as_view(), name="review-reject"),
    path("<str:review_id>/publish", views.PublishReviewView.as_view(), name="review-publish"),
    path("<str:review_id>/hide", views.HideReviewView.as_view(), name="review-hide"),
    path("<str:review_id>/withdraw", views.WithdrawReviewView.as_view(), name="review-withdraw"),
    path("<str:review_id>/media", views.AttachReviewMediaView.as_view(), name="review-media"),
]
