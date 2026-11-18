from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("staff/reports/", views.reports, name="reports"),
    path("avatar/preview.svg", views.avatar_preview, name="avatar_preview"),
]
