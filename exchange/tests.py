from datetime import timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from skills.models import Category, Skill, UserSkill

from .models import ExchangeRequest, LearningSession, Review

User = get_user_model()


class ExchangeTestBase(TestCase):
    def setUp(self):
        cat = Category.objects.create(name="Programming")
        self.python = Skill.objects.create(name="Python", category=cat)
        self.design = Skill.objects.create(name="UI/UX Design", category=cat)
        self.aarav = User.objects.create_user("aarav", password="x-Strong-pass-1")
        self.priya = User.objects.create_user("priya", password="x-Strong-pass-1")
        self.outsider = User.objects.create_user("rohan", password="x-Strong-pass-1")
        UserSkill.objects.create(user=self.aarav, skill=self.python, kind="offer", level="advanced")
        UserSkill.objects.create(user=self.priya, skill=self.design, kind="offer", level="expert")
        self.exchange = ExchangeRequest.objects.create(
            sender=self.aarav, receiver=self.priya,
            requested_skill=self.design, offered_skill=self.python, message="Swap?",
        )

    def make_session(self, skill, days):
        self.exchange.status = ExchangeRequest.Status.ACCEPTED
        self.exchange.save()
        return LearningSession.objects.create(
            exchange=self.exchange, skill=skill, created_by=self.aarav,
            scheduled_at=timezone.now() + timedelta(days=days),
        )


class ExchangeRequestRuleTests(ExchangeTestBase):
    def test_only_receiver_can_accept(self):
        with self.assertRaises(PermissionDenied):
            self.exchange.accept(self.aarav)
        self.exchange.accept(self.priya)
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.ACCEPTED)

    def test_cannot_accept_twice(self):
        self.exchange.accept(self.priya)
        with self.assertRaises(ValidationError):
            self.exchange.accept(self.priya)

    def test_only_sender_can_cancel(self):
        with self.assertRaises(PermissionDenied):
            self.exchange.cancel(self.priya)
        self.exchange.cancel(self.aarav)
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.CANCELLED)

    def test_clean_rejects_skill_receiver_does_not_offer(self):
        bad = ExchangeRequest(sender=self.priya, receiver=self.aarav, requested_skill=self.design, message="Hi")
        with self.assertRaises(ValidationError) as ctx:
            bad.full_clean()
        self.assertIn("requested_skill", ctx.exception.message_dict)

    def test_clean_rejects_duplicate_pending_request(self):
        dup = ExchangeRequest(sender=self.aarav, receiver=self.priya, requested_skill=self.design, message="Again")
        with self.assertRaises(ValidationError):
            dup.full_clean()

    def test_database_blocks_self_request(self):
        with self.assertRaises(IntegrityError):
            ExchangeRequest.objects.create(
                sender=self.aarav, receiver=self.aarav, requested_skill=self.python, message="Me"
            )

    def test_complete_needs_a_finished_session(self):
        self.exchange.accept(self.priya)
        with self.assertRaises(ValidationError):
            self.exchange.mark_completed(self.aarav)


class SessionAndReviewTests(ExchangeTestBase):
    def test_roles_follow_from_skill(self):
        learn = self.make_session(self.design, 1)
        teach = self.make_session(self.python, 2)
        self.assertEqual((learn.teacher, learn.learner), (self.priya, self.aarav))
        self.assertEqual((teach.teacher, teach.learner), (self.aarav, self.priya))

    def test_cannot_schedule_on_pending_exchange(self):
        session = LearningSession(
            exchange=self.exchange, skill=self.design, created_by=self.aarav,
            scheduled_at=timezone.now() + timedelta(days=1),
        )
        with self.assertRaisesMessage(ValidationError, "only be scheduled for accepted exchanges"):
            session.full_clean()

    def test_cannot_complete_before_start(self):
        session = self.make_session(self.design, 1)
        with self.assertRaises(ValidationError):
            session.mark_completed(self.aarav)

    def test_outsider_cannot_complete(self):
        session = self.make_session(self.design, -1)
        with self.assertRaises(PermissionDenied):
            session.mark_completed(self.outsider)

    def test_review_flow(self):
        session = self.make_session(self.design, -1)
        self.assertFalse(session.can_review(self.aarav))
        session.mark_completed(self.aarav)
        self.assertTrue(session.can_review(self.aarav))

        review = Review(session=session, reviewer=self.aarav, rating=5, comment="Great")
        review.full_clean()
        review.save()
        self.assertEqual(review.reviewee, self.priya)
        self.assertFalse(session.can_review(self.aarav))

        with self.assertRaisesMessage(ValidationError, "already reviewed"):
            Review(session=session, reviewer=self.aarav, rating=4).full_clean()
        with self.assertRaisesMessage(ValidationError, "Only the people in this session"):
            Review(session=session, reviewer=self.outsider, rating=4).full_clean()

    def test_exchange_completes_after_sessions(self):
        session = self.make_session(self.design, -1)
        session.mark_completed(self.priya)
        self.exchange.mark_completed(self.aarav)
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.COMPLETED)


class RequestViewTests(ExchangeTestBase):
    def action_url(self, action, exchange=None):
        return reverse("exchange:action", args=[(exchange or self.exchange).pk, action])

    def test_send_request(self):
        self.exchange.delete()
        self.client.force_login(self.aarav)
        url = reverse("exchange:create", args=["priya"])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {
            "requested_skill": self.design.pk, "offered_skill": self.python.pk, "message": "Swap?",
        })
        exchange = ExchangeRequest.objects.get()
        self.assertRedirects(response, reverse("exchange:detail", args=[exchange.pk]))
        self.assertEqual((exchange.sender, exchange.receiver), (self.aarav, self.priya))
        self.assertEqual(exchange.status, ExchangeRequest.Status.PENDING)

    def test_cannot_request_skill_receiver_does_not_teach(self):
        self.client.force_login(self.priya)
        response = self.client.post(reverse("exchange:create", args=["aarav"]), {
            "requested_skill": self.design.pk, "message": "Hi",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExchangeRequest.objects.count(), 1)

    def test_duplicate_pending_request_shows_error(self):
        self.client.force_login(self.aarav)
        response = self.client.post(reverse("exchange:create", args=["priya"]), {
            "requested_skill": self.design.pk, "message": "Again",
        })
        self.assertContains(response, "already have a pending request")
        self.assertEqual(ExchangeRequest.objects.count(), 1)

    def test_cannot_request_yourself(self):
        self.client.force_login(self.aarav)
        response = self.client.get(reverse("exchange:create", args=["aarav"]))
        self.assertRedirects(response, reverse("accounts:profile", args=["aarav"]))

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("exchange:detail", args=[self.exchange.pk])).status_code, 404)
        self.assertEqual(self.client.post(self.action_url("accept")).status_code, 404)

    def test_receiver_accepts(self):
        self.client.force_login(self.priya)
        self.client.post(self.action_url("accept"))
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.ACCEPTED)

    def test_sender_cannot_accept_own_request(self):
        self.client.force_login(self.aarav)
        self.assertEqual(self.client.post(self.action_url("accept")).status_code, 403)
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.PENDING)

    def test_invalid_transition_shows_message(self):
        self.client.force_login(self.priya)
        self.client.post(self.action_url("reject"))
        response = self.client.post(self.action_url("accept"), follow=True)
        self.assertContains(response, "Only pending requests can be accepted.")

    def test_actions_require_post_and_known_action(self):
        self.client.force_login(self.priya)
        self.assertEqual(self.client.get(self.action_url("accept")).status_code, 405)
        self.assertEqual(self.client.post(self.action_url("explode")).status_code, 404)

    def test_list_tabs(self):
        self.client.force_login(self.priya)
        response = self.client.get(reverse("exchange:list"))
        self.assertContains(response, "wants to learn")
        response = self.client.get(reverse("exchange:list"), {"tab": "outgoing"})
        self.assertNotContains(response, "wants to learn")
        self.assertEqual(response.context["pending_request_count"], 1)


def local_input(dt):
    """Format a datetime the way <input type="datetime-local"> submits it."""
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


class SessionClashTests(ExchangeTestBase):
    def setUp(self):
        super().setUp()
        self.start = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        self.first = self.make_session(self.design, 0)
        self.first.scheduled_at = self.start
        self.first.save()

    def new_session(self, minutes_after_start, exchange=None):
        return LearningSession(
            exchange=exchange or self.exchange, skill=self.python, created_by=self.aarav,
            scheduled_at=self.start + timedelta(minutes=minutes_after_start), duration_minutes=60,
        )

    def test_overlapping_session_rejected(self):
        with self.assertRaisesMessage(ValidationError, "overlaps another session"):
            self.new_session(30).full_clean()

    def test_session_ending_inside_rejected(self):
        with self.assertRaisesMessage(ValidationError, "overlaps another session"):
            self.new_session(-30).full_clean()

    def test_back_to_back_sessions_allowed(self):
        self.new_session(60).full_clean()
        self.new_session(-60).full_clean()

    def test_cancelled_sessions_do_not_block(self):
        self.first.status = LearningSession.Status.CANCELLED
        self.first.save()
        self.new_session(0).full_clean()

    def test_clash_with_a_different_exchange(self):
        # Priya is busy teaching Rohan at the same time in another exchange.
        other = ExchangeRequest.objects.create(
            sender=self.outsider, receiver=self.priya, requested_skill=self.design,
            message="Hi", status=ExchangeRequest.Status.ACCEPTED,
        )
        LearningSession.objects.create(
            exchange=other, skill=self.design, created_by=self.outsider,
            scheduled_at=self.start + timedelta(hours=3),
        )
        with self.assertRaisesMessage(ValidationError, "overlaps another session"):
            self.new_session(180).full_clean()


class SessionViewTests(ExchangeTestBase):
    def setUp(self):
        super().setUp()
        self.exchange.accept(self.priya)
        self.client.force_login(self.aarav)
        self.create_url = reverse("exchange:session_create", args=[self.exchange.pk])

    def post_session(self, **overrides):
        data = {
            "skill": self.design.pk,
            "scheduled_at": local_input(timezone.now() + timedelta(days=3)),
            "duration_minutes": 60,
            "mode": "online",
            "location_or_link": "https://meet.example.com/abc",
            "agenda": "Wireframes",
        }
        data.update(overrides)
        return self.client.post(self.create_url, data)

    def test_schedule_session(self):
        self.assertEqual(self.client.get(self.create_url).status_code, 200)
        response = self.post_session()
        session = LearningSession.objects.get()
        detail = reverse("exchange:session_detail", args=[session.pk])
        self.assertRedirects(response, detail + "?booked=1")
        self.assertEqual((session.teacher, session.learner, session.created_by), (self.priya, self.aarav, self.aarav))
        # The booking page prints a ticket straight away.
        page = self.client.get(detail + "?booked=1")
        self.assertTrue(page.context["print_ticket"])
        self.assertContains(page, "Session ticket")
        self.assertContains(page, 'data-autoplay="1"')

    def test_cannot_schedule_in_the_past(self):
        response = self.post_session(scheduled_at=local_input(timezone.now() - timedelta(hours=2)))
        self.assertContains(response, "Pick a time in the future.")
        self.assertFalse(LearningSession.objects.exists())

    def test_in_person_needs_a_place(self):
        response = self.post_session(mode="in_person", location_or_link="")
        self.assertContains(response, "Say where you&#x27;ll meet.")

    def test_only_exchange_skills_allowed(self):
        cat = self.design.category
        other_skill = Skill.objects.create(name="Chess", category=cat)
        response = self.post_session(skill=other_skill.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LearningSession.objects.exists())

    def test_pending_exchange_redirects(self):
        pending = ExchangeRequest.objects.create(
            sender=self.priya, receiver=self.aarav, requested_skill=self.python, message="Hi"
        )
        response = self.client.get(reverse("exchange:session_create", args=[pending.pk]))
        self.assertRedirects(response, reverse("exchange:detail", args=[pending.pk]))

    def test_outsider_cannot_see_or_act(self):
        session = self.make_session(self.design, 1)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("exchange:session_detail", args=[session.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("exchange:session_action", args=[session.pk, "cancel"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("exchange:session_calendar", args=[session.pk])).status_code, 404)
        self.assertEqual(self.client.get(self.create_url).status_code, 404)

    def test_complete_and_cancel_actions(self):
        future = self.make_session(self.design, 1)
        response = self.client.post(reverse("exchange:session_action", args=[future.pk, "complete"]), follow=True)
        self.assertContains(response, "once it has started")
        self.client.post(reverse("exchange:session_action", args=[future.pk, "cancel"]))
        future.refresh_from_db()
        self.assertEqual(future.status, LearningSession.Status.CANCELLED)

        started = self.make_session(self.python, -1)
        self.client.post(reverse("exchange:session_action", args=[started.pk, "complete"]))
        started.refresh_from_db()
        self.assertEqual(started.status, LearningSession.Status.COMPLETED)

    def test_calendar_download(self):
        session = self.make_session(self.design, 1)
        response = self.client.get(reverse("exchange:session_calendar", args=[session.pk]))
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        body = response.content.decode()
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn("SUMMARY:SkillSwap: UI/UX Design with priya", body)
        self.assertIn(f"DTSTART:{session.scheduled_at.astimezone(dt_timezone.utc):%Y%m%dT%H%M%SZ}", body)

    def test_session_list_tabs(self):
        self.make_session(self.design, 1)
        self.make_session(self.python, -1)
        response = self.client.get(reverse("exchange:sessions"))
        self.assertEqual(response.context["tab"], "confirm")  # opens on what needs attention
        self.assertContains(response, "To confirm")
        response = self.client.get(reverse("exchange:sessions"), {"tab": "upcoming"})
        self.assertEqual(len(response.context["sessions"]), 1)


class ReviewViewTests(ExchangeTestBase):
    def setUp(self):
        super().setUp()
        self.session = self.make_session(self.design, -1)  # Priya teaches Aarav, started yesterday
        self.session.mark_completed(self.aarav)
        self.url = reverse("exchange:session_review", args=[self.session.pk])
        self.client.force_login(self.aarav)

    def test_leave_review(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.post(self.url, {"rating": 5, "comment": "Super clear."})
        self.assertRedirects(response, reverse("exchange:session_detail", args=[self.session.pk]))
        review = Review.objects.get()
        self.assertEqual((review.reviewer, review.reviewee, review.rating), (self.aarav, self.priya, 5))

    def test_review_shows_on_profile(self):
        self.client.post(self.url, {"rating": 4, "comment": "Patient and well prepared."})
        response = self.client.get(reverse("accounts:profile", args=["priya"]))
        self.assertContains(response, "Patient and well prepared.")

    def test_rating_required_and_in_range(self):
        self.assertContains(self.client.post(self.url, {"comment": "x"}), "Choose a rating")
        self.assertEqual(self.client.post(self.url, {"rating": 6}).status_code, 200)
        self.assertFalse(Review.objects.exists())

    def test_only_one_review_per_person(self):
        self.client.post(self.url, {"rating": 5})
        response = self.client.post(self.url, {"rating": 1}, follow=True)
        self.assertContains(response, "already reviewed")
        self.assertEqual(Review.objects.get().rating, 5)

    def test_both_people_can_review(self):
        self.client.post(self.url, {"rating": 5})
        self.client.force_login(self.priya)
        self.client.post(self.url, {"rating": 4})
        self.assertEqual(
            set(Review.objects.values_list("reviewer__username", "reviewee__username")),
            {("aarav", "priya"), ("priya", "aarav")},
        )

    def test_cannot_review_unfinished_session(self):
        upcoming = self.make_session(self.python, 2)
        response = self.client.get(reverse("exchange:session_review", args=[upcoming.pk]))
        self.assertRedirects(response, reverse("exchange:session_detail", args=[upcoming.pk]))

    def test_outsider_cannot_review(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.url, {"rating": 1}).status_code, 404)
        self.assertFalse(Review.objects.exists())


class ActivityTests(ExchangeTestBase):
    def setUp(self):
        super().setUp()
        self.exchange.accept(self.priya)
        session = self.make_session(self.design, -1)
        session.duration_minutes = 90
        session.save()
        session.mark_completed(self.priya)
        Review.objects.create(session=session, reviewer=self.priya, rating=4, comment="Great questions")
        self.client.force_login(self.aarav)

    def test_history_lists_everything(self):
        response = self.client.get(reverse("exchange:activity"))
        kinds = [e.kind for e in response.context["events"]]
        self.assertEqual(sorted(set(kinds)), ["request", "review", "session"])
        self.assertContains(response, "You learned UI/UX Design from priya")
        self.assertContains(response, "priya reviewed you")
        self.assertContains(response, "Great questions")

    def test_filter_by_type(self):
        response = self.client.get(reverse("exchange:activity"), {"type": "reviews"})
        self.assertEqual({e.kind for e in response.context["events"]}, {"review"})

    def test_summary_numbers(self):
        summary = self.client.get(reverse("exchange:activity")).context["summary"]
        self.assertEqual(summary["learned_sessions"], 1)
        self.assertEqual(summary["learned_hours"], 1.5)
        self.assertEqual(summary["taught_sessions"], 0)
        self.assertEqual(summary["partners"], 1)
        self.assertEqual(summary["rating_avg"], 4)

    def test_history_is_private(self):
        self.client.logout()
        response = self.client.get(reverse("exchange:activity"))
        self.assertEqual(response.status_code, 302)


class ReceiptTests(ActivityTests):
    def test_activity_has_learning_receipt(self):
        response = self.client.get(reverse("exchange:activity"))
        receipt = response.context["receipt"]
        self.assertEqual(receipt["subtitle"], "Learning receipt")
        values = {line.get("label"): line.get("value") for line in receipt["lines"]}
        self.assertEqual(values["Money spent"], "₹0.00")
        self.assertEqual(values["Knowledge swapped"], "1.5 h")
        self.assertContains(response, "data-receipt")

    def test_cancelled_session_has_no_ticket(self):
        session = LearningSession.objects.get()
        session.status = LearningSession.Status.CANCELLED
        session.save()
        response = self.client.get(reverse("exchange:session_detail", args=[session.pk]))
        self.assertIsNone(response.context["ticket"])
