from django.urls import path

from . import views

app_name = "exchange"

urlpatterns = [
    path("requests/", views.request_list, name="list"),
    path("requests/new/<str:username>/", views.request_create, name="create"),
    path("requests/<int:pk>/", views.request_detail, name="detail"),
    # action is one of: accept, reject, cancel, complete (POST only)
    path("requests/<int:pk>/<slug:action>/", views.request_action, name="action"),
    path("requests/<int:pk>/sessions/new/", views.session_create, name="session_create"),
    path("sessions/", views.session_list, name="sessions"),
    path("activity/", views.activity, name="activity"),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/calendar.ics", views.session_calendar, name="session_calendar"),
    path("sessions/<int:pk>/review/", views.session_review, name="session_review"),
    # action is one of: complete, cancel (POST only)
    path("sessions/<int:pk>/<slug:action>/", views.session_action, name="session_action"),
]
