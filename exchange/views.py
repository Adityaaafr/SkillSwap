from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from skills.models import UserSkill

from .activity import EVENT_TYPES, history_for, receipt_for, summary_for, ticket_for
from .forms import ExchangeRequestForm, LearningSessionForm, ReviewForm
from .models import ExchangeRequest, LearningSession, Review
from .selectors import sessions_for

User = get_user_model()
Status = ExchangeRequest.Status

STATUS_FILTERS = {
    "all": None,
    "pending": [Status.PENDING],
    "active": [Status.ACCEPTED],
    "completed": [Status.COMPLETED],
    "closed": [Status.REJECTED, Status.CANCELLED],
}


@login_required
def request_list(request):
    tab = "outgoing" if request.GET.get("tab") == "outgoing" else "incoming"
    status = request.GET.get("status", "all")
    if status not in STATUS_FILTERS:
        status = "all"

    if tab == "incoming":
        qs = ExchangeRequest.objects.filter(receiver=request.user)
    else:
        qs = ExchangeRequest.objects.filter(sender=request.user)
    if STATUS_FILTERS[status]:
        qs = qs.filter(status__in=STATUS_FILTERS[status])
    qs = qs.select_related(
        "sender__profile", "receiver__profile", "requested_skill", "offered_skill"
    ).annotate(session_count=Count("sessions")).order_by("-created_at")  # Meta.ordering is dropped by GROUP BY

    counts = ExchangeRequest.objects.aggregate(
        incoming=Count("id", filter=Q(receiver=request.user)),
        incoming_pending=Count("id", filter=Q(receiver=request.user, status=Status.PENDING)),
        outgoing=Count("id", filter=Q(sender=request.user)),
    )
    return render(request, "exchange/request_list.html", {
        "requests": qs,
        "tab": tab,
        "status": status,
        "counts": counts,
        "status_filters": [
            ("all", "All"), ("pending", "Pending"), ("active", "Active"),
            ("completed", "Completed"), ("closed", "Declined & cancelled"),
        ],
    })


@login_required
def request_create(request, username):
    receiver = get_object_or_404(User.objects.select_related("profile"), username=username, is_active=True)
    if receiver == request.user:
        messages.error(request, "You can't send an exchange request to yourself.")
        return redirect("accounts:profile", username=username)
    if not receiver.user_skills.filter(kind=UserSkill.Kind.OFFER).exists():
        messages.info(request, f"{receiver.first_name or receiver.username} hasn't listed any skills to teach yet.")
        return redirect("accounts:profile", username=username)

    initial = {}
    if request.method == "GET":
        if request.GET.get("skill"):
            initial["requested_skill"] = request.GET["skill"]
        # Pre-select something the receiver wants that the sender can teach.
        their_wants = receiver.user_skills.filter(kind=UserSkill.Kind.WANT).values("skill")
        swap = request.user.user_skills.filter(kind=UserSkill.Kind.OFFER, skill__in=their_wants).first()
        if swap:
            initial["offered_skill"] = swap.skill_id

    form = ExchangeRequestForm(request.user, receiver, request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        exchange = form.save()
        messages.success(request, f"Request sent to {receiver.get_full_name() or receiver.username}. You'll see their reply here.")
        return redirect("exchange:detail", pk=exchange.pk)

    return render(request, "exchange/request_form.html", {
        "form": form,
        "receiver": receiver,
        "has_offers": request.user.user_skills.filter(kind=UserSkill.Kind.OFFER).exists(),
    })


def _get_exchange_for(user, pk):
    """Only the sender and receiver can see an exchange; everyone else gets a 404."""
    return get_object_or_404(
        ExchangeRequest.objects.involving(user).select_related(
            "sender__profile", "receiver__profile", "requested_skill", "offered_skill"
        ),
        pk=pk,
    )


@login_required
def request_detail(request, pk):
    exchange = _get_exchange_for(request.user, pk)
    is_sender = request.user.pk == exchange.sender_id
    is_pending = exchange.status == Status.PENDING
    is_accepted = exchange.status == Status.ACCEPTED

    return render(request, "exchange/request_detail.html", {
        "exchange": exchange,
        "other": exchange.other_party(request.user),
        "is_sender": is_sender,
        "sessions": exchange.sessions.select_related("skill", "teacher", "learner"),
        "can_respond": is_pending and not is_sender,
        "can_cancel": is_pending and is_sender,
        "can_complete": is_accepted,
    })


ACTIONS = {
    # action: (model method, success message)
    "accept": ("accept", "Request accepted. Next, agree on a time for your first session."),
    "reject": ("reject", "Request declined."),
    "cancel": ("cancel", "Request cancelled."),
    "complete": ("mark_completed", "Exchange marked as completed. Nice work!"),
}


@login_required
@require_POST
def request_action(request, pk, action):
    if action not in ACTIONS:
        raise Http404("Unknown action.")
    exchange = _get_exchange_for(request.user, pk)
    method_name, success_message = ACTIONS[action]
    try:
        # PermissionDenied (wrong person) is left to propagate and becomes a 403 response.
        getattr(exchange, method_name)(request.user)
    except ValidationError as error:
        for msg in error.messages:
            messages.error(request, msg)
    else:
        messages.success(request, success_message)
    return redirect("exchange:detail", pk=exchange.pk)


# ---- Learning sessions ---------------------------------------------------------------------

SESSION_TABS = [
    ("upcoming", "Upcoming"),
    ("confirm", "To confirm"),
    ("past", "Past"),
]


@login_required
def session_list(request):
    now = timezone.now()
    mine = sessions_for(request.user).select_related("skill", "teacher__profile", "learner__profile", "exchange")
    tabs = {
        "upcoming": mine.filter(status=LearningSession.Status.SCHEDULED, scheduled_at__gt=now).order_by("scheduled_at"),
        "confirm": mine.filter(status=LearningSession.Status.SCHEDULED, scheduled_at__lte=now).order_by("scheduled_at"),
        "past": mine.exclude(status=LearningSession.Status.SCHEDULED).order_by("-scheduled_at"),
    }
    tab = request.GET.get("tab")
    if tab not in tabs:
        # Open on "To confirm" when something is waiting for the user, otherwise "Upcoming".
        tab = "confirm" if tabs["confirm"].exists() else "upcoming"
    return render(request, "exchange/session_list.html", {
        "sessions": tabs[tab],
        "tab": tab,
        "tabs": [(key, label, tabs[key].count()) for key, label in SESSION_TABS],
        "reviewed_ids": set(Review.objects.filter(reviewer=request.user).values_list("session_id", flat=True)),
    })


@login_required
def session_create(request, pk):
    exchange = _get_exchange_for(request.user, pk)
    if exchange.status != Status.ACCEPTED:
        messages.error(request, "Sessions can only be scheduled once the request has been accepted.")
        return redirect("exchange:detail", pk=exchange.pk)

    form = LearningSessionForm(exchange, request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        session = form.save()
        when = timezone.localtime(session.scheduled_at)
        messages.success(request, f"Session booked for {when:%a %d %b at %H:%M}. Add it to your calendar so you don't forget.")
        return redirect(reverse("exchange:session_detail", args=[session.pk]) + "?booked=1")
    return render(request, "exchange/session_form.html", {
        "form": form,
        "exchange": exchange,
        "other": exchange.other_party(request.user),
    })


def _get_session_for(user, pk):
    """Only the teacher and learner can see a session; everyone else gets a 404."""
    return get_object_or_404(
        sessions_for(user).select_related(
            "skill", "teacher__profile", "learner__profile",
            "exchange__requested_skill", "exchange__offered_skill",
        ),
        pk=pk,
    )


@login_required
def session_detail(request, pk):
    session = _get_session_for(request.user, pk)
    return render(request, "exchange/session_detail.html", {
        "session": session,
        "other": session.other_party(request.user),
        "is_teacher": session.teacher_id == request.user.pk,
        "is_link": session.location_or_link.startswith(("http://", "https://")),
        "reviews": session.reviews.select_related("reviewer__profile"),
        "can_review": session.can_review(request.user),
        "ticket": ticket_for(session, request.user) if session.status != LearningSession.Status.CANCELLED else None,
        "print_ticket": request.GET.get("booked") == "1",
    })


@login_required
def session_review(request, pk):
    session = _get_session_for(request.user, pk)
    if not session.can_review(request.user):
        if session.has_reviewed(request.user):
            messages.info(request, "You've already reviewed this session.")
        else:
            messages.error(request, "You can review a session once it's been marked as done.")
        return redirect("exchange:session_detail", pk=session.pk)

    other = session.other_party(request.user)
    form = ReviewForm(session, request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Thanks! Your review is now on {other.first_name or other.username}'s profile.")
        return redirect("exchange:session_detail", pk=session.pk)
    return render(request, "exchange/review_form.html", {"form": form, "session": session, "other": other})


SESSION_ACTIONS = {
    "complete": ("mark_completed", "Session marked as done. Nice work!"),
    "cancel": ("cancel", "Session cancelled."),
}


@login_required
@require_POST
def session_action(request, pk, action):
    if action not in SESSION_ACTIONS:
        raise Http404("Unknown action.")
    session = _get_session_for(request.user, pk)
    method_name, success_message = SESSION_ACTIONS[action]
    try:
        getattr(session, method_name)(request.user)
    except ValidationError as error:
        for msg in error.messages:
            messages.error(request, msg)
    else:
        messages.success(request, success_message)
    return redirect("exchange:session_detail", pk=session.pk)


def _ics_text(value):
    """Escape text for an iCalendar field."""
    return (
        value.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
        .replace("\r\n", r"\n").replace("\n", r"\n")
    )


def _ics_time(dt):
    return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@login_required
def session_calendar(request, pk):
    """Download the session as an .ics file for Google Calendar, Outlook or Apple Calendar."""
    session = _get_session_for(request.user, pk)
    other = session.other_party(request.user)
    title = f"SkillSwap: {session.skill.name} with {other.get_full_name() or other.username}"
    details = f"{session.teacher.get_full_name() or session.teacher.username} teaches {session.skill.name}."
    if session.agenda:
        details += f"\n\nPlan: {session.agenda}"
    details += f"\n\n{request.build_absolute_uri(reverse('exchange:session_detail', args=[session.pk]))}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SkillSwap//Learning sessions//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:skillswap-session-{session.pk}@{request.get_host().split(':')[0]}",
        f"DTSTAMP:{_ics_time(timezone.now())}",
        f"DTSTART:{_ics_time(session.scheduled_at)}",
        f"DTEND:{_ics_time(session.ends_at)}",
        f"SUMMARY:{_ics_text(title)}",
        f"DESCRIPTION:{_ics_text(details)}",
    ]
    if session.location_or_link:
        lines.append(f"LOCATION:{_ics_text(session.location_or_link)}")
    if session.status == LearningSession.Status.CANCELLED:
        lines.append("STATUS:CANCELLED")
    lines += ["END:VEVENT", "END:VCALENDAR"]

    response = HttpResponse("\r\n".join(lines) + "\r\n", content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="skillswap-session-{session.pk}.ics"'
    return response


# ---- Activity history ----------------------------------------------------------------------

@login_required
def activity(request):
    kind = request.GET.get("type", "all")
    if kind not in dict(EVENT_TYPES):
        kind = "all"
    summary = summary_for(request.user)
    return render(request, "exchange/activity.html", {
        "events": history_for(request.user, kind),
        "kind": kind,
        "event_types": EVENT_TYPES,
        "summary": summary,
        "receipt": receipt_for(request.user, summary),
    })
