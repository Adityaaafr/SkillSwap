from django import template
from django.utils.safestring import mark_safe

from core.pixel_avatar import options_for, render_svg

register = template.Library()

# Bright, flat swatches that read well with near-black initials on top.
AVATAR_COLOURS = ["#ff6a3d", "#c8f169", "#8fd3ff", "#ffd23f", "#f4a3c8", "#b9a6ff", "#7ee0b5", "#e8e4d8"]


@register.filter
def initials(user):
    first, last = (user.first_name or "").strip(), (user.last_name or "").strip()
    if first or last:
        return f"{first[:1]}{last[:1]}".upper()
    return user.username[:2].upper()


@register.filter
def session_other(session, user):
    """The other person in a session or exchange: {{ s|session_other:user }}."""
    return session.other_party(user)


@register.filter
def avatar_colour(user):
    """A stable colour per user, used for avatars and the big member tiles."""
    weighted = sum((i + 1) * ord(ch) for i, ch in enumerate(user.username))
    return AVATAR_COLOURS[weighted % len(AVATAR_COLOURS)]


def _pixel_svg(user, size, crop):
    profile = getattr(user, "profile", None)
    if profile is None:
        return ""
    o = options_for(profile)
    return mark_safe(render_svg(o["hair"], o["skin"], o["hair_colour"], o["extra"], avatar_colour(user), size, crop))


@register.simple_tag
def pixel_avatar(user, size=128):
    """The member's full pixel avatar (head and shoulders), e.g. for member cards."""
    return _pixel_svg(user, size, crop=False)


@register.inclusion_tag("partials/_avatar.html")
def avatar(user, size=40):
    """Small square avatar: the uploaded photo if there is one, else the pixel head (cropped)."""
    profile = getattr(user, "profile", None)
    has_photo = bool(profile and profile.avatar)
    return {
        "user": user,
        "url": profile.avatar.url if has_photo else "",
        "size": size,
        "colour": avatar_colour(user),
        "pixel": "" if has_photo else _pixel_svg(user, size, crop=True),
    }


@register.inclusion_tag("partials/_stars.html")
def stars(rating, count=None):
    """Five stars rounded to the nearest half, e.g. {% stars 4.3 12 %}."""
    value = round(float(rating or 0) * 2) / 2
    full = int(value)
    half = (value - full) == 0.5
    return {
        "rating": rating,
        "count": count,
        "full": range(full),
        "half": half,
        "empty": range(5 - full - (1 if half else 0)),
    }


@register.filter
def barcode_bars(code):
    """Decorative barcode for receipts: each character's bits become thin and thick bars."""
    bars = [{"w": 2, "on": True}, {"w": 1, "on": False}, {"w": 1, "on": True}, {"w": 1, "on": False}]
    for ch in str(code):
        n = ord(ch)
        for bit in range(4):
            bars.append({"w": 3 if (n >> bit) & 1 else 1, "on": True})
            bars.append({"w": 2 if (n >> (bit + 4)) & 1 else 1, "on": False})
    bars += [{"w": 1, "on": True}, {"w": 1, "on": False}, {"w": 2, "on": True}]
    return bars
