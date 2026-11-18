from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from exchange.selectors import ratings_by_user

from .forms import UserSkillForm
from .models import Category, Skill, UserSkill
from .services import number_skills, skill_ids_for, skills_with_counts

User = get_user_model()

# (key, label, ordering). "default" keeps the catalogue order and groups rows by category.
SORT_OPTIONS = [
    ("default", "Default", ("category__name", "name")),
    ("teachers", "Most teachers", ("-teacher_count", "name")),
    ("wanted", "Most wanted", ("-learner_count", "name")),
    ("az", "Name A–Z", ("name",)),
    ("za", "Name Z–A", ("-name",)),
]


def _safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return target
    return fallback


def index_context(request, query="", category=None, sort="default"):
    """Everything the skill index table needs. Shared by Explore and the home page."""
    orderings = {key: order for key, _, order in SORT_OPTIONS}
    if sort not in orderings:
        sort = "default"

    skills = skills_with_counts()
    if query:
        skills = skills.filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query)
        )
    if category:
        skills = skills.filter(category=category)
    skills = number_skills(skills.order_by(*orderings[sort]))

    my_wants, my_offers = skill_ids_for(request.user)
    return {
        "skills": skills,
        "grouped": sort == "default",
        "sort": sort,
        "sort_options": [(key, label) for key, label, _ in SORT_OPTIONS],
        "query": query,
        "active_category": category,
        "categories": Category.objects.annotate(skill_count=Count("skills")),
        "total_skills": Skill.objects.count(),
        "my_wants": my_wants,
        "my_offers": my_offers,
    }


def skill_list(request):
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "")
    active_category = get_object_or_404(Category, slug=category_slug) if category_slug else None
    context = index_context(request, query, active_category, request.GET.get("sort", "default"))

    # "Search users by skill": people who teach a skill matching the search.
    people = []
    if query:
        people = (
            User.objects.filter(
                is_active=True,
                user_skills__kind=UserSkill.Kind.OFFER,
                user_skills__skill__name__icontains=query,
            )
            .distinct()
            .select_related("profile")
            .prefetch_related("user_skills__skill")[:8]
        )
        for person in people:
            person.teaches = [us.skill for us in person.user_skills.all() if us.kind == UserSkill.Kind.OFFER]
    context["people"] = people
    return render(request, "skills/skill_list.html", context)


def skill_detail(request, slug):
    skill = get_object_or_404(Skill.objects.select_related("category"), slug=slug)
    entries = list(
        skill.user_skills.filter(user__is_active=True).select_related("user__profile").order_by("-created_at")
    )
    teachers = [e for e in entries if e.kind == UserSkill.Kind.OFFER]
    learners = [e for e in entries if e.kind == UserSkill.Kind.WANT]

    ratings = ratings_by_user([t.user_id for t in teachers])
    for teacher in teachers:
        teacher.rating = ratings.get(teacher.user_id, {"avg": None, "count": 0})

    my_kind = None
    if request.user.is_authenticated:
        my_kind = next((e.kind for e in entries if e.user_id == request.user.pk), None)

    return render(request, "skills/skill_detail.html", {
        "skill": skill,
        "teachers": teachers,
        "learners": learners,
        "my_kind": my_kind,
        "related": Skill.objects.filter(category=skill.category).exclude(pk=skill.pk)[:8],
    })


@login_required
def my_skills(request):
    initial = {}
    if request.method == "GET":
        initial = {k: request.GET[k] for k in ("skill", "kind") if k in request.GET}

    form = UserSkillForm(request.user, request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        entry = form.save()
        verb = "teach" if entry.kind == UserSkill.Kind.OFFER else "learn"
        messages.success(request, f"Added {entry.skill.name} to the skills you want to {verb}.")
        return redirect(_safe_next(request, "skills:my_skills"))

    entries = request.user.user_skills.select_related("skill__category")
    return render(request, "skills/my_skills.html", {
        "form": form,
        "offers": [e for e in entries if e.kind == UserSkill.Kind.OFFER],
        "wants": [e for e in entries if e.kind == UserSkill.Kind.WANT],
    })


@login_required
@require_POST
def my_skill_delete(request, pk):
    entry = get_object_or_404(UserSkill, pk=pk, user=request.user)
    entry.delete()
    messages.info(request, f"Removed {entry.skill.name} from your skills.")
    return redirect(_safe_next(request, "skills:my_skills"))
