from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=40, blank=True, help_text="Bootstrap Icons name, e.g. “code-slash”."
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"{reverse('skills:list')}?category={self.slug}"


class Skill(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="skills")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("skills:detail", args=[self.slug])


class UserSkill(models.Model):
    """A skill a user can teach (OFFER) or wants to learn (WANT).

    This is the explicit "through" table of the many-to-many relationship between User and Skill.
    """

    class Kind(models.TextChoices):
        OFFER = "offer", "I can teach this"
        WANT = "want", "I want to learn this"

    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        EXPERT = "expert", "Expert"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_skills"
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="user_skills")
    kind = models.CharField(max_length=5, choices=Kind.choices)
    level = models.CharField(max_length=12, choices=Level.choices, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["skill__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "skill", "kind"], name="unique_user_skill_kind"
            ),
        ]

    def __str__(self):
        verb = "teaches" if self.kind == self.Kind.OFFER else "wants to learn"
        return f"{self.user} {verb} {self.skill}"

    def clean(self):
        if self.kind == self.Kind.OFFER and not self.level:
            raise ValidationError({"level": "Tell learners how experienced you are."})
        if self.kind == self.Kind.WANT:
            self.level = ""

        if self.user_id and self.skill_id:
            others = UserSkill.objects.filter(user_id=self.user_id, skill_id=self.skill_id).exclude(
                pk=self.pk
            )
            if others.filter(kind=self.kind).exists():
                raise ValidationError({"skill": "This skill is already on your list."})
            if others.exists():
                raise ValidationError(
                    {"skill": "You can't both teach and want to learn the same skill."}
                )
