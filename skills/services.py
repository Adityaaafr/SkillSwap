from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from .models import Skill, UserSkill

User = get_user_model()


def skills_with_counts():
    """Skills with how many people teach and want each one."""
    return Skill.objects.select_related("category").annotate(
        teacher_count=Count("user_skills", filter=Q(user_skills__kind=UserSkill.Kind.OFFER)),
        learner_count=Count("user_skills", filter=Q(user_skills__kind=UserSkill.Kind.WANT)),
    )


def number_skills(skills):
    """Give each skill its catalogue number (position in category/name order).

    The number stays the same whatever filter or sort is applied, like an index entry.
    """
    ids = Skill.objects.order_by("category__name", "name").values_list("pk", flat=True)
    numbers = {pk: n for n, pk in enumerate(ids, start=1)}
    skills = list(skills)
    for skill in skills:
        skill.number = numbers.get(skill.pk, 0)
    return skills


def skill_ids_for(user):
    """(wanted skill ids, offered skill ids) for a user; empty sets for visitors."""
    wants, offers = set(), set()
    if user.is_authenticated:
        for skill_id, kind in user.user_skills.values_list("skill_id", "kind"):
            (wants if kind == UserSkill.Kind.WANT else offers).add(skill_id)
    return wants, offers


def find_matches(user, limit=6):
    """Users who can teach something `user` wants AND want something `user` can teach.

    The two separate .filter() calls each create their own JOIN on user_skills, so one row
    satisfies "offers what I want" and a different row satisfies "wants what I offer".
    """
    my_skills = list(user.user_skills.values_list("skill_id", "kind"))
    my_wants = {skill_id for skill_id, kind in my_skills if kind == UserSkill.Kind.WANT}
    my_offers = {skill_id for skill_id, kind in my_skills if kind == UserSkill.Kind.OFFER}
    if not (my_wants and my_offers):
        return []

    candidates = (
        User.objects.filter(is_active=True)
        .filter(user_skills__kind=UserSkill.Kind.OFFER, user_skills__skill__in=my_wants)
        .filter(user_skills__kind=UserSkill.Kind.WANT, user_skills__skill__in=my_offers)
        .exclude(pk=user.pk)
        .distinct()
        .select_related("profile")
        .prefetch_related("user_skills__skill")[:limit]
    )

    matches = []
    for person in candidates:
        their_skills = list(person.user_skills.all())
        matches.append({
            "user": person,
            "can_teach_you": [
                us.skill for us in their_skills
                if us.kind == UserSkill.Kind.OFFER and us.skill_id in my_wants
            ],
            "wants_from_you": [
                us.skill for us in their_skills
                if us.kind == UserSkill.Kind.WANT and us.skill_id in my_offers
            ],
        })
    return matches
