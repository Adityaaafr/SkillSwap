from itertools import groupby

from django import forms

from core.forms import BootstrapFormMixin

from .models import Skill, UserSkill


class UserSkillForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = UserSkill
        fields = ("skill", "kind", "level", "note")
        labels = {"kind": "I…", "note": "Details (optional)"}
        widgets = {
            "note": forms.TextInput(attrs={"placeholder": "e.g. Can help with Django REST APIs"}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The user isn't a form field, so set it on the instance before validation runs.
        self.instance.user = user

        skills = Skill.objects.select_related("category").order_by("category__name", "name")
        self.fields["skill"].queryset = skills
        # Show the dropdown grouped by category (<optgroup>).
        grouped = [("", "Choose a skill…")]
        for category, items in groupby(skills, key=lambda s: s.category.name):
            grouped.append((category, [(s.pk, s.name) for s in items]))
        self.fields["skill"].choices = grouped

        self.fields["level"].required = False
        self.fields["level"].help_text = "Needed when you offer to teach."
