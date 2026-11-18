"""Fill the database with demo categories, skills, users and exchange activity.

    python manage.py seed_demo           # add demo data (skips users that already exist)
    python manage.py seed_demo --reset   # delete the demo users and recreate everything
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from exchange.models import ExchangeRequest, LearningSession, Review
from skills.models import Category, Skill, UserSkill

User = get_user_model()

# Shared password for the demo accounts below. Demo data only: never reuse it for real accounts.
DEMO_PASSWORD = "SkillSwap@123"

CATALOG = [
    ("Programming", "code-slash", "Write software, build apps and automate the boring stuff.", [
        ("Python", "General-purpose programming, scripting and data work."),
        ("JavaScript", "The language of the web, from DOM basics to modern frameworks."),
        ("Django", "Build database-backed web apps with Python."),
        ("Java", "Object-oriented programming and the JVM ecosystem."),
        ("SQL", "Query and design relational databases."),
    ]),
    ("Design", "palette", "Make things that look good and work well.", [
        ("UI/UX Design", "User research, wireframes, usability and interface design."),
        ("Figma", "Design and prototype interfaces collaboratively."),
        ("Graphic Design", "Layout, colour, typography and visual identity."),
    ]),
    ("Data & AI", "graph-up", "Turn data into insight and build intelligent systems.", [
        ("Data Analysis", "Clean, explore and visualise data with pandas and friends."),
        ("Machine Learning", "Train and evaluate predictive models."),
        ("Excel", "Formulas, pivot tables and dashboards."),
    ]),
    ("Languages", "translate", "Speak, read and write in a new language.", [
        ("English Communication", "Speaking confidently, writing clearly."),
        ("Japanese", "Hiragana, katakana and everyday conversation."),
        ("Spanish", "Conversation and grammar for beginners."),
        ("French", "Pronunciation, vocabulary and conversation."),
    ]),
    ("Music", "music-note-beamed", "Play, sing and understand music.", [
        ("Guitar", "Chords, strumming patterns and your first songs."),
        ("Piano", "Reading music, scales and simple pieces."),
        ("Singing", "Breath control, pitch and confidence."),
    ]),
    ("Career & Business", "briefcase", "Skills that help you study, work and lead.", [
        ("Public Speaking", "Plan, practise and deliver talks with confidence."),
        ("Digital Marketing", "SEO, social media and content strategy."),
        ("Video Editing", "Cut, colour and publish videos."),
    ]),
    ("Lifestyle", "heart", "Everything else worth learning.", [
        ("Cooking", "Everyday recipes and kitchen fundamentals."),
        ("Yoga", "Poses, breathing and building a routine."),
        ("Chess", "Openings, tactics and endgames."),
    ]),
]

USERS = [
    {
        "username": "aarav", "first": "Aarav", "last": "Kapoor", "location": "Delhi",
        "headline": "Backend developer in the making", "availability": "Weekday evenings",
        "bio": "Final-year CS student. I love building web apps with Django and want to make them look as good as they work.",
        "offers": [("Python", "advanced", "OOP, scripting and pandas basics"), ("Django", "intermediate", "Models, views and the admin")],
        "wants": ["UI/UX Design", "Figma"],
    },
    {
        "username": "priya", "first": "Priya", "last": "Sharma", "location": "Bengaluru",
        "headline": "Product designer who wants to code", "availability": "Weekends",
        "bio": "I design mobile apps and want to understand what developers do with my Figma files.",
        "offers": [("UI/UX Design", "advanced", "Wireframes to usability testing"), ("Figma", "expert", "Auto layout, components, prototyping")],
        "wants": ["Python", "Public Speaking"],
    },
    {
        "username": "rohan", "first": "Rohan", "last": "Mehta", "location": "Mumbai",
        "headline": "Guitarist and debate club captain", "availability": "Evenings after 7pm",
        "bio": "I've played guitar for ten years and coached our college debate team.",
        "offers": [("Guitar", "expert", "Acoustic and fingerstyle"), ("Public Speaking", "advanced", "Debate and presentations")],
        "wants": ["Python", "Japanese"],
    },
    {
        "username": "sara", "first": "Sara", "last": "Joseph", "location": "Kochi",
        "headline": "Language nerd, JLPT N2", "availability": "Weekday mornings",
        "bio": "I lived in Osaka for two years and teach Japanese and English conversation.",
        "offers": [("Japanese", "advanced", "Conversation and JLPT prep"), ("English Communication", "expert", "Interviews and presentations")],
        "wants": ["Guitar", "Data Analysis"],
    },
    {
        "username": "kavya", "first": "Kavya", "last": "Reddy", "location": "Hyderabad",
        "headline": "Data analyst at a fintech startup", "availability": "Saturday afternoons",
        "bio": "I spend my days in SQL and pandas, and want to move into machine learning.",
        "offers": [("Data Analysis", "advanced", "pandas, matplotlib, storytelling"), ("Excel", "expert", "Pivot tables and dashboards"), ("SQL", "advanced", "Joins, window functions")],
        "wants": ["Machine Learning", "Spanish"],
    },
    {
        "username": "ishaan", "first": "Ishaan", "last": "Patel", "location": "Ahmedabad",
        "headline": "ML researcher who can't cook", "availability": "Flexible",
        "bio": "I work on computer vision research. My cooking skills are limited to instant noodles.",
        "offers": [("Machine Learning", "expert", "scikit-learn and PyTorch"), ("Python", "advanced", "NumPy and clean code")],
        "wants": ["Cooking", "SQL"],
    },
    {
        "username": "meera", "first": "Meera", "last": "Das", "location": "Kolkata",
        "headline": "Home chef and yoga teacher", "availability": "Early mornings",
        "bio": "Certified yoga instructor. I also run a small home kitchen and love teaching Bengali recipes.",
        "offers": [("Cooking", "expert", "Indian home cooking"), ("Yoga", "expert", "Hatha yoga for beginners")],
        "wants": ["JavaScript", "Machine Learning"],
    },
    {
        "username": "vikram", "first": "Vikram", "last": "Thakur", "location": "Pune",
        "headline": "Front-end developer and chess player", "availability": "Weekends",
        "bio": "React developer by day, 1900-rated chess player by night.",
        "offers": [("JavaScript", "expert", "Modern JS and React"), ("Chess", "advanced", "Openings and tactics")],
        "wants": ["Yoga", "Figma"],
    },
]

# Pixel avatars for the demo members: (hair style, hair colour, skin tone, extras).
AVATARS = {
    "aarav": ('short', 'black', '3', 'none'),
    "priya": ('long', 'black', '3', 'none'),
    "rohan": ('curly', 'black', '4', 'none'),
    "sara": ('bun', 'brown', '2', 'glasses'),
    "kavya": ('long', 'brown', '3', 'glasses'),
    "ishaan": ('spiky', 'black', '3', 'glasses'),
    "meera": ('bun', 'black', '4', 'none'),
    "vikram": ('buzz', 'black', '4', 'beard'),
}


class Command(BaseCommand):
    help = "Create demo categories, skills, users and exchange activity."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the demo users first and recreate them.")

    @transaction.atomic
    def handle(self, *args, **options):
        skills = self.seed_catalog()
        usernames = [u["username"] for u in USERS]

        if options["reset"]:
            deleted = User.objects.filter(username__in=usernames).delete()[0]
            self.stdout.write(f"Deleted {deleted} demo rows.")
        if User.objects.filter(username__in=usernames).exists():
            self.stdout.write(self.style.WARNING("Demo users already exist. Run with --reset to recreate them."))
            return

        users = self.seed_users(skills)
        self.seed_activity(users, skills)
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(users)} demo users ({', '.join(usernames)}). Password for all of them: {DEMO_PASSWORD}"
        ))

    def seed_catalog(self):
        skills = {}
        for cat_name, icon, cat_desc, items in CATALOG:
            category, _ = Category.objects.update_or_create(
                name=cat_name, defaults={"icon": icon, "description": cat_desc}
            )
            for name, desc in items:
                skill, _ = Skill.objects.update_or_create(
                    name=name, defaults={"category": category, "description": desc}
                )
                skills[name] = skill
        self.stdout.write(f"Catalog ready: {Category.objects.count()} categories, {Skill.objects.count()} skills.")
        return skills

    def seed_users(self, skills):
        users = {}
        for data in USERS:
            user = User.objects.create_user(
                username=data["username"], password=DEMO_PASSWORD,
                first_name=data["first"], last_name=data["last"],
                email=f"{data['username']}@example.com",
            )
            profile = user.profile
            profile.headline = data["headline"]
            profile.bio = data["bio"]
            profile.location = data["location"]
            profile.availability = data["availability"]
            hair, colour, skin, extra = AVATARS.get(data["username"], ("", "", "", ""))
            profile.pixel_hair, profile.pixel_hair_colour, profile.pixel_skin, profile.pixel_extra = hair, colour, skin, extra
            profile.save()
            for skill_name, level, note in data["offers"]:
                UserSkill.objects.create(user=user, skill=skills[skill_name], kind=UserSkill.Kind.OFFER, level=level, note=note)
            for skill_name in data["wants"]:
                UserSkill.objects.create(user=user, skill=skills[skill_name], kind=UserSkill.Kind.WANT)
            users[data["username"]] = user
        return users

    def seed_activity(self, u, s):
        now = timezone.now()

        def exchange(sender, receiver, requested, offered=None, status=ExchangeRequest.Status.PENDING,
                     message="", days_ago=1):
            ex = ExchangeRequest.objects.create(
                sender=u[sender], receiver=u[receiver], requested_skill=s[requested],
                offered_skill=s[offered] if offered else None, status=status, message=message,
            )
            created = now - timedelta(days=days_ago)
            responded = created + timedelta(hours=6) if status != ExchangeRequest.Status.PENDING else None
            completed = now - timedelta(days=1) if status == ExchangeRequest.Status.COMPLETED else None
            ExchangeRequest.objects.filter(pk=ex.pk).update(
                created_at=created, responded_at=responded, completed_at=completed
            )
            ex.refresh_from_db()
            return ex

        def session(ex, skill, days_from_now, status=LearningSession.Status.SCHEDULED, hour=18):
            when = timezone.localtime(now + timedelta(days=days_from_now)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            return LearningSession.objects.create(
                exchange=ex, skill=s[skill], scheduled_at=when, duration_minutes=60,
                mode=LearningSession.Mode.ONLINE, location_or_link="https://meet.example.com/skillswap",
                status=status, created_by=ex.sender,
                completed_at=when + timedelta(hours=1) if status == LearningSession.Status.COMPLETED else None,
            )

        def review(sess, reviewer, rating, comment):
            Review.objects.create(session=sess, reviewer=u[reviewer], rating=rating, comment=comment)

        done = LearningSession.Status.COMPLETED

        # Aarav <-> Priya: an active two-way swap with history and an upcoming session.
        ex = exchange("aarav", "priya", "UI/UX Design", "Python", ExchangeRequest.Status.ACCEPTED,
                      "Hi Priya! I'd love to learn UI/UX basics. Happy to teach you Python in return.", days_ago=10)
        u_ex_aarav_priya = ex
        s1 = session(ex, "UI/UX Design", -6, done)
        s2 = session(ex, "Python", -4, done)
        session(ex, "UI/UX Design", 2)
        review(s1, "aarav", 5, "Priya explained design heuristics with real examples. Super clear.")
        review(s1, "priya", 4, "Aarav came prepared with questions. Great learner!")
        review(s2, "priya", 5, "Finally understand list comprehensions. Patient teacher.")

        # Kavya <-> Ishaan: a finished swap.
        ex = exchange("kavya", "ishaan", "Machine Learning", "SQL", ExchangeRequest.Status.COMPLETED,
                      "Could you walk me through ML fundamentals? I can help with SQL.", days_ago=20)
        s3 = session(ex, "Machine Learning", -12, done)
        s4 = session(ex, "SQL", -10, done)
        review(s3, "kavya", 5, "Ishaan made gradient descent click for me.")
        review(s4, "ishaan", 4, "Window functions are now my favourite thing. Thanks Kavya!")
        review(s3, "ishaan", 5, "Kavya asked brilliant questions.")

        # Meera <-> Ishaan: accepted; yesterday's session still needs confirming, next one coming up.
        ex = exchange("meera", "ishaan", "Machine Learning", "Cooking", ExchangeRequest.Status.ACCEPTED,
                      "I'd like to understand ML. I'll teach you to cook something better than noodles!", days_ago=3)
        session(ex, "Machine Learning", -1, hour=19)
        session(ex, "Cooking", 3, hour=8)

        # A cancelled session, so the "Past" tab shows more than one state.
        cancelled = session(u_ex_aarav_priya, "Python", -8)
        LearningSession.objects.filter(pk=cancelled.pk).update(status=LearningSession.Status.CANCELLED)

        # Pending requests waiting on a reply.
        exchange("rohan", "sara", "Japanese", "Guitar",
                 message="Konnichiwa! Guitar lessons in exchange for Japanese?", days_ago=1)
        exchange("vikram", "meera", "Yoga", "JavaScript",
                 message="My back hates my desk. Yoga for JavaScript?", days_ago=2)
        exchange("priya", "rohan", "Public Speaking",
                 message="I have a design conference talk coming up. Could you help me prepare?", days_ago=1)

        # A declined one-way request.
        exchange("sara", "kavya", "Data Analysis", status=ExchangeRequest.Status.REJECTED,
                 message="Would you teach me pandas?", days_ago=5)
