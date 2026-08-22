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
band behind the text → a quiet area of the picture → an outline. The band is
built here (grey 200, the level Phase 1 measured as usable, with 170 as the
lower bound); the other two are left to whoever picks the picture, because no
code can tell a quiet sky from a busy hedge.

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

# --- the band -----------------------------------------------------------------
# Grey 200 [Festlegung, Phase 1: 200 is usable, 170 is the lower bound]. It is a
# flat area, not a hairline, so the dither raster does it no harm — the measured
# failure of grey was a 2 px rule breaking up into dots, which is a different
# problem from a 300 px band.
BAND_GREY = 200
BAND_PAD_Y = 72
BLOCK_GAP = 48  # between the name and the greeting line


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
    band: bool
    band_top: int
    band_height: int
    background_url: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.as_dict(),
            "greeting": self.greeting.as_dict(),
            "font_family": self.font_family,
            "font_weight": self.font_weight,
            "font_url": self.font_url,
            "band": self.band,
            "band_top": self.band_top,
            "band_height": self.band_height,
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


def plan(config: dict[str, Any], background_url: str | None = None) -> GuestPlan:
    """Turn the ``guests`` section of the render document into a finished layout.

    Reads defensively — every field may be missing or ``None``, because the
    section exists from the first start while nobody has typed anything into it
    yet, and an empty guest page is a legitimate thing to render.
    """
    cfg = config or {}
    font_id = str(cfg.get("font") or DEFAULT_FONT)
    if font_id not in FONTS:
        font_id = DEFAULT_FONT
    entry = font_entry(font_id)

    name = fit(
        str(cfg.get("name") or ""),
        font_id,
        int(cfg.get("name_px") or DEFAULT_NAME_PX),
        NAME_MAX_LINES,
        NAME_FLOOR_PX,
    )
    greeting = fit(
        str(cfg.get("greeting") or ""),
        font_id,
        int(cfg.get("greeting_px") or DEFAULT_GREETING_PX),
        GREETING_MAX_LINES,
        GREETING_FLOOR_PX,
    )

    text_height = name.height + greeting.height
    if name.lines and greeting.lines:
        text_height += BLOCK_GAP

    # The band is only worth its grey on top of a picture. On the flat white of
    # a missing background it would be a grey stripe for nothing — and grey on
    # white is the one combination that *does* carry a visible dither raster,
    # right behind the text it is supposed to help.
    band = bool(cfg.get("band", True)) and bool(background_url) and bool(text_height)
    band_height = text_height + 2 * BAND_PAD_Y
    band_top = max(0, (CANVAS_H - band_height) // 2)

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
        band=band,
        band_top=band_top,
        band_height=band_height,
        background_url=background_url,
    )
