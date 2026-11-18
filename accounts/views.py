from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from exchange.models import ExchangeRequest, LearningSession, Review
from exchange.selectors import rating_summary, sessions_for
from skills.models import UserSkill
from skills.services import find_matches

from .forms import ProfileForm, SignUpForm, UserUpdateForm

User = get_user_model()


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome to SkillSwap, {user.first_name}! Add a few skills so we can find you a match.")
        return redirect("skills:my_skills")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def dashboard(request):
    user = request.user
    now = timezone.now()
    sessions = sessions_for(user).select_related("skill", "teacher__profile", "learner__profile")
    incoming = (
        ExchangeRequest.objects.filter(receiver=user, status=ExchangeRequest.Status.PENDING)
        .select_related("sender__profile", "requested_skill", "offered_skill")
    )
    completion, missing_steps = user.profile.completion_details()

    context = {
        "completion": completion,
        "missing_steps": missing_steps,
        "rating": rating_summary(user),
        "incoming_requests": incoming[:5],
        "upcoming_sessions": sessions.filter(
            status=LearningSession.Status.SCHEDULED, scheduled_at__gte=now
        )[:5],
        "sessions_to_confirm": sessions.filter(
            status=LearningSession.Status.SCHEDULED, scheduled_at__lt=now
        ).count(),
        "sessions_to_review": sessions.filter(status=LearningSession.Status.COMPLETED)
        .exclude(reviews__reviewer=user)
        .order_by("-scheduled_at")[:5],
        "stats": {
            "incoming": incoming.count(),
            "active": ExchangeRequest.objects.involving(user)
            .filter(status=ExchangeRequest.Status.ACCEPTED)
            .count(),
            "taught": sessions.filter(status=LearningSession.Status.COMPLETED, teacher=user).count(),
            "learned": sessions.filter(status=LearningSession.Status.COMPLETED, learner=user).count(),
        },
        "offers": user.user_skills.filter(kind=UserSkill.Kind.OFFER).select_related("skill"),
        "wants": user.user_skills.filter(kind=UserSkill.Kind.WANT).select_related("skill"),
        "matches": find_matches(user),
    }
    return render(request, "accounts/dashboard.html", context)


def profile_detail(request, username):
    person = get_object_or_404(User.objects.select_related("profile"), username=username, is_active=True)
    entries = list(person.user_skills.select_related("skill__category"))
    is_own = request.user == person

    # Highlight overlaps with the person who's looking at the profile.
    viewer_wants, viewer_offers = set(), set()
    if request.user.is_authenticated and not is_own:
        for skill_id, kind in request.user.user_skills.values_list("skill_id", "kind"):
            (viewer_wants if kind == UserSkill.Kind.WANT else viewer_offers).add(skill_id)

    context = {
        "person": person,
        "is_own": is_own,
        "offers": [e for e in entries if e.kind == UserSkill.Kind.OFFER],
        "wants": [e for e in entries if e.kind == UserSkill.Kind.WANT],
        "viewer_wants": viewer_wants,
        "viewer_offers": viewer_offers,
        "rating": rating_summary(person),
        "reviews": Review.objects.filter(reviewee=person)
        .select_related("reviewer__profile", "session__skill")[:10],
        "completed_sessions": sessions_for(person)
        .filter(status=LearningSession.Status.COMPLETED)
        .count(),
    }
    return render(request, "accounts/profile_detail.html", context)


@login_required
def profile_edit(request):
    user_form = UserUpdateForm(request.POST or None, instance=request.user)
    profile_form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile)
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("accounts:profile", username=request.user.username)
    return render(request, "accounts/profile_edit.html", {
        "user_form": user_form,
        "profile_form": profile_form,
    })
