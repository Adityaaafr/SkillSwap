from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Skill, UserSkill
from .services import find_matches

User = get_user_model()
OFFER, WANT = UserSkill.Kind.OFFER, UserSkill.Kind.WANT


class SkillTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Category.objects.create(name="Programming")
        cls.python = Skill.objects.create(name="Python", category=cat)
        cls.design = Skill.objects.create(name="UI/UX Design", category=cat)
        cls.guitar = Skill.objects.create(name="Guitar", category=cat)
        cls.aarav = User.objects.create_user("aarav", password="x-Strong-pass-1")
        cls.priya = User.objects.create_user("priya", password="x-Strong-pass-1")
        cls.rohan = User.objects.create_user("rohan", password="x-Strong-pass-1")


class MatchingTests(SkillTestBase):
    def test_mutual_match_found(self):
        UserSkill.objects.create(user=self.aarav, skill=self.python, kind=OFFER, level="advanced")
        UserSkill.objects.create(user=self.aarav, skill=self.design, kind=WANT)
        UserSkill.objects.create(user=self.priya, skill=self.design, kind=OFFER, level="expert")
        UserSkill.objects.create(user=self.priya, skill=self.python, kind=WANT)
        # Rohan teaches what Aarav wants but doesn't want anything Aarav teaches: not a match.
        UserSkill.objects.create(user=self.rohan, skill=self.design, kind=OFFER, level="beginner")
        UserSkill.objects.create(user=self.rohan, skill=self.guitar, kind=WANT)

        matches = find_matches(self.aarav)
        self.assertEqual([m["user"] for m in matches], [self.priya])
        self.assertEqual(matches[0]["can_teach_you"], [self.design])
        self.assertEqual(matches[0]["wants_from_you"], [self.python])

    def test_no_matches_without_both_lists(self):
        UserSkill.objects.create(user=self.aarav, skill=self.python, kind=OFFER, level="advanced")
        self.assertEqual(find_matches(self.aarav), [])


class MySkillsViewTests(SkillTestBase):
    def setUp(self):
        self.client.force_login(self.aarav)

    def test_offer_requires_level(self):
        response = self.client.post(reverse("skills:my_skills"), {"skill": self.python.pk, "kind": OFFER})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserSkill.objects.exists())

    def test_add_and_reject_duplicate_or_conflicting(self):
        url = reverse("skills:my_skills")
        self.client.post(url, {"skill": self.python.pk, "kind": OFFER, "level": "advanced"})
        self.assertEqual(UserSkill.objects.count(), 1)
        self.client.post(url, {"skill": self.python.pk, "kind": OFFER, "level": "expert"})
        self.client.post(url, {"skill": self.python.pk, "kind": WANT})
        self.assertEqual(UserSkill.objects.count(), 1)

    def test_cannot_delete_someone_elses_skill(self):
        entry = UserSkill.objects.create(user=self.priya, skill=self.design, kind=OFFER, level="expert")
        response = self.client.post(reverse("skills:my_skill_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(UserSkill.objects.filter(pk=entry.pk).exists())

    def test_delete_requires_post(self):
        entry = UserSkill.objects.create(user=self.aarav, skill=self.python, kind=OFFER, level="expert")
        response = self.client.get(reverse("skills:my_skill_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 405)

    def test_explore_and_detail_pages(self):
        UserSkill.objects.create(user=self.priya, skill=self.design, kind=OFFER, level="expert")
        response = self.client.get(reverse("skills:list"), {"q": "design"})
        self.assertContains(response, "UI/UX Design")
        self.assertContains(response, "People who teach")
        response = self.client.get(self.design.get_absolute_url())
        self.assertContains(response, "priya")
