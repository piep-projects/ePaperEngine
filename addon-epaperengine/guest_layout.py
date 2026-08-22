"""How the guest greeting is set on the wall (FSD §8.4, Mockup 11-wand-gaeste).

The policy, not the drawing — the same bargain ``recipe_layout.py`` and
``outage.py`` make: a module of plain data and pure functions, so the part worth
testing needs no Chromium, no panel and no wait.

**What the specification fixes** [Festlegung C13]: name and greeting line come
from Home Assistant, they are set in **large script type on a background
picture**, and the picture is chosen in the panel.

**What it warns about, and what this module does with it.** FSD §8.4 says the
danger is not the stroke width — at 180 px even a script's thin connecting
strokes are far above the 2 px floor of FSD §7 — but the **contrast against the
dither raster of the photo**, and it names the remedies in order: a lightened
band behind the text → a quiet area of the picture → an outline.

**The band is gone** [Festlegung P23, 2026-08-22]: the greeting sits directly on
the picture, with no ground of its own. What takes its place is the **colour**,
which is now chosen rather than assumed — white script over a dark photo is the
same remedy the band was, without covering a third of the picture with a stripe.
The colour is picked from the six Spectra primaries and from nothing else: any
other value would be dithered into a raster, and a rastered glyph edge is
exactly the thing FSD §8.4 warns about. The other two remedies stay with whoever
picks the picture, because no code can tell a quiet sky from a busy hedge.

**The text can be set at an angle** [Festlegung P23]. That is not free: a block
rotated by θ needs ``w·|cos θ| + h·|sin θ|`` of horizontal room, so a name that
fits lying flat can hang over the edge at 20°. The fit is therefore measured
against the **rotated bounding box**, not against the line width — see ``plan``.

**The outline is the third remedy** [Festlegung P24], and the only one that makes
the greeting independent of the picture underneath it: a seam in the counter
colour separates the glyph from whatever it happens to sit on, rather than
relying on the whole letter out-contrasting it. Switchable, because a calm motif
does not need it and a seam always costs a little of the script's elegance. Its
colour comes from the same six primaries for the same reason the fill does, and
its width is a **visible** width — see ``stroke_px`` for why that is not the
number the CSS gets.

**The type size is measured, not guessed.** ``recipe_layout`` had to estimate
character widths because DejaVu was a system font it could not open; here the
font files ship with the add-on, so Pillow opens the very file Chromium will
render and asks it how wide the name is. That is why a 69-character family name
shrinks by exactly as much as it needs to and no more.

**Both surfaces get the same line breaks.** The lines are computed here and
handed to the template one by one; CSS never wraps anything. Letting the browser
re-wrap what Python had already budgeted for is precisely how the first recipe
image ran off the bottom of the canvas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import ImageFont

# --- the canvas, 1:1 with the panel -------------------------------------------
CANVAS_W = 2560
CANVAS_H = 1440

# The margin the error page uses, and for the same reason: FSD §7 measured its
# type sizes against it. Script faces swing further left and right than an
# upright sans, so the text is fitted into a little less than what is left.
MARGIN = 160
TEXT_W = CANVAS_W - 2 * MARGIN  # 2240
# The vertical budget. It only started to matter with the angle: a block set at
# 30° is taller than it is deep, and until now nothing measured the height at
# all — the band was simply centred and would have run off the canvas without
# anybody noticing.
TEXT_H = CANVAS_H - 2 * MARGIN  # 1120
SAFETY = 0.98  # a hair of room for the swash of a capital

# --- the faces ----------------------------------------------------------------
# Shipped with the add-on rather than installed from Alpine: no Alpine package
# carries a script face, and a font downloaded at build time would make the build
# depend on somebody else's server. All three are SIL Open Font License; the
# licence files sit next to them.
#
# The token on the left is what the store holds — English, like every other
# technical identifier (FSD §3.0a). The family name in the middle is what
# fontconfig knows the file as, i.e. what the CSS asks for.
#
# The weight matters more here than anywhere else in this project: a dithered
# photo behind a hairline is the failure mode FSD §8.4 warns about, so the two
# variable faces are set at **700** rather than at their regular weight. Great
# Vibes has only one weight — it is the formal one, and the one to check first
# if the wall shows a broken-up outline.
FONT_DIR = Path(__file__).parent / "fonts"

FONTS: dict[str, dict[str, Any]] = {
    "dancing_script": {"family": "Dancing Script", "file": "DancingScript-Variable.ttf", "weight": 700},
    "caveat": {"family": "Caveat", "file": "Caveat-Variable.ttf", "weight": 700},
    "great_vibes": {"family": "Great Vibes", "file": "GreatVibes-Regular.ttf", "weight": 400},
}
DEFAULT_FONT = "dancing_script"

# --- the type sizes -----------------------------------------------------------
# From the mockup: 180 px for the name, 72 px for the greeting line. Both are
# *wishes*, not commitments — a long name shrinks until it fits (see ``fit``).
DEFAULT_NAME_PX = 180
DEFAULT_GREETING_PX = 72

# How far a wish may be cut back. 72 px is still more than twice the 32 px floor
# FSD §7 sets for readable text at a metre, so a name that has shrunk this far is
# small for a greeting but never illegible.
NAME_FLOOR_PX = 72
GREETING_FLOOR_PX = 40
SHRINK_PX = 4

# Two lines for a name (``Familie Berger-Wiedemann`` breaks after the article),
# three for a greeting sentence.
NAME_MAX_LINES = 2
GREETING_MAX_LINES = 3

# Script faces carry tall ascenders and deep descenders; 1.3 keeps the loop of a
# lowercase g clear of the capital below it.
LINE_HEIGHT = 1.3

BLOCK_GAP = 48  # between the name and the greeting line

# --- the colour ---------------------------------------------------------------
# **The six Spectra primaries and nothing else** [Festlegung P23]. This is not a
# restriction of the picker, it is what the panel can actually show: a colour off
# the palette is reproduced by *dithering* it out of the six, and on a glyph edge
# that comes out as a speckled outline rather than a tint. The same lesson cost a
# hairline in phase 5.3 — a 2 px grey rule dithered into a dotted trail — and it
# is why the recipe headings are palette blue and palette green.
#
# ``tests/test_guest_layout.py`` checks every value against ``imaging.SPECTRA``,
# so a colour that is not a primary cannot be added by accident.
COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (220, 30, 30),
    "yellow": (240, 200, 30),
    "blue": (30, 60, 180),
    "green": (30, 140, 70),
}
DEFAULT_COLOR = "black"

# --- the outline --------------------------------------------------------------
# **What is configured is the width that can be *seen*.** ``-webkit-text-stroke``
# centres its stroke on the glyph outline, and the template draws it with
# ``paint-order: stroke fill`` so the fill covers the inner half — which is what
# keeps a script face from being thinned by its own seam. The visible part is
# therefore half of what CSS is told, and the factor lives here rather than in
# somebody's head [Festlegung P24].
OUTLINE_CSS_FACTOR = 2

# FSD §7's floor is 2 px, and a seam is exactly the kind of thin feature that
# breaks up into dots below it. The ceiling is where the counter colour starts
# eating the letter it is supposed to frame.
OUTLINE_MIN_PX = 2
OUTLINE_MAX_PX = 32
DEFAULT_OUTLINE_PX = 8
DEFAULT_OUTLINE_COLOR = "white"

# --- the angle ----------------------------------------------------------------
# Degrees, positive is clockwise (the CSS sense). Bounded rather than free: past
# 45° the block is more vertical than horizontal on a 16:9 canvas, and every
# extra degree costs type size for nothing — the fit below would simply shrink
# the name until it fitted the diagonal.
ANGLE_LIMIT = 45.0

# Fitting a **tilted** block takes two knobs, not one, and neither alone is
# enough. Both were tried:
#
# * **Only the width budget.** Narrowing the room a line may use wraps it into
#   more lines, and more lines make the block *taller* — the wrong direction
#   whenever the height is what binds. Measured: 16 px of seam at 25° came out
#   1.706 px tall against a budget of 1.120, and the loop only stopped because
#   the fonts had hit their floors.
# * **Only the type size.** ``fit`` prefers *fewer lines at a larger size*, which
#   is right for a level block and wrong for a tilted one: at 40° it is the line
#   *width* that drives the height. Measured: a 52-character name came out as one
#   1.563 px line at the 72 px floor — 1.153 px tall, over budget — while the
#   same name on **two** lines at 100 px would have been 1.004 px tall and
#   larger to read.
#
# So both are searched: an outer walk over the width budget, an inner walk over
# the type size, and of everything that fits the canvas the **largest type**
# wins. A few hundred fits at worst, each of them a handful of measurements
# against an already-open font — microseconds against a 5-second render.
ROOM_FACTORS: tuple[float, ...] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)
SHRINK_STEP = 0.94
SHRINK_PASSES = 30


@dataclass(frozen=True)
class TextBlock:
    """One piece of text, already broken into the lines the wall will show."""

    lines: tuple[str, ...]
    font_px: int
    requested_px: int

    @property
    def shrunk(self) -> bool:
        """Did the wish have to give way? Reported, so the panel can say so."""
        return self.font_px < self.requested_px

    @property
    def height(self) -> int:
        return round(len(self.lines) * self.font_px * LINE_HEIGHT)

    def as_dict(self) -> dict[str, Any]:
        return {
            "lines": list(self.lines),
            "font_px": self.font_px,
            "requested_px": self.requested_px,
            "shrunk": self.shrunk,
        }


@dataclass(frozen=True)
class GuestPlan:
    """Everything ``guests.html.j2`` needs, decided before the browser starts."""

    name: TextBlock
    greeting: TextBlock
    font_family: str
    font_weight: int
    font_url: str
    color: tuple[int, int, int]
    angle: float
    outline: bool
    outline_px: int
    outline_color: tuple[int, int, int]
    # The block as it ends up on the canvas: the width of its widest line, its
    # stacked height, and the axis-aligned box those two occupy once rotated.
    # Reported rather than kept private because it is the thing the fit was
    # working towards, and a run that came out cramped should say so in its log.
    width: int
    height: int
    box_w: int
    box_h: int
    background_url: str | None

    @property
    def cramped(self) -> bool:
        """Did the block end up larger than the canvas allows?

        Only reachable at the very bottom of the shrinking loop — both type
        sizes at their floor and the box still over budget, which takes a long
        name, a steep tilt and a thick seam together. Reported rather than
        silently clipped: ``overflow: hidden`` would swallow it, and text
        quietly missing from a wall is the failure this project has already paid
        for once.
        """
        return self.box_w > TEXT_W or self.box_h > TEXT_H

    @property
    def stroke_px(self) -> int:
        """The ``-webkit-text-stroke`` width for the visible seam asked for."""
        return self.outline_px * OUTLINE_CSS_FACTOR if self.outline else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.as_dict(),
            "greeting": self.greeting.as_dict(),
            "font_family": self.font_family,
            "font_weight": self.font_weight,
            "font_url": self.font_url,
            # Handed over as CSS, not as three numbers: the template has no
            # business assembling a colour, and a stray value could not become
            # markup here even if it tried.
            "color": "rgb(%d, %d, %d)" % self.color,
            "angle": self.angle,
            "outline": self.outline,
            "outline_px": self.outline_px,
            "outline_color": "rgb(%d, %d, %d)" % self.outline_color,
            # What the stylesheet is actually given — twice the visible width,
            # because half of the centred stroke disappears under the fill.
            "stroke_px": self.stroke_px,
            "width": self.width,
            "height": self.height,
            "box_w": self.box_w,
            "box_h": self.box_h,
            "cramped": self.cramped,
            "background_url": self.background_url,
        }


def font_path(font_id: str) -> Path:
    """The file for a font token, falling back to the default face.

    A token nobody knows resolves rather than raising: a typo in the store must
    not be the reason the wall goes dark, and the panel offers a closed list
    anyway.
    """
    entry = FONTS.get(font_id) or FONTS[DEFAULT_FONT]
    return FONT_DIR / str(entry["file"])


def font_entry(font_id: str) -> dict[str, Any]:
    return FONTS.get(font_id) or FONTS[DEFAULT_FONT]


_faces: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _face(font_id: str, px: int) -> ImageFont.FreeTypeFont:
    """Open the very file Chromium will render, at the size it will render it.

    Memoised: fitting a name walks a couple of dozen sizes, and FreeType opening
    a 400 KB variable font each time would be the slowest thing on this page.

    The variable faces are pinned to their **Bold** instance, matching the
    ``font-weight`` the template asks for. If FreeType cannot set the axis, the
    measurement falls back to the regular weight — narrower than what is drawn
    would be the dangerous direction, so this is the safe one: a bold face
    measured as regular would overflow, a regular face measured as bold only
    shrinks a little more than it had to.
    """
    key = (font_id, px)
    if key not in _faces:
        entry = font_entry(font_id)
        face = ImageFont.truetype(str(font_path(font_id)), px)
        if int(entry["weight"]) >= 700:
            try:
                face.set_variation_by_name("Bold")
            except (OSError, ValueError, AttributeError):
                pass
        _faces[key] = face
    return _faces[key]


def width_of(text: str, font_id: str, px: int) -> float:
    """Advance width of ``text`` in pixels, from the font file itself."""
    return float(_face(font_id, px).getlength(text))


def wrap(text: str, font_id: str, px: int, width: int = TEXT_W) -> tuple[str, ...]:
    """Greedy word wrap on measured widths.

    A single word wider than the line is left whole rather than broken: a name
    is not a place to hyphenate, and the shrinking step above will take care of
    it in the next iteration.
    """
    limit = width * SAFETY
    words = str(text or "").split()
    if not words:
        return ()
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if width_of(candidate, font_id, px) <= limit:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def fit(
    text: str,
    font_id: str,
    requested_px: int,
    max_lines: int,
    floor_px: int,
    width: int = TEXT_W,
) -> TextBlock:
    """The largest size at or below the wish that fits in ``max_lines``.

    Nothing fitting even at the floor is not an error: the block keeps the floor
    size and takes the lines it needs. A greeting nobody will ever type — three
    sentences in one field — then sets small and tall instead of overflowing the
    canvas silently, and the band grows with it because the band is measured off
    this result rather than assumed.
    """
    requested_px = max(int(requested_px or 0), floor_px)
    if not str(text or "").strip():
        return TextBlock(lines=(), font_px=requested_px, requested_px=requested_px)

    px = requested_px
    while px >= floor_px:
        lines = wrap(text, font_id, px, width)
        if len(lines) <= max_lines:
            return TextBlock(lines=lines, font_px=px, requested_px=requested_px)
        px -= SHRINK_PX
    return TextBlock(
        lines=wrap(text, font_id, floor_px, width),
        font_px=floor_px,
        requested_px=requested_px,
    )


def block_size(
    name: TextBlock, greeting: TextBlock, font_id: str, outline_px: int = 0
) -> tuple[int, int]:
    """The unrotated box the two blocks occupy: widest line × stacked height.

    ``outline_px`` grows the box on every side. The seam sits *outside* the glyph
    (``paint-order: stroke fill``), so it adds to the extremes of the line
    without touching the advance between letters — the same kind of coupling the
    angle has, and the same reason it is accounted for here instead of being
    left for the browser to discover at the edge of the canvas.
    """
    width = 0.0
    for block in (name, greeting):
        for line in block.lines:
            width = max(width, width_of(line, font_id, block.font_px))
    height = name.height + greeting.height
    if name.lines and greeting.lines:
        height += BLOCK_GAP
    if width or height:
        width += 2 * outline_px
        height += 2 * outline_px
    return round(width), height


def rotated_box(width: int, height: int, angle: float) -> tuple[int, int]:
    """The axis-aligned box a ``width × height`` block fills once rotated.

    Plain trigonometry, and the reason the angle is not free of charge: at 30° a
    2.000 px line already claims 1.732 px of width *plus* half its own height
    again. A layout that ignored this would let a name that fits lying flat hang
    over the edge of the panel the moment somebody tilted it.
    """
    radians = math.radians(abs(angle))
    cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
    return round(width * cos + height * sin), round(width * sin + height * cos)


def plan(config: dict[str, Any], background_url: str | None = None) -> GuestPlan:
    """Turn the ``guests`` section of the render document into a finished layout.

    Reads defensively — every field may be missing or ``None``, because the
    section exists from the first start while nobody has typed anything into it
    yet, and an empty guest page is a legitimate thing to render.

    **The fit is against the rotated box, not the line width** [Festlegung P23].
    Width and height are coupled through the tilt — ``w·|cos θ| + h·|sin θ|`` —
    and through the seam, so it is walked rather than solved: set the text,
    measure the rotated bounding box, and if it hangs over the canvas take 6 %
    off the **type size** and set it again.

    The type size and not the width budget, and that distinction is the whole
    lesson of this loop: a narrower budget wraps more lines and makes the block
    *taller*, which is the wrong direction whenever the height is what binds.
    See ``SHRINK_STEP``.
    """
    cfg = config or {}
    font_id = str(cfg.get("font") or DEFAULT_FONT)
    if font_id not in FONTS:
        font_id = DEFAULT_FONT
    entry = font_entry(font_id)

    color_id = str(cfg.get("color") or DEFAULT_COLOR)
    color = COLORS.get(color_id) or COLORS[DEFAULT_COLOR]

    outline = bool(cfg.get("outline"))
    outline_color_id = str(cfg.get("outline_color") or DEFAULT_OUTLINE_COLOR)
    outline_color = COLORS.get(outline_color_id) or COLORS[DEFAULT_OUTLINE_COLOR]
    try:
        outline_px = int(cfg.get("outline_px") or DEFAULT_OUTLINE_PX)
    except (TypeError, ValueError):
        outline_px = DEFAULT_OUTLINE_PX
    outline_px = max(OUTLINE_MIN_PX, min(OUTLINE_MAX_PX, outline_px))
    pad = outline_px if outline else 0

    try:
        angle = float(cfg.get("angle") or 0.0)
    except (TypeError, ValueError):
        angle = 0.0
    angle = max(-ANGLE_LIMIT, min(ANGLE_LIMIT, angle))

    name_px = int(cfg.get("name_px") or DEFAULT_NAME_PX)
    greeting_px = int(cfg.get("greeting_px") or DEFAULT_GREETING_PX)

    # The room the lines themselves may use: the canvas less the seam, which is
    # drawn outside them.
    full_room = max(1, TEXT_W - 2 * pad)

    def attempt(room: int, scale: float) -> tuple[TextBlock, TextBlock, int, int, int, int]:
        """One candidate layout: set both blocks, measure the rotated box."""
        name = fit(
            str(cfg.get("name") or ""),
            font_id,
            max(NAME_FLOOR_PX, round(name_px * scale)),
            NAME_MAX_LINES,
            NAME_FLOOR_PX,
            room,
        )
        greeting = fit(
            str(cfg.get("greeting") or ""),
            font_id,
            max(GREETING_FLOOR_PX, round(greeting_px * scale)),
            GREETING_MAX_LINES,
            GREETING_FLOOR_PX,
            room,
        )
        width, height = block_size(name, greeting, font_id, pad)
        box_w, box_h = rotated_box(width, height, angle)
        return name, greeting, width, height, box_w, box_h

    best: tuple[TextBlock, TextBlock, int, int, int, int] | None = None
    fallback = attempt(full_room, 1.0)
    for factor in ROOM_FACTORS:
        room = max(1, round(full_room * factor))
        scale = 1.0
        for _pass in range(SHRINK_PASSES):
            candidate = attempt(room, scale)
            fallback = candidate
            if candidate[4] <= TEXT_W and candidate[5] <= TEXT_H:
                # Of everything that fits, the largest type wins — the greeting
                # is meant to be read from across the room.
                if best is None or (candidate[0].font_px, candidate[1].font_px) > (
                    best[0].font_px,
                    best[1].font_px,
                ):
                    best = candidate
                break
            if candidate[0].font_px <= NAME_FLOOR_PX and candidate[1].font_px <= GREETING_FLOOR_PX:
                # As small as the rules allow. Going further would mean cutting
                # the greeting, and a greeting is never cut (P21).
                break
            scale *= SHRINK_STEP

    # Nothing fitted at any width: keep the last attempt and let ``cramped`` say
    # so, rather than quietly handing the browser something to clip.
    name, greeting, width, height, box_w, box_h = best or fallback

    return GuestPlan(
        name=name,
        greeting=greeting,
        font_family=str(entry["family"]),
        font_weight=int(entry["weight"]),
        # The template declares the face with an ``@font-face`` on this URL as
        # well as naming the family. Belt and braces on purpose: the Dockerfile
        # installs the files into the system font path and runs ``fc-cache``, so
        # naming the family *should* be enough — but a font that silently failed
        # to register would fall back to DejaVu, and "the greeting is not in
        # script" is a defect nobody sees until they walk past the wall.
        font_url=font_path(font_id).as_uri(),
        color=color,
        angle=angle,
        outline=outline,
        outline_px=outline_px,
        outline_color=outline_color,
        width=width,
        height=height,
        box_w=box_w,
        box_h=box_h,
        background_url=background_url,
    )
