from io import BytesIO, StringIO

from PIL import Image

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from exchange.models import ExchangeRequest, LearningSession, Review
from skills.models import Category, Skill

User = get_user_model()


class SeedDemoTests(TestCase):
    def test_seed_creates_demo_world_and_is_repeatable(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(User.objects.count(), 8)
        self.assertEqual(Category.objects.count(), 7)
        self.assertTrue(Skill.objects.count() >= 20)
        self.assertTrue(ExchangeRequest.objects.filter(status=ExchangeRequest.Status.PENDING).exists())
        self.assertTrue(LearningSession.objects.filter(status=LearningSession.Status.CANCELLED).exists())
        self.assertTrue(Review.objects.exists())

        out = StringIO()
        call_command("seed_demo", stdout=out)  # second run leaves existing users alone
        self.assertIn("already exist", out.getvalue())
        self.assertEqual(User.objects.count(), 8)

        call_command("seed_demo", "--reset", stdout=StringIO())
        self.assertEqual(User.objects.count(), 8)


class HomePageTests(TestCase):
    def test_home_with_demo_data(self):
        call_command("seed_demo", stdout=StringIO())
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "The Index")
        self.assertContains(response, "From the community")
        self.assertEqual(len(response.context["members"]), 8)


class ReportsTests(TestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        self.url = reverse("core:reports")

    def test_staff_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)  # visitors go to admin login
        self.client.force_login(User.objects.get(username="aarav"))
        self.assertEqual(self.client.get(self.url).status_code, 302)  # regular members too

    def test_staff_sees_report(self):
        staff = User.objects.create_user("boss", password="x-Strong-pass-1", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        numbers = response.context["numbers"]
        self.assertEqual(numbers["members"], 9)
        self.assertEqual(numbers["requests"], ExchangeRequest.objects.count())
        self.assertTrue(response.context["teachers"])
        self.assertContains(response, "Skill demand vs supply")

    def test_admin_index_links_to_reports(self):
        admin_user = User.objects.create_superuser("root", "root@example.com", "x-Strong-pass-1")
        self.client.force_login(admin_user)
        self.assertContains(self.client.get(reverse("admin:index")), self.url)


class PolishTests(TestCase):
    def test_branded_404(self):
        response = self.client.get("/definitely-not-here/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "This page doesn't exist.", status_code=404)

    def test_branded_403_explains_why(self):
        call_command("seed_demo", stdout=StringIO())
        pending = ExchangeRequest.objects.filter(status=ExchangeRequest.Status.PENDING).first()
        self.client.force_login(pending.sender)  # the sender can't accept their own request
        response = self.client.post(reverse("exchange:action", args=[pending.pk, "accept"]))
        self.assertContains(response, "Only the person who received this request", status_code=403)

    def test_favicon_redirect(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].endswith("favicon.svg"))

    def test_skip_link_present(self):
        self.assertContains(self.client.get(reverse("core:home")), 'href="#main"')


@override_settings(AVATAR_MAX_BYTES=1024)
class AvatarUploadTests(TestCase):
    # A valid 1x1 GIF.
    GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
           b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

    def setUp(self):
        self.user = User.objects.create_user("neha", email="neha@example.com", password="x-Strong-pass-1")
        self.client.force_login(self.user)

    def post(self, upload):
        return self.client.post(reverse("accounts:profile_edit"), {
            "first_name": "Neha", "last_name": "", "email": "neha@example.com",
            "headline": "", "bio": "", "location": "", "availability": "", "avatar": upload,
        })

    def test_small_image_accepted(self):
        response = self.post(SimpleUploadedFile("me.gif", self.GIF, content_type="image/gif"))
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.avatar.name.startswith("avatars/"))
        self.user.profile.avatar.delete(save=False)  # don't leave test files in media/

    def test_too_large_rejected(self):
        big = self.GIF + b"\x00" * 2048
        response = self.post(SimpleUploadedFile("big.gif", big, content_type="image/gif"))
        self.assertContains(response, "The limit is 2 MB.")

    def test_wrong_type_rejected(self):
        # Django detects the format from the image data itself, so a real BMP is caught even
        # if the browser claims it's a GIF.
        buffer = BytesIO()
        Image.new("RGB", (1, 1)).save(buffer, format="BMP")
        response = self.post(SimpleUploadedFile("me.gif", buffer.getvalue(), content_type="image/gif"))
        self.assertContains(response, "Upload a JPG, PNG, WebP or GIF image.")


class SwapMapTests(TestCase):
    def test_map_data_from_demo(self):
        from core.geo import city_key, swap_map_data

        self.assertEqual(city_key("Bangalore, Karnataka"), "bengaluru")
        self.assertIsNone(city_key("Atlantis"))

        call_command("seed_demo", stdout=StringIO())
        data = swap_map_data()
        ids = {p["id"] for p in data["points"]}
        self.assertEqual(len(ids), 8)  # every demo member lives in a known city
        self.assertIn(["bengaluru", "delhi"], data["routes"])  # Aarav <-> Priya
        # Declined requests (Sara -> Kavya) don't draw a route.
        self.assertNotIn(["hyderabad", "kochi"], data["routes"])
        self.assertEqual(sum(p["members"] for p in data["points"]), 8)

    def test_home_embeds_map_and_effects(self):
        call_command("seed_demo", stdout=StringIO())
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="swap-map-data"')
        self.assertContains(response, "data-signal-map")
        self.assertContains(response, "data-luminous")
        self.assertContains(response, "data-blur-highlight")
        # The effects script must never block the first paint.
        self.assertContains(response, "js/effects.js?v=1\" defer")

    def test_barcode_filter(self):
        from core.templatetags.swap_tags import barcode_bars

        bars = barcode_bars("SS0001")
        self.assertTrue(len(bars) > 40)
        self.assertTrue(all(b["w"] in (1, 2, 3) for b in bars))


class PixelAvatarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("neha", email="neha@example.com", password="x-Strong-pass-1")

    def test_every_style_renders(self):
        from core.pixel_avatar import EXTRAS, HAIR_STYLES, render_svg

        for hair, _ in HAIR_STYLES:
            for extra, _ in EXTRAS:
                svg = render_svg(hair, "3", "brown", extra, "#ff6a3d", 64)
                self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"))
                self.assertIn('fill="#d29b6c"', svg)  # skin tone 3

    def test_bad_values_fall_back_safely(self):
        from core.pixel_avatar import render_svg

        svg = render_svg("<script>", "9", "nope", "x", "red;}", 32)
        self.assertNotIn("<script", svg)
        self.assertIn('fill="#8a8a8a"', svg)  # invalid shirt colour replaced

    def test_automatic_is_stable_and_choices_win(self):
        from core.pixel_avatar import options_for

        profile = self.user.profile
        self.assertEqual(options_for(profile), options_for(profile))
        profile.pixel_hair, profile.pixel_hair_colour = "headscarf", "teal"
        self.assertEqual(options_for(profile)["hair"], "headscarf")
        self.assertEqual(options_for(profile)["hair_colour"], "teal")

    def test_profile_form_saves_choices_and_preview(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:profile_edit"), {
            "first_name": "Neha", "last_name": "", "email": "neha@example.com",
            "headline": "", "bio": "", "location": "", "availability": "",
            "pixel_hair": "long", "pixel_hair_colour": "auburn", "pixel_skin": "5", "pixel_extra": "glasses",
        })
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.pixel_hair, "long")

        preview = self.client.get(reverse("core:avatar_preview"), {"hair": "bun"})
        self.assertEqual(preview["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", preview.content)

    def test_preview_needs_login(self):
        self.assertEqual(self.client.get(reverse("core:avatar_preview")).status_code, 302)

    def test_member_cards_show_pixel_heads(self):
        call_command("seed_demo", stdout=StringIO())
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'class="px-avatar"')
        self.assertContains(response, 'class="m-tile"')
