from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Profile

User = get_user_model()


class ProfileSignalTests(TestCase):
    def test_profile_created_for_new_user(self):
        user = User.objects.create_user("neha", password="x-Strong-pass-1")
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_completion_starts_low_and_lists_missing_steps(self):
        user = User.objects.create_user("neha", password="x-Strong-pass-1")
        percent, missing = user.profile.completion_details()
        self.assertEqual(percent, 0)
        self.assertIn("Write a short bio", missing)


class AuthViewTests(TestCase):
    def test_register_logs_user_in_and_redirects(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "neha", "first_name": "Neha", "last_name": "", "email": "neha@example.com",
            "password1": "x-Strong-pass-1", "password2": "x-Strong-pass-1",
        })
        self.assertRedirects(response, reverse("skills:my_skills"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="neha").pk)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user("first", email="dup@example.com", password="x-Strong-pass-1")
        response = self.client.post(reverse("accounts:register"), {
            "username": "second", "first_name": "S", "email": "DUP@example.com",
            "password1": "x-Strong-pass-1", "password2": "x-Strong-pass-1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:dashboard')}")

    def test_pages_render(self):
        user = User.objects.create_user("neha", password="x-Strong-pass-1")
        self.client.force_login(user)
        for url in [
            reverse("core:home"),
            reverse("accounts:dashboard"),
            reverse("accounts:profile", args=["neha"]),
            reverse("accounts:profile_edit"),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
