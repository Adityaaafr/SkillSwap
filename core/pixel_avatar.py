"""Pixel-art head-and-shoulders avatars, drawn as tiny inline SVGs (no image files, no requests).

Each avatar is a 16x16 grid built from layers: hair behind the head, the face and shirt, hair in
front, then extras (glasses, beard). Members choose every option themselves in Edit profile; until
they do, the options are picked from a hash of their username so each person still looks distinct.
"""
from functools import lru_cache
from hashlib import md5

HAIR_STYLES = [
    ("short", "Short"), ("long", "Long"), ("bun", "Bun"), ("curly", "Curly"),
    ("spiky", "Spiky"), ("buzz", "Buzz cut"), ("headscarf", "Headscarf"), ("bald", "Bald"),
]
SKIN_TONES = [
    ("1", "#f6d3b3"), ("2", "#eebd93"), ("3", "#d29b6c"),
    ("4", "#b5774a"), ("5", "#8d5532"), ("6", "#5e3a22"),
]
HAIR_COLOURS = [
    ("black", "#1f1b1a"), ("brown", "#5a3825"), ("auburn", "#8e3b1f"), ("blonde", "#e0b45c"),
    ("grey", "#a8a39b"), ("coral", "#ff6a3d"), ("teal", "#3cb4a8"), ("lavender", "#b9a6ff"),
]
EXTRAS = [("none", "None"), ("glasses", "Glasses"), ("beard", "Beard"), ("both", "Glasses and beard")]

# Choices for model/form fields: (value, label).
HAIR_STYLE_CHOICES = HAIR_STYLES
SKIN_TONE_CHOICES = [(k, f"Tone {k}") for k, _ in SKIN_TONES]
HAIR_COLOUR_CHOICES = [(k, k.title()) for k, _ in HAIR_COLOURS]
EXTRA_CHOICES = EXTRAS

_SKIN = dict(SKIN_TONES)
_HAIR = dict(HAIR_COLOURS)

# S skin, E eye, M mouth, C shirt. "." is empty.
FACE = [
    "................",
    "................",
    "................",
    ".....SSSSSS.....",
    "....SSSSSSSS....",
    "....SSSSSSSS....",
    "...SSSSSSSSSS...",
    "...SSESSSSESS...",
    "....SSSSSSSS....",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "......SSSS......",
    "......SSSS......",
    "...CCCCCCCCCC...",
    "..CCCCCCCCCCCC..",
    "..CCCCCCCCCCCC..",
]

# Hair layers: (behind the face, in front of the face). H = hair.
HAIR = {
    "short": ([], [
        (2, ".....HHHHHH....."),
        (3, "....HHHHHHHH...."),
        (4, "...HHHHHHHHHH..."),
        (5, "...HH......HH..."),
        (6, "...H........H..."),
    ]),
    "long": ([(r, "...HHHHHHHHHH...") for r in range(4, 12)] + [(12, "...HHH....HHH...")], [
        (2, ".....HHHHHH....."),
        (3, "....HHHHHHHH...."),
        (4, "...HHHHHHHHHH..."),
        (5, "...HHHH..HHHH..."),
        (6, "...HH......HH..."),
        (7, "...HH......HH..."),
        (8, "...H........H..."),
        (9, "...H........H..."),
        (10, "...H........H..."),
        (11, "...HH......HH..."),
        (12, "...HH......HH..."),
        (13, "...HH......HH..."),
        (14, "...HH......HH..."),
    ]),
    "bun": ([], [
        (0, "......HHHH......"),
        (1, "......HHHH......"),
        (2, ".....HHHHHH....."),
        (3, "....HHHHHHHH...."),
        (4, "...HHHHHHHHHH..."),
        (5, "...HH......HH..."),
        (6, "...H........H..."),
    ]),
    "curly": ([(r, "..HHHHHHHHHHHH..") for r in range(3, 10)] + [(10, "...HHHHHHHHHH...")], [
        (1, "....HHHHHHHH...."),
        (2, "...HHHHHHHHHH..."),
        (3, "..HHHHHHHHHHHH.."),
        (4, "..HHHHHHHHHHHH.."),
        (5, "..HHH.H..H.HHH.."),
    ]),
    "spiky": ([], [
        (1, "....H.H..H.H...."),
        (2, "....HHHHHHHH...."),
        (3, "...HHHHHHHHHH..."),
        (4, "...HHHHHHHHHH..."),
        (5, "...H........H..."),
    ]),
    "buzz": ([], [
        (3, ".....HHHHHH....."),
        (4, "....HHHHHHHH...."),
    ]),
    "headscarf": ([], [
        (1, ".....HHHHHH....."),
        (2, "....HHHHHHHH...."),
        (3, "...HHHHHHHHHH..."),
        (4, "...HHHHHHHHHH..."),
        (5, "...HH......HH..."),
        (6, "...HH......HH..."),
        (7, "...HH......HH..."),
        (8, "...HH......HH..."),
        (9, "...HHH....HHH..."),
        (10, "...HHHH..HHHH..."),
        (11, "...HHHHHHHHHH..."),
        (12, "..HHHHHHHHHHHH.."),
        (13, "..HHHHHHHHHHHH.."),
    ]),
    "bald": ([], []),
}

# Silver frames round each eye (rows 6-8), so the dark eyes still show through.
GLASSES = [(6, "....GGG..GGG...."), (7, "....G.GGGG.G...."), (8, "....GGG..GGG....")]
BEARD = [(9, "....BB....BB...."), (10, ".....BBBBBB....."), (11, "......BBBB......")]


def _darken(hex_colour, factor=0.78):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(int(r * factor), int(g * factor), int(b * factor))


def options_for(profile):
    """The avatar options to draw: the member's own choices, falling back to a hash of their username."""
    digest = md5(profile.user.username.encode()).digest()
    return {
        "hair": profile.pixel_hair or HAIR_STYLES[digest[0] % 6][0],  # hashes pick from the first six
        "skin": profile.pixel_skin or SKIN_TONES[digest[1] % len(SKIN_TONES)][0],
        "hair_colour": profile.pixel_hair_colour or HAIR_COLOURS[digest[2] % 5][0],
        "extra": profile.pixel_extra or ("glasses" if digest[3] % 4 == 0 else "none"),
    }


@lru_cache(maxsize=512)
def render_svg(hair, skin, hair_colour, extra, shirt, size, crop=False):
    """Return the avatar as an SVG string. Unknown values fall back to safe defaults."""
    hair = hair if hair in HAIR else "short"
    skin_hex = _SKIN.get(skin, SKIN_TONES[2][1])
    hair_hex = _HAIR.get(hair_colour, HAIR_COLOURS[0][1])
    shirt = shirt if isinstance(shirt, str) and shirt.startswith("#") and len(shirt) == 7 else "#8a8a8a"
    palette = {"S": skin_hex, "M": _darken(skin_hex), "E": "#1a1a1a", "C": shirt,
               "H": hair_hex, "G": "#b8bcc2", "B": hair_hex}

    grid = [["."] * 16 for _ in range(16)]

    def paint(rows):
        for r, line in rows:
            for c, ch in enumerate(line):
                if ch != ".":
                    grid[r][c] = ch

    back, front = HAIR[hair]
    paint(back)
    paint(list(enumerate(FACE)))
    paint(front)
    if extra in ("beard", "both"):
        paint(BEARD)
    if extra in ("glasses", "both"):
        paint(GLASSES)

    # Merge horizontal runs of one colour into a single <rect> to keep the markup small.
    rects = []
    for y, row in enumerate(grid):
        x = 0
        while x < 16:
            ch = row[x]
            if ch == ".":
                x += 1
                continue
            start = x
            while x < 16 and row[x] == ch:
                x += 1
            rects.append(f'<rect x="{start}" y="{y}" width="{x - start}" height="1" fill="{palette[ch]}"/>')

    box = "2 1 12 12" if crop else "0 0 16 16"
    return (f'<svg class="px-avatar" viewBox="{box}" width="{size}" height="{size}" '
            f'shape-rendering="crispEdges" aria-hidden="true" focusable="false">{"".join(rects)}</svg>')
