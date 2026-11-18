from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from exchange.models import ExchangeRequest, LearningSession, Review
from exchange.selectors import ratings_by_user
from skills.models import Category, Skill, UserSkill
from skills.services import skills_with_counts
from skills.views import index_context

from .geo import swap_map_data
from .pixel_avatar import options_for, render_svg
from .templatetags.swap_tags import avatar_colour

User = get_user_model()


def _member_cards(limit=10):
    """Recently joined members who have listed at least one skill, ready for the card strip."""
    people = (
        User.objects.filter(is_active=True, user_skills__isnull=False)
        .distinct()
        .select_related("profile")
        .prefetch_related("user_skills__skill__category")
        .order_by("-date_joined")[:limit]
    )
    ratings = ratings_by_user([p.pk for p in people])
    cards = []
    for person in people:
        entries = list(person.user_skills.all())
        teaches = [e.skill for e in entries if e.kind == UserSkill.Kind.OFFER]
        cards.append({
            "user": person,
            "teaches": teaches,
            "wants": [e.skill for e in entries if e.kind == UserSkill.Kind.WANT],
            "category": teaches[0].category.name if teaches else "Learner",
            "rating": ratings.get(person.pk, {}).get("avg"),
        })
    return cards


def home(request):
    featured = (
        Review.objects.exclude(comment="")
        .filter(rating__gte=4)
        .select_related(
            "reviewer", "reviewee__profile", "session__skill",
            "session__exchange__requested_skill", "session__exchange__offered_skill",
        )
        .order_by("-created_at")
        .first()
    )
    context = {
        "stats": {
            "members": User.objects.filter(is_active=True).count(),
            "skills": Skill.objects.count(),
            "categories": Category.objects.count(),
            "sessions": LearningSession.objects.filter(status=LearningSession.Status.COMPLETED).count(),
        },
        "members": _member_cards(),
        "featured": featured,
        "swap_map": swap_map_data(),
    }
    context.update(index_context(request))
    return render(request, "core/home.html", context)


@staff_member_required
def reports(request):
    """Platform health at a glance for admins: growth, the request funnel, sessions and skill demand."""
    now = timezone.now()
    users = User.objects.filter(is_active=True)

    by_status = dict(ExchangeRequest.objects.values_list("status").annotate(n=Count("id")))
    total_requests = sum(by_status.values())
    status_rows = [
        {"label": label, "key": key, "n": by_status.get(key, 0),
         "pct": round(by_status.get(key, 0) * 100 / total_requests) if total_requests else 0}
        for key, label in ExchangeRequest.Status.choices
    ]
    agreed = by_status.get("accepted", 0) + by_status.get("completed", 0)
    answered = agreed + by_status.get("rejected", 0)

    done = LearningSession.objects.filter(status=LearningSession.Status.COMPLETED)
    minutes = done.aggregate(total=Sum("duration_minutes"))["total"] or 0
    rating = Review.objects.aggregate(avg=Avg("rating"), n=Count("id"))

    skills = list(skills_with_counts().filter(Q(teacher_count__gt=0) | Q(learner_count__gt=0)))
    for s in skills:
        s.gap = s.learner_count - s.teacher_count
    demand = sorted(skills, key=lambda s: (-s.gap, -s.learner_count, s.name))[:8]

    teachers = list(
        users.annotate(taught=Count("sessions_taught", filter=Q(sessions_taught__status=LearningSession.Status.COMPLETED)))
        .filter(taught__gt=0).select_related("profile").order_by("-taught", "username")[:5]
    )
    ratings = ratings_by_user([t.pk for t in teachers])
    for t in teachers:
        t.rating = ratings.get(t.pk, {"avg": None, "count": 0})

    return render(request, "core/reports.html", {
        "numbers": {
            "members": users.count(),
            "new_members": users.filter(date_joined__gte=now - timedelta(days=30)).count(),
            "requests": total_requests,
            "acceptance": round(agreed * 100 / answered) if answered else None,
            "sessions": done.count(),
            "hours": minutes / 60,
            "upcoming": LearningSession.objects.filter(status=LearningSession.Status.SCHEDULED, scheduled_at__gt=now).count(),
            "rating_avg": rating["avg"],
            "reviews": rating["n"],
        },
        "status_rows": status_rows,
        "demand": demand,
        "teachers": teachers,
        "newest": users.select_related("profile").order_by("-date_joined")[:6],
    })


@login_required
def avatar_preview(request):
    """Live preview for the pixel-avatar picker in Edit profile. Blank options use the member's defaults."""
    defaults = options_for(request.user.profile)
    pick = lambda key, param: request.GET.get(param) or defaults[key]  # noqa: E731
    svg = render_svg(pick("hair", "hair"), pick("skin", "skin"), pick("hair_colour", "colour"),
                     pick("extra", "extra"), avatar_colour(request.user), 160)
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "private, max-age=3600"
    return response
