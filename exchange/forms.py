from django import forms
from django.utils import timezone

from core.forms import BootstrapFormMixin
from skills.models import Skill, UserSkill

from .models import ExchangeRequest, LearningSession, Review

DATETIME_LOCAL = "%Y-%m-%dT%H:%M"  # the format <input type="datetime-local"> sends
DURATION_CHOICES = [(30, "30 minutes"), (45, "45 minutes"), (60, "1 hour"), (90, "1½ hours"), (120, "2 hours")]


class ExchangeRequestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ExchangeRequest
        fields = ("requested_skill", "offered_skill", "message")
        labels = {
            "requested_skill": "What do you want to learn?",
            "offered_skill": "What will you teach in return?",
            "message": "Message",
        }
        widgets = {
            "message": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Introduce yourself and say what you'd like to get out of the sessions.",
            }),
        }

    def __init__(self, sender, receiver, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # sender/receiver aren't form fields, so set them before the model's clean() runs.
        self.instance.sender = sender
        self.instance.receiver = receiver

        offers = UserSkill.Kind.OFFER
        self.fields["requested_skill"].queryset = Skill.objects.filter(
            user_skills__user=receiver, user_skills__kind=offers
        )
        self.fields["requested_skill"].empty_label = "Choose a skill they teach…"
        self.fields["requested_skill"].help_text = "Only skills they've listed as “can teach”."

        self.fields["offered_skill"].queryset = Skill.objects.filter(
            user_skills__user=sender, user_skills__kind=offers
        )
        self.fields["offered_skill"].empty_label = "Nothing for now, I just want to learn"
        self.fields["offered_skill"].help_text = (
            "Optional, but a two-way swap is much more likely to be accepted."
        )
        self.fields["message"].help_text = "Up to 500 characters."


class LearningSessionForm(BootstrapFormMixin, forms.ModelForm):
    scheduled_at = forms.DateTimeField(
        label="Date and time",
        input_formats=[DATETIME_LOCAL],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL),
    )
    duration_minutes = forms.TypedChoiceField(
        label="Length", choices=DURATION_CHOICES, coerce=int, initial=60
    )

    class Meta:
        model = LearningSession
        fields = ("skill", "scheduled_at", "duration_minutes", "mode", "location_or_link", "agenda")
        labels = {
            "skill": "What will this session cover?",
            "mode": "Where",
            "location_or_link": "Meeting link or place",
            "agenda": "Plan for the session (optional)",
        }
        widgets = {
            "location_or_link": forms.TextInput(attrs={"placeholder": "https://meet.google.com/… or “Library, 2nd floor”"}),
            "agenda": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Set up Figma, then build a first wireframe together."}),
        }

    def __init__(self, exchange, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # exchange and created_by aren't form fields; set them so the model's clean() can use them.
        self.instance.exchange = exchange
        self.instance.created_by = user

        skill_field = self.fields["skill"]
        skill_field.queryset = Skill.objects.filter(pk__in=[s.pk for s in exchange.skills()])
        skill_field.empty_label = None

        def describe(skill):
            teacher, _ = exchange.roles_for(skill)
            who = "you teach" if teacher.pk == user.pk else f"{teacher.first_name or teacher.username} teaches you"
            return f"{skill.name} ({who})"

        skill_field.label_from_instance = describe
        self.fields["scheduled_at"].widget.attrs["min"] = timezone.localtime().strftime(DATETIME_LOCAL)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("mode") == LearningSession.Mode.IN_PERSON and not cleaned.get("location_or_link"):
            self.add_error("location_or_link", "Say where you'll meet.")
        return cleaned


RATING_CHOICES = [(5, "Excellent"), (4, "Good"), (3, "Okay"), (2, "Poor"), (1, "Bad")]


class ReviewForm(BootstrapFormMixin, forms.ModelForm):
    rating = forms.TypedChoiceField(
        label="Your rating", choices=RATING_CHOICES, coerce=int, widget=forms.RadioSelect,
        error_messages={"required": "Choose a rating from 1 to 5 stars."},
    )

    class Meta:
        model = Review
        fields = ("rating", "comment")
        labels = {"comment": "What was it like? (optional)"}
        widgets = {
            "comment": forms.Textarea(attrs={
                "rows": 4, "maxlength": 600,
                "placeholder": "What did they explain well? Anything they could do differently?",
            }),
        }

    def __init__(self, session, reviewer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Not form fields: set them so Review.clean() can check the session and pick the reviewee.
        self.instance.session = session
        self.instance.reviewer = reviewer
        self.fields["comment"].help_text = "Shown on their public profile."
