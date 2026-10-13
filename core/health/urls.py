from django.urls import path

from core.health import views

urlpatterns = [
    path("live", views.liveness, name="health-live"),
    path("ready", views.readiness, name="health-ready"),
]
