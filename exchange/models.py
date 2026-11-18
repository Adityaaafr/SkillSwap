from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from skills.models import Skill, UserSkill

MAX_SESSION_MINUTES = 240


class ExchangeRequestQuerySet(models.QuerySet):
    def involving(self, user):
        """Requests the user sent or received."""
        return self.filter(Q(sender=user) | Q(receiver=user))


class ExchangeRequest(models.Model):
    """A request from `sender` to learn `requested_skill` from `receiver`.

    If `offered_skill` is set it's a two-way swap: the sender teaches that skill in return.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_requests"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_requests"
    )
    requested_skill = models.ForeignKey(
        Skill, on_delete=models.PROTECT, related_name="+",
        help_text="The skill the sender wants to learn from the receiver.",
    )
    offered_skill = models.ForeignKey(
        Skill, on_delete=models.PROTECT, related_name="+", null=True, blank=True,
        help_text="Optional: the skill the sender will teach in return.",
    )
    message = models.TextField(max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ExchangeRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(sender=F("receiver")), name="no_self_request"),
            models.UniqueConstraint(
                fields=["sender", "receiver", "requested_skill"],
                condition=Q(status="pending"),
                name="one_pending_request_per_skill",
            ),
        ]

    def __str__(self):
        return f"{self.sender} → {self.receiver}: {self.requested_skill}"

    # ---- helpers -------------------------------------------------------------------------

    @property
    def is_swap(self):
        return self.offered_skill_id is not None

    def is_participant(self, user):
        return user.pk in (self.sender_id, self.receiver_id)

    def other_party(self, user):
        return self.receiver if user.pk == self.sender_id else self.sender

    def skills(self):
        """The one or two skills that sessions in this exchange can cover."""
        return [s for s in (self.requested_skill, self.offered_skill) if s is not None]

    def roles_for(self, skill):
        """Return (teacher, learner) for a session about `skill`."""
        if skill.pk == self.requested_skill_id:
            return self.receiver, self.sender
        if skill.pk == self.offered_skill_id:
            return self.sender, self.receiver
        raise ValidationError({"skill": "That skill isn't part of this exchange."})

    # ---- validation ----------------------------------------------------------------------

    def clean(self):
        if not (self.sender_id and self.receiver_id):
            return
        if self.sender_id == self.receiver_id:
            raise ValidationError("You can't send an exchange request to yourself.")

        errors = {}
        offers = UserSkill.objects.filter(kind=UserSkill.Kind.OFFER)
        if self.requested_skill_id and not offers.filter(
            user_id=self.receiver_id, skill_id=self.requested_skill_id
        ).exists():
            errors["requested_skill"] = "This person doesn't offer that skill."
        if self.offered_skill_id:
            if self.offered_skill_id == self.requested_skill_id:
                errors["offered_skill"] = "Offer a different skill from the one you're asking for."
            elif not offers.filter(user_id=self.sender_id, skill_id=self.offered_skill_id).exists():
                errors["offered_skill"] = "You can only offer a skill listed on your profile."
        if self._state.adding and self.requested_skill_id and ExchangeRequest.objects.filter(
            sender_id=self.sender_id,
            receiver_id=self.receiver_id,
            requested_skill_id=self.requested_skill_id,
            status=self.Status.PENDING,
        ).exists():
            errors["requested_skill"] = "You already have a pending request for this skill."
        if errors:
            raise ValidationError(errors)

    # ---- state transitions ---------------------------------------------------------------
    # PENDING --accept/reject (receiver)--> ACCEPTED / REJECTED
    # PENDING --cancel (sender)--> CANCELLED
    # ACCEPTED --complete (either participant, >=1 completed session)--> COMPLETED

    def accept(self, user):
        if user.pk != self.receiver_id:
            raise PermissionDenied("Only the person who received this request can accept it.")
        if self.status != self.Status.PENDING:
            raise ValidationError("Only pending requests can be accepted.")
        self.status = self.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])

    def reject(self, user):
        if user.pk != self.receiver_id:
            raise PermissionDenied("Only the person who received this request can reject it.")
        if self.status != self.Status.PENDING:
            raise ValidationError("Only pending requests can be rejected.")
        self.status = self.Status.REJECTED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])

    def cancel(self, user):
        if user.pk != self.sender_id:
            raise PermissionDenied("Only the person who sent this request can cancel it.")
        if self.status != self.Status.PENDING:
            raise ValidationError("Only pending requests can be cancelled.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])

    def mark_completed(self, user):
        if not self.is_participant(user):
            raise PermissionDenied("Only the people in this exchange can complete it.")
        if self.status != self.Status.ACCEPTED:
            raise ValidationError("Only accepted exchanges can be completed.")
        if not self.sessions.filter(status=LearningSession.Status.COMPLETED).exists():
            raise ValidationError("Complete at least one learning session first.")
        if self.sessions.filter(status=LearningSession.Status.SCHEDULED).exists():
            raise ValidationError("Finish or cancel the upcoming sessions first.")
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])


class LearningSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Mode(models.TextChoices):
        ONLINE = "online", "Online"
        IN_PERSON = "in_person", "In person"

    exchange = models.ForeignKey(ExchangeRequest, on_delete=models.CASCADE, related_name="sessions")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="sessions")
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions_taught"
    )
    learner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions_learned"
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(15), MaxValueValidator(MAX_SESSION_MINUTES)]
    )
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.ONLINE)
    location_or_link = models.CharField(
        max_length=255, blank=True, help_text="Meeting link for online sessions, or a place to meet."
    )
    agenda = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        when = timezone.localtime(self.scheduled_at).strftime("%d %b %Y %H:%M")
        return f"{self.skill} · {self.teacher} teaches {self.learner} · {when}"

    @property
    def ends_at(self):
        return self.scheduled_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_upcoming(self):
        return self.status == self.Status.SCHEDULED and self.scheduled_at > timezone.now()

    @property
    def needs_confirmation(self):
        """Started (or finished) but nobody has marked it as done or cancelled yet."""
        return self.status == self.Status.SCHEDULED and self.scheduled_at <= timezone.now()

    def clashes(self):
        """Other scheduled sessions of the teacher or learner that overlap this one's time."""
        if not (self.scheduled_at and self.duration_minutes and self.teacher_id and self.learner_id):
            return []
        people = [self.teacher_id, self.learner_id]
        longest = MAX_SESSION_MINUTES
        # Narrow the search in the database, then check exact overlap in Python
        # (end time = start + duration, which SQLite can't compute for us easily).
        nearby = (
            LearningSession.objects.filter(status=self.Status.SCHEDULED)
            .filter(Q(teacher_id__in=people) | Q(learner_id__in=people))
            .filter(scheduled_at__lt=self.ends_at, scheduled_at__gt=self.scheduled_at - timedelta(minutes=longest))
            .exclude(pk=self.pk)
            .select_related("skill")
        )
        return [s for s in nearby if s.ends_at > self.scheduled_at]

    def is_participant(self, user):
        return user.pk in (self.teacher_id, self.learner_id)

    def other_party(self, user):
        return self.learner if user.pk == self.teacher_id else self.teacher

    def assign_roles(self):
        """Teacher and learner always follow from the exchange and the chosen skill."""
        if self.exchange_id and self.skill_id:
            self.teacher, self.learner = self.exchange.roles_for(self.skill)

    def clean_fields(self, exclude=None):
        # Fill teacher/learner before Django checks required fields; clean() reports a bad skill.
        try:
            self.assign_roles()
        except ValidationError:
            pass
        super().clean_fields(exclude=exclude)

    def clean(self):
        if not (self.exchange_id and self.skill_id):
            return
        if self._state.adding:
            if self.exchange.status != ExchangeRequest.Status.ACCEPTED:
                raise ValidationError("Sessions can only be scheduled for accepted exchanges.")
            if self.scheduled_at and self.scheduled_at <= timezone.now():
                raise ValidationError({"scheduled_at": "Pick a time in the future."})
        self.assign_roles()
        if self.status == self.Status.SCHEDULED:
            clash = next(iter(self.clashes()), None)
            if clash:
                start = timezone.localtime(clash.scheduled_at)
                end = timezone.localtime(clash.ends_at)
                raise ValidationError({"scheduled_at": (
                    f"That overlaps another session ({clash.skill.name}, {start:%d %b} "
                    f"{start:%H:%M}–{end:%H:%M}). Pick a different time."
                )})

    def save(self, *args, **kwargs):
        self.assign_roles()
        super().save(*args, **kwargs)

    # ---- state transitions ---------------------------------------------------------------
    # SCHEDULED --mark done (participant, after start time)--> COMPLETED  (unlocks reviews)
    # SCHEDULED --cancel (participant, before start time)--> CANCELLED

    def mark_completed(self, user):
        if not self.is_participant(user):
            raise PermissionDenied("Only the teacher or learner can complete this session.")
        if self.status != self.Status.SCHEDULED:
            raise ValidationError("Only scheduled sessions can be marked as completed.")
        if self.scheduled_at > timezone.now():
            raise ValidationError("You can mark a session as done once it has started.")
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    def cancel(self, user):
        if not self.is_participant(user):
            raise PermissionDenied("Only the teacher or learner can cancel this session.")
        if self.status != self.Status.SCHEDULED:
            raise ValidationError("Only scheduled sessions can be cancelled.")
        if self.scheduled_at <= timezone.now():
            raise ValidationError("This session has already started, so it can't be cancelled.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])

    def has_reviewed(self, user):
        return self.reviews.filter(reviewer=user).exists()

    def can_review(self, user):
        return (
            self.status == self.Status.COMPLETED
            and self.is_participant(user)
            and not self.has_reviewed(user)
        )


class Review(models.Model):
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_given"
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "reviewer"], name="one_review_per_session_per_user"
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="rating_between_1_and_5"
            ),
        ]

    def __str__(self):
        return f"{self.reviewer} → {self.reviewee}: {self.rating}★"

    def clean_fields(self, exclude=None):
        # The reviewee is always "the other person in the session", so fill it in first.
        if self.session_id and self.reviewer_id:
            self.reviewee = self.session.other_party(self.reviewer)
        super().clean_fields(exclude=exclude)

    def clean(self):
        if not (self.session_id and self.reviewer_id):
            return
        session = self.session
        if session.status != LearningSession.Status.COMPLETED:
            raise ValidationError("You can only review a session after it's completed.")
        if not session.is_participant(self.reviewer):
            raise ValidationError("Only the people in this session can review it.")
        if self._state.adding and Review.objects.filter(
            session_id=self.session_id, reviewer_id=self.reviewer_id
        ).exists():
            raise ValidationError("You've already reviewed this session.")
        self.reviewee = session.other_party(self.reviewer)

    def save(self, *args, **kwargs):
        if self.session_id and self.reviewer_id and not self.reviewee_id:
            self.reviewee = self.session.other_party(self.reviewer)
        super().save(*args, **kwargs)
