from django.contrib import admin
from django.db.models import Count, Q

from .models import Category, Skill, UserSkill


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "skill_count")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_skill_count=Count("skills"))

    @admin.display(description="Skills", ordering="_skill_count")
    def skill_count(self, obj):
        return obj._skill_count


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "teacher_count", "learner_count")
    list_filter = ("category",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("category",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _teachers=Count("user_skills", filter=Q(user_skills__kind=UserSkill.Kind.OFFER)),
            _learners=Count("user_skills", filter=Q(user_skills__kind=UserSkill.Kind.WANT)),
        )

    @admin.display(description="Teachers", ordering="_teachers")
    def teacher_count(self, obj):
        return obj._teachers

    @admin.display(description="Learners", ordering="_learners")
    def learner_count(self, obj):
        return obj._learners


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "kind", "level", "created_at")
    list_filter = ("kind", "level", "skill__category")
    search_fields = ("user__username", "skill__name", "note")
    autocomplete_fields = ("user", "skill")
    list_select_related = ("user", "skill")
