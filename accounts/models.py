from django.conf import settings
from django.db import models

from core.pixel_avatar import EXTRA_CHOICES, HAIR_COLOUR_CHOICES, HAIR_STYLE_CHOICES, SKIN_TONE_CHOICES


class Profile(models.Model):
    """Extra information about a user. Created automatically by a post_save signal."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    headline = models.CharField(
        max_length=120, blank=True, help_text="One line about you, e.g. “CS student who loves Python”."
    )
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    location = models.CharField(max_length=100, blank=True)
    availability = models.CharField(
        max_length=200, blank=True, help_text="When you're usually free, e.g. “Weekday evenings”."
    )
    # Pixel avatar, shown whenever there's no uploaded photo. Blank = picked from the username.
    pixel_hair = models.CharField("hair style", max_length=12, blank=True, choices=HAIR_STYLE_CHOICES)
    pixel_hair_colour = models.CharField("hair colour", max_length=12, blank=True, choices=HAIR_COLOUR_CHOICES)
    pixel_skin = models.CharField("skin tone", max_length=2, blank=True, choices=SKIN_TONE_CHOICES)
    pixel_extra = models.CharField("extras", max_length=8, blank=True, choices=EXTRA_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.username

    def completion_details(self):
        """Return (percent_complete, list_of_missing_steps) for the dashboard."""
        from skills.models import UserSkill

        kinds = set(self.user.user_skills.values_list("kind", flat=True))
        checks = [
            ("Add a headline", bool(self.headline)),
            ("Write a short bio", bool(self.bio)),
            ("Upload a profile photo", bool(self.avatar)),
            ("Add your location", bool(self.location)),
            ("Share when you're available", bool(self.availability)),
            ("List a skill you can teach", UserSkill.Kind.OFFER in kinds),
            ("List a skill you want to learn", UserSkill.Kind.WANT in kinds),
        ]
        done = sum(1 for _, ok in checks if ok)
        percent = round(done * 100 / len(checks))
        missing = [label for label, ok in checks if not ok]
        return percent, missing
