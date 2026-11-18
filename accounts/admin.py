from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from skills.models import UserSkill

from .models import Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    max_num = 1


class UserSkillInline(admin.TabularInline):
    model = UserSkill
    extra = 0
    autocomplete_fields = ("skill",)
    fields = ("skill", "kind", "level", "note")


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline, UserSkillInline)
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "date_joined")

    def get_inline_instances(self, request, obj=None):
        # On the "add user" page the post_save signal creates the Profile, so hide the inlines
        # there to avoid creating a second one.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "headline", "location", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "headline", "location")
    list_select_related = ("user",)
    readonly_fields = ("created_at", "updated_at")
