from django.contrib import admin

from .models import ExchangeRequest, LearningSession, Review


class LearningSessionInline(admin.TabularInline):
    model = LearningSession
    extra = 0
    fields = ("skill", "teacher", "learner", "scheduled_at", "duration_minutes", "mode", "status")
    readonly_fields = ("teacher", "learner")
    show_change_link = True


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    fields = ("reviewer", "reviewee", "rating", "comment")
    readonly_fields = ("reviewee",)


@admin.register(ExchangeRequest)
class ExchangeRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "sender", "receiver", "requested_skill", "offered_skill", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("sender__username", "receiver__username", "requested_skill__name", "offered_skill__name")
    list_select_related = ("sender", "receiver", "requested_skill", "offered_skill")
    autocomplete_fields = ("sender", "receiver", "requested_skill", "offered_skill")
    readonly_fields = ("created_at", "responded_at", "completed_at")
    date_hierarchy = "created_at"
    inlines = (LearningSessionInline,)


@admin.register(LearningSession)
class LearningSessionAdmin(admin.ModelAdmin):
    list_display = ("skill", "teacher", "learner", "scheduled_at", "duration_minutes", "mode", "status")
    list_filter = ("status", "mode", "scheduled_at")
    search_fields = ("skill__name", "teacher__username", "learner__username")
    list_select_related = ("skill", "teacher", "learner")
    readonly_fields = ("teacher", "learner", "created_at", "completed_at")
    date_hierarchy = "scheduled_at"
    inlines = (ReviewInline,)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("session", "reviewer", "reviewee", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("reviewer__username", "reviewee__username", "comment")
    list_select_related = ("session__skill", "reviewer", "reviewee")
    readonly_fields = ("reviewee", "created_at")
