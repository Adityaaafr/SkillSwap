from django.urls import path

from . import views

app_name = "skills"

urlpatterns = [
    path("skills/", views.skill_list, name="list"),
    path("skills/<slug:slug>/", views.skill_detail, name="detail"),
    path("my-skills/", views.my_skills, name="my_skills"),
    path("my-skills/<int:pk>/delete/", views.my_skill_delete, name="my_skill_delete"),
]
