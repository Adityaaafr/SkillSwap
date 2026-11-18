"""Read-only queries about exchanges, shared by several views."""
from django.db.models import Avg, Count, Q

from .models import LearningSession, Review


def rating_summary(user):
    """{'avg': float | None, 'count': int} of the reviews a user has received."""
    return Review.objects.filter(reviewee=user).aggregate(avg=Avg("rating"), count=Count("id"))


def ratings_by_user(user_ids):
    """Map user id -> {'avg': ..., 'count': ...} in a single query."""
    rows = (
        Review.objects.filter(reviewee_id__in=user_ids)
        .values("reviewee_id")
        .annotate(avg=Avg("rating"), count=Count("id"))
    )
    return {row["reviewee_id"]: row for row in rows}


def sessions_for(user):
    """All sessions where the user is the teacher or the learner."""
    return LearningSession.objects.filter(Q(teacher=user) | Q(learner=user))
