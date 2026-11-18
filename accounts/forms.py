from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from core.forms import BootstrapFormMixin

from .models import Profile

User = get_user_model()


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass


class UserUpdateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Another account already uses this email.")
        return email


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("headline", "bio", "location", "availability", "avatar",
                  "pixel_hair", "pixel_hair_colour", "pixel_skin", "pixel_extra")
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4, "placeholder": "What do you enjoy teaching? What are you curious about?"}),
            "location": forms.TextInput(attrs={"placeholder": "City, campus or “Online only”"}),
        }

    ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["avatar"].help_text = "JPG, PNG, WebP or GIF, up to 2 MB. A square image looks best."
        self.fields["avatar"].widget.attrs["accept"] = ",".join(sorted(self.ALLOWED_AVATAR_TYPES))
        for name in ("pixel_hair", "pixel_hair_colour", "pixel_skin", "pixel_extra"):
            field = self.fields[name]
            field.choices = [("", "Automatic")] + [c for c in field.choices if c[0] != ""]
            field.widget.attrs["data-px"] = name

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        # Only newly uploaded files have a content_type. Django's ImageField sets it from the
        # format Pillow detects in the file's bytes, not from what the browser claims.
        content_type = getattr(avatar, "content_type", None)
        if avatar and content_type:
            if content_type not in self.ALLOWED_AVATAR_TYPES:
                raise ValidationError("Upload a JPG, PNG, WebP or GIF image.")
            if avatar.size > settings.AVATAR_MAX_BYTES:
                raise ValidationError(f"That image is {avatar.size / 1024 / 1024:.1f} MB. The limit is 2 MB.")
        return avatar
