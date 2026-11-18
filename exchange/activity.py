"""Builds a user's learning history from requests, sessions and reviews.

There's no separate "activity" table: every event is derived from data that already exists,
so the history can never drift out of sync with what actually happened.
"""
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Avg, Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from .models import ExchangeRequest, LearningSession, Review
from .selectors import sessions_for

EVENT_TYPES = [("all", "All"), ("sessions", "Sessions"), ("reviews", "Reviews"), ("requests", "Requests")]


@dataclass
class Event:
    when: datetime
    kind: str            # "session" | "review" | "request"
    text: str
    url: str
    rating: int | None = None
    note: str = ""

    @property
    def month(self):
        return timezone.localtime(self.when).strftime("%B %Y")


def _name(user, me):
    return "you" if user.pk == me.pk else (user.first_name or user.username)


def _request_events(user):
    requests = ExchangeRequest.objects.involving(user).select_related(
        "sender", "receiver", "requested_skill", "offered_skill"
    )
    for r in requests:
        url = reverse("exchange:detail", args=[r.pk])
        sent_by_me = r.sender_id == user.pk
        other = r.receiver if sent_by_me else r.sender
        swap = f", offering {r.offered_skill.name}" if r.offered_skill else ""
        if sent_by_me:
            text = f"You asked {_name(other, user)} to teach you {r.requested_skill.name}{swap}"
        else:
            text = f"{_name(other, user)} asked to learn {r.requested_skill.name} from you{swap}"
        yield Event(r.created_at, "request", text, url)

        if r.responded_at:
            verb = "declined" if r.status == ExchangeRequest.Status.REJECTED else "accepted"
            who = "You" if not sent_by_me else other.first_name or other.username
            yield Event(r.responded_at, "request", f"{who} {verb} the {r.requested_skill.name} request", url)
        if r.completed_at:
            yield Event(r.completed_at, "request", f"Exchange with {_name(other, user)} completed", url)


def _session_events(user):
    done = sessions_for(user).filter(status=LearningSession.Status.COMPLETED).select_related(
        "skill", "teacher", "learner"
    )
    for s in done:
        if s.teacher_id == user.pk:
            text = f"You taught {s.skill.name} to {_name(s.learner, user)} · {s.duration_minutes} min"
        else:
            text = f"You learned {s.skill.name} from {_name(s.teacher, user)} · {s.duration_minutes} min"
        yield Event(s.completed_at or s.ends_at, "session", text, reverse("exchange:session_detail", args=[s.pk]))


def _review_events(user):
    reviews = Review.objects.filter(Q(reviewer=user) | Q(reviewee=user)).select_related(
        "reviewer", "reviewee", "session__skill"
    )
    for rv in reviews:
        if rv.reviewer_id == user.pk:
            text = f"You reviewed {_name(rv.reviewee, user)} ({rv.session.skill.name})"
        else:
            text = f"{_name(rv.reviewer, user)} reviewed you ({rv.session.skill.name})"
        yield Event(
            rv.created_at, "review", text, reverse("exchange:session_detail", args=[rv.session_id]),
            rating=rv.rating, note=rv.comment,
        )


def history_for(user, kind="all"):
    builders = {"requests": _request_events, "sessions": _session_events, "reviews": _review_events}
    chosen = builders.values() if kind == "all" else [builders[kind]]
    events = [event for build in chosen for event in build(user)]
    events.sort(key=lambda e: e.when, reverse=True)
    return events


def summary_for(user):
    """Headline numbers for the activity page."""
    done = sessions_for(user).filter(status=LearningSession.Status.COMPLETED)
    taught = done.filter(teacher=user).aggregate(n=Count("id"), minutes=Sum("duration_minutes"))
    learned = done.filter(learner=user).aggregate(n=Count("id"), minutes=Sum("duration_minutes"))
    partners = {pk for pair in done.values_list("teacher_id", "learner_id") for pk in pair} - {user.pk}
    received = Review.objects.filter(reviewee=user).aggregate(avg=Avg("rating"), n=Count("id"))
    return {
        "taught_sessions": taught["n"],
        "taught_hours": (taught["minutes"] or 0) / 60,
        "learned_sessions": learned["n"],
        "learned_hours": (learned["minutes"] or 0) / 60,
        "partners": len(partners),
        "skills_taught": done.filter(teacher=user).values("skill").distinct().count(),
        "rating_avg": received["avg"],
        "rating_count": received["n"],
        "reviews_given": Review.objects.filter(reviewer=user).count(),
    }


def _row(label, value):
    return {"kind": "row", "label": label, "value": value}


DIVIDER = {"kind": "divider"}


def receipt_for(user, summary):
    """The activity page's printable 'learning receipt'."""
    now = timezone.localtime()
    rating = f"{summary['rating_avg']:.1f} / 5 ({summary['rating_count']})" if summary["rating_avg"] else "No reviews yet"
    total_hours = summary["taught_hours"] + summary["learned_hours"]
    return {
        "title": "SkillSwap",
        "subtitle": "Learning receipt",
        "number": f"{user.pk:04d}",
        "stamp": now.strftime("%d %b %Y · %H:%M"),
        "lines": [
            _row("Member", f"@{user.username}"),
            _row("Since", timezone.localtime(user.date_joined).strftime("%b %Y")),
            DIVIDER,
            _row(f"Taught × {summary['taught_sessions']}", f"{summary['taught_hours']:g} h"),
            _row(f"Learned × {summary['learned_sessions']}", f"{summary['learned_hours']:g} h"),
            _row("Partners", str(summary["partners"])),
            _row("Skills taught", str(summary["skills_taught"])),
            _row("Reviews given", str(summary["reviews_given"])),
            _row("Rating", rating),
            DIVIDER,
            {"kind": "total", "label": "Knowledge swapped", "value": f"{total_hours:g} h"},
            {"kind": "total", "label": "Money spent", "value": "₹0.00"},
        ],
        "footer": "Thank you. Keep swapping.",
        "code": f"SS{user.pk:04d}{now:%y%m%d}",
    }


def ticket_for(session, viewer):
    """A session's 'ticket', printed right after booking."""
    start = timezone.localtime(session.scheduled_at)
    end = timezone.localtime(session.ends_at)
    where = session.get_mode_display()
    if session.location_or_link and not session.location_or_link.startswith(("http://", "https://")):
        where = f"{where} · {session.location_or_link}"

    def name(u):
        return "You" if u.pk == viewer.pk else (u.first_name or u.username)

    return {
        "title": "SkillSwap",
        "subtitle": "Session ticket",
        "number": f"{session.pk:04d}",
        "stamp": timezone.localtime(session.created_at).strftime("%d %b %Y · %H:%M"),
        "lines": [
            {"kind": "heading", "label": session.skill.name},
            _row("Teacher", name(session.teacher)),
            _row("Learner", name(session.learner)),
            DIVIDER,
            _row("Date", start.strftime("%a %d %b %Y")),
            _row("Time", f"{start:%H:%M}–{end:%H:%M}"),
            _row("Length", f"{session.duration_minutes} min"),
            _row("Where", where),
            DIVIDER,
            {"kind": "total", "label": "Price", "value": "₹0.00"},
        ],
        "footer": "Bring curiosity. No coins needed.",
        "code": f"SST{session.pk:05d}",
    }
