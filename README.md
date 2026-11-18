<<<<<<< HEAD
# SkillSwap

**Learn together. Exchange knowledge. Grow together.**

SkillSwap is a peer-to-peer skill exchange built with Django and SQLite. Members list the skills they
can teach and the skills they want to learn, find each other, and arrange learning sessions. No money
changes hands: everyone is both a learner and a mentor.

Built for INT3253 as a moderately complex Django application with a real workflow, not just CRUD.

---

## Contents

1. [Run it locally](#run-it-locally)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Data model](#data-model)
5. [The exchange workflow](#the-exchange-workflow)
6. [Business rules](#business-rules)
7. [Pages and URLs](#pages-and-urls)
8. [Design](#design)
9. [Performance](#performance)
10. [Testing](#testing)
11. [Deployment notes](#deployment-notes)

---

## Run it locally

Requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # demo categories, skills, 8 members and exchange history
python manage.py createsuperuser  # your own admin account
python manage.py runserver
```

Open http://127.0.0.1:8000/.

**Demo accounts:** `aarav`, `priya`, `rohan`, `sara`, `kavya`, `ishaan`, `meera`, `vikram`. They share one
password, which is set at the top of `core/management/commands/seed_demo.py` and printed when the command runs.
Good starting points:

- `aarav`: has a mutual match (Priya), an active swap, an upcoming session and a review to write.
- `priya`: has incoming requests and reviews on her profile.
- `ishaan`: has a session from yesterday that still needs confirming.

Run `python manage.py seed_demo --reset` at any time to restore the demo data.
Staff accounts also get **Reports** at `/staff/reports/` and the admin at `/admin/`.

---

## Features

**Accounts and profiles**
- Registration (with unique email), login and logout using Django's built-in auth.
- A `Profile` is created automatically for every user by a `post_save` signal.
- Profile editing with photo upload (JPG/PNG/WebP/GIF, up to 2 MB) and a profile-completion meter.
- Public profiles with skills, rating, reviews, and highlights of skills the viewer could swap.

**Skills and discovery**
- Skills organised into categories, listed as "can teach" (with level) or "want to learn".
- **The Index**: every skill, numbered and grouped by category, with teacher and learner counts.
  Filter by category, sort five ways, and search by name, description or category.
- Search also lists the people who teach a matching skill.
- **Suggested swaps**: people who teach what you want *and* want what you teach, found with a single ORM query.

**Exchange requests**
- Request to learn a skill from someone, optionally offering one of your skills in return.
- Accept, decline or cancel, with incoming and sent tabs and status filters.
- A navbar badge shows how many requests are waiting for you.

**Learning sessions**
- Schedule sessions on accepted exchanges: skill, time, length, online or in person, link or place, plan.
- Double-booking protection across *all* of both people's sessions.
- Upcoming / To confirm / Past tabs, with "mark as done" and "cancel" actions.
- Download any session as an `.ics` file for Google Calendar, Outlook or Apple Calendar.

**Reviews and history**
- After a session is done, each participant can leave one 1–5 star review with an optional comment.
- Ratings appear on profiles, skill pages and the dashboard.
- **Activity**: a personal history of requests, sessions and reviews, grouped by month, with
  hours taught and learned, partners, skills taught and average rating.

**Admin and reporting**
- A configured Django admin: searchable, filterable lists with inline profiles, skills, sessions and reviews.
- **Reports** for staff: members, request funnel and acceptance rate, hours exchanged, top teachers,
  and skill demand vs supply (skills people want that nobody teaches).

**Pixel avatars**
- Every member has a pixel-art head-and-shoulders avatar, drawn as a tiny inline SVG (no image files).
- Members choose hair style, hair colour, skin tone and extras (glasses, beard) in Edit profile, with a live
  preview. Until they choose, a style is picked from their username. Uploaded photos take priority.

**Interactive components** (plain CSS and JavaScript, loaded with `defer`)
- **Luminous Type**: the home statement sits dimmed under a drifting spotlight that follows the pointer;
  click to light it all up.
- **Blur Highlight**: the "Why swap" paragraph sharpens and highlights key phrases as it scrolls into view.
- **Signal Map**: a dotted map of India with members' cities and signals arcing along real exchanges.
  Its script only downloads when the map is about to scroll into view.
- **Receipt Printer**: a printed "learning receipt" on the Activity page and a ticket on every session,
  fed line by line from a printer; drag it up to tear it off.

**Polish**
- Dark and light themes (remembered per browser), keyboard shortcut `/` for search, skip link,
  branded 403/404/500 pages, responsive layout down to phone width.
- Every animation respects `prefers-reduced-motion`, and content stays readable without JavaScript.

---

## Architecture

```
skillswap/
├── config/          settings, root URLs, WSGI/ASGI
├── core/            landing page, staff reports, shared form mixin, template tags, seed_demo command
├── accounts/        Profile model + signal, auth forms, dashboard, profiles
├── skills/          Category, Skill, UserSkill, explore/index, matching service
├── exchange/        ExchangeRequest, LearningSession, Review, requests/sessions/reviews/activity views
├── templates/       base layout, partials, one folder per app, error pages, admin index override
└── static/          css/style.css (the whole design system), favicon.svg
```

| App | Responsibility |
|---|---|
| `accounts` | Authentication and identity: registration, login, `Profile`, dashboard, public profiles |
| `skills` | Skill discovery: categories, skills, offered/wanted listings, search, filtering, matching |
| `exchange` | The workflow: requests, approvals, sessions, reviews, activity history |
| `core` | Shared pieces: landing page, reports, form styling, template tags, demo data |

Design choices worth knowing:

- **Fat models, thin views.** Every status change is a model method (`accept()`, `reject()`, `cancel()`,
  `mark_completed()`) that checks who is acting and what the current status is. Views just call it and
  show the result, so the rules live in one place and are easy to test.
- **Derived, not duplicated.** Ratings are calculated with `Avg()`, and the activity history is built from
  requests, sessions and reviews. There's no counter or activity table to drift out of sync.
- **Privacy by query.** Exchanges and sessions are fetched with `involving(user)` / `sessions_for(user)`, so
  anyone who isn't a participant gets a 404 and can't even tell the record exists.

---

## Data model

| Model | Purpose | Key relationships |
|---|---|---|
| `User` | Django's built-in auth user | |
| `Profile` | Headline, bio, photo, location, availability | one-to-one with `User` |
| `Category` | Groups skills | one-to-many with `Skill` |
| `Skill` | A teachable skill | FK to `Category` |
| `UserSkill` | A user teaches (with level) or wants a skill | **through table** for the User ↔ Skill many-to-many |
| `ExchangeRequest` | A request to learn a skill, optionally offering one back | FKs to sender, receiver, requested skill, offered skill |
| `LearningSession` | A scheduled session within an exchange | FK to exchange, skill, teacher, learner |
| `Review` | A 1–5 star review after a session | FK to session, reviewer, reviewee |

Database constraints back up the most important rules:

- `unique_user_skill_kind`: a skill appears once per list per user.
- `no_self_request` (check constraint): nobody can send a request to themselves.
- `one_pending_request_per_skill` (conditional unique constraint): no duplicate pending requests.
- `one_review_per_session_per_user` and `rating_between_1_and_5`.

---

## The exchange workflow

```
ExchangeRequest
  PENDING ──accept (receiver)──▶ ACCEPTED ──complete (either, ≥1 completed session)──▶ COMPLETED
     ├────reject (receiver)────▶ REJECTED
     └────cancel (sender)──────▶ CANCELLED

LearningSession (only on ACCEPTED exchanges)
  SCHEDULED ──mark done (participant, after start)──▶ COMPLETED ──▶ reviews unlocked
      └─────cancel (participant, before start)────▶ CANCELLED
```

1. **Discover**: find a skill in the Index, or a suggested swap on the dashboard.
2. **Request**: ask to learn it, offering one of your skills back.
3. **Accept or decline**: only the receiver can respond; the sender can cancel while it's pending.
4. **Schedule**: either person books sessions; teacher and learner are worked out from the skill.
5. **Learn and confirm**: after a session starts, either person marks it as done.
6. **Review**: each person rates the other; the exchange can then be marked completed.

---

## Business rules

| Rule | Where it's enforced |
|---|---|
| Can't request yourself | DB check constraint + `ExchangeRequest.clean()` |
| Receiver must teach the requested skill; sender must teach the offered one | `ExchangeRequest.clean()` + form querysets |
| One pending request per sender/receiver/skill | Conditional unique constraint + `clean()` |
| Only the receiver accepts/declines; only the sender cancels | `ExchangeRequest.accept()/reject()/cancel()` → 403 otherwise |
| Sessions only on accepted exchanges, in the future | `LearningSession.clean()` |
| No overlapping sessions for either person | `LearningSession.clashes()` |
| Mark done only after the start time; cancel only before it | `LearningSession.mark_completed()/cancel()` |
| Exchange completes only with ≥1 completed and no upcoming sessions | `ExchangeRequest.mark_completed()` |
| One review per person per session, only after completion | `Review.clean()` + unique constraint |
| Non-participants can't see exchanges or sessions | `involving()` / `sessions_for()` → 404 |
| State changes are POST-only with CSRF protection | `@require_POST` on every action view |

---

## Pages and URLs

| URL | Page |
|---|---|
| `/` | Landing page: wordmark, members strip, featured review, the Index |
| `/accounts/register/`, `/accounts/login/` | Sign up and log in |
| `/dashboard/` | Profile completion, stats, suggested swaps, upcoming sessions, requests, reviews due |
| `/u/<username>/` | Public profile |
| `/profile/edit/` | Edit account and profile |
| `/skills/`, `/skills/<slug>/` | Explore (the Index) and skill detail |
| `/my-skills/` | Manage skills you teach and want |
| `/requests/`, `/requests/<id>/` | Exchange requests and their detail |
| `/requests/new/<username>/` | Send a request |
| `/requests/<id>/sessions/new/` | Schedule a session |
| `/sessions/`, `/sessions/<id>/` | Sessions and their detail |
| `/sessions/<id>/calendar.ics` | Calendar download |
| `/sessions/<id>/review/` | Leave a review |
| `/activity/` | Your learning history |
| `/staff/reports/` | Platform report (staff only) |
| `/admin/` | Django admin |

---

## Design

The interface follows an editorial "index" structure: a thin four-slot top bar, a full-width wordmark,
ruled section bars with superscript counts, a horizontal card strip, a featured block, and numbered
category-grouped rows that invert on hover. It's flat and high-contrast, with hairline rules,
monospaced metadata, no rounded corners, and a single coral accent. Fonts are Anton (wordmark),
Geist (text) and Geist Mono (numbers and labels).

All styling lives in `static/css/style.css`, layered over Bootstrap 5.3 (used for the grid, utilities and
JavaScript components only). Colours are CSS variables, with a light theme alongside the default dark one.
When you change the stylesheet, bump `?v=` on its `<link>` in `templates/base.html` so browsers fetch the new file.

---

## Performance

- No render-blocking JavaScript: Bootstrap's bundle and the effects script load with `defer`.
- The icon stylesheet loads without blocking the first paint, and font and CDN hosts are preconnected.
- The Largest Contentful Paint element is the wordmark text, so the first screen needs no images.
- Avatars are inline SVG; uploaded photos have fixed dimensions and lazy loading, so layout never shifts.
- The swap map's code is fetched only when the map nears the viewport, and it pauses when off screen.

## Testing

```bash
python manage.py test
```

The suite (88 tests) covers the signal, registration, matching, every status change (including who may
perform it), double-booking, reviews, activity history, privacy (404s for outsiders), POST-only actions,
reports access, photo upload validation, the error pages, the swap map data, receipts and tickets, and
pixel avatars.

---

## Deployment notes

Settings default to local development. To run it anywhere public, set these environment variables:

| Variable | Example | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `0` | Turns off debug pages (required) |
| `DJANGO_SECRET_KEY` | a long random string | Required when debug is off; the app refuses to start without it |
| `DJANGO_ALLOWED_HOSTS` | `skillswap.example.com` | Comma-separated host names |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://skillswap.example.com` | Needed behind HTTPS proxies |
| `DJANGO_HTTPS` | `1` | Secure cookies, HTTPS redirect and HSTS (only once HTTPS works) |

Then run `python manage.py collectstatic` and serve `staticfiles/` and `media/` from your web server.
`python manage.py check --deploy` lists anything still missing.
=======
# SkillSwap
>>>>>>> 5085e485959774657e98f7792f83cb1a3c2debef
