"""How a recipe is fitted into its column (FSD §7, §8.2, Mockup 09-wand-rezepte).

The policy, not the drawing — like ``outage.py`` and the integration's
``resolve.py``: a pure function over plain data, so the part that is worth
testing can be tested without Chromium, a panel or a wait.

**What the specification fixes** [Festlegung 2026-08-20]: three columns of
773 px, landscape only; type shrinks **28 → 26 → 24 px, per column separately**,
so one long recipe does not shrink the short ones next to it; **24 px is the
floor** (colour carries down to 24 px and no further, FSD §7); below that the
text is **shortened and the shortening is made visible**.

**The model counts lines, not characters** [Korrektur 2026-08-22, am ersten
echten Bild gemessen]. FSD §7 budgets a column in characters — ~950 at 28 px,
~1.350 at 24 px — and marks the numbers as *[Vorschlag, am Panel zu prüfen]*.
They do not survive contact with a real recipe: a character budget assumes full
lines, and an ingredient list is the opposite of that. Nineteen ingredients of
fifteen characters are 285 characters by the old model — about five lines —
and nineteen lines on the wall. The first rendered recipe ran off the bottom of
the canvas and was silently clipped, because the budget said it fit.

So the column is measured the way it is actually set:

* the title wraps at 40 px and the head grows with it (a 69-character recipe
  name is three lines, and that is 240 px of the 1.280 px column before a word
  of the recipe);
* every **source line** of the ingredients costs at least one line, however
  short it is;
* the directions wrap as prose.

**Two-column ingredients** [Vorschlag 2026-08-22, auf Anregung]: a list of
short items wastes two thirds of the column width. When the items still fit at
half width, they are set in two columns and the block costs half the lines.
Decided here rather than in CSS so the height model and the drawing cannot
disagree — CSS balancing what Python did not account for is exactly how the
clipping happened.

**What gives way when it still does not fit** [Festlegung P13]: the ingredients
win, the directions are cut, the title never is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# --- the canvas, 1:1 with the mockup ------------------------------------------
CANVAS_H = 1440
MARGIN = 80
COLUMN_W = 773
COLUMN_H = CANVAS_H - 2 * MARGIN  # 1280

# Character width of DejaVu Sans as a fraction of the type size. Derived from
# FSD §7's own table — 52 characters per 773 px at 28 px — and it reproduces the
# other rows: 45 at 32 px, 40 at 36 px, ~61 at 24 px (the figure the mockup
# generator uses).
CHAR_RATIO = 0.531

TITLE_PX = 40
TITLE_LINE = 56  # advance per wrapped title line (mockup: title at M, meta at M+56)
META_LINE = 48   # meta line plus the gap to the rule
RULE_GAP = 24    # rule under the head, plus the gap to the first heading

HEADING_PX = 32
HEADING_BLOCK = 52  # heading line plus the gap under it (mockup: y += 52)
GROUP_GAP = 20      # between the end of a block and the next heading
CUT_BLOCK = 46      # the "shortened" marker: 26 px on a 20 px top margin

# One line of slack, and it is not superstition: this model averages the width
# of a DejaVu glyph, and a line of capitals or a hyphenated compound can break
# one word earlier than predicted. The column clips silently, so the cost of
# being one line short is invisible and the cost of being one line over is the
# bug this whole model exists to fix.
SAFETY_LINES = 1

# (type size, line advance) — the mockup sets 40 px at 28 and 34 px at 24.
STEPS: tuple[tuple[int, int], ...] = ((28, 40), (26, 37), (24, 34))
FLOOR_PX, FLOOR_LINE = STEPS[-1]

# Two-column ingredients only pay off from this many items, and only when
# half-width wrapping does not itself cost more lines than it saves.
TWO_COLUMN_MIN_ITEMS = 6
TWO_COLUMN_WRAP_TOLERANCE = 1.15

ELLIPSIS = "…"


@dataclass
class Column:
    """One recipe, measured and ready for the template."""

    name: str
    meta: str
    ingredients: list[str] = field(default_factory=list)  # source lines, "" = a gap
    directions: str = ""
    font_px: int = FLOOR_PX
    line_px: int = FLOOR_LINE
    ingredient_columns: int = 1
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "meta": self.meta,
            "ingredients": self.ingredients,
            "directions": self.directions,
            "font_px": self.font_px,
            "line_px": self.line_px,
            "ingredient_columns": self.ingredient_columns,
            "truncated": self.truncated,
        }


# --- measuring ----------------------------------------------------------------
def chars_per_line(font_px: int, width: int = COLUMN_W) -> int:
    """How many characters of DejaVu Sans fit across ``width`` at ``font_px``.

    Rounded, not truncated: that is what reproduces all four rows of the FSD §7
    table (52 at 28 px, 45 at 32, 40 at 36, 61 at 24). The slack lives in
    ``SAFETY_LINES``, where it is visible, rather than hidden in this constant.
    """
    return max(round(width / (CHAR_RATIO * font_px)), 1)


def wrap(text: str, limit: int) -> list[str]:
    """Greedy word wrap — the model of what the browser will do.

    Source line breaks are kept: ``ingredients`` and ``directions`` are
    multi-line free text at Paprika [belegt], and the line breaks in them are
    the only structure they have.
    """
    lines: list[str] = []
    for source in text.split("\n"):
        words = source.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= limit:
                current += " " + word
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def head_lines(name: str, has_meta: bool) -> int:
    """Height of title + meta + rule, in pixels."""
    title = max(len(wrap(name, chars_per_line(TITLE_PX))), 1)
    return title * TITLE_LINE + (META_LINE if has_meta else 0) + RULE_GAP


def body_lines(name: str, has_meta: bool, line_px: int, reserve: int = 0) -> int:
    """How many body lines are left once head, both headings and the gap are off.

    ``reserve`` is extra pixels the caller knows it will need — the "shortened"
    marker, which only exists on a column that had to be cut.
    """
    room = COLUMN_H - head_lines(name, has_meta) - 2 * HEADING_BLOCK - GROUP_GAP - reserve
    return max(room // line_px - SAFETY_LINES, 0)


def ingredient_layout(items: list[str], font_px: int) -> tuple[int, int]:
    """``(lines the block costs, number of sub-columns)``.

    Two columns when the items are short enough to survive half the width —
    that is the difference between nineteen lines and ten for a real
    ingredient list, and it is where the room for the directions comes from.
    """
    if not items:
        return 0, 1
    full = len(wrap("\n".join(items), chars_per_line(font_px)))
    if len(items) < TWO_COLUMN_MIN_ITEMS:
        return full, 1
    half = len(wrap("\n".join(items), chars_per_line(font_px, COLUMN_W // 2)))
    if half > full * TWO_COLUMN_WRAP_TOLERANCE:
        # The items are long enough that halving the width only re-wraps them.
        return full, 1
    return math.ceil(half / 2), 2


def cut_to_lines(text: str, limit: int, budget: int) -> tuple[str, bool]:
    """Keep whole source lines until ``budget`` lines are used up.

    Cutting on source lines rather than on a character count keeps the
    paragraphs intact — a recipe that stops after a whole step reads as
    shortened, one that stops mid-sentence reads as broken. The last line is
    cut at a word boundary when a part of it still fits.
    """
    if budget <= 0:
        return "", bool(text.strip())
    kept: list[str] = []
    used = 0
    for source in text.split("\n"):
        cost = len(wrap(source, limit))
        if used + cost <= budget:
            kept.append(source)
            used += cost
            continue
        # Part of this line may still fit.
        room = budget - used
        if room > 0:
            partial = wrap(source, limit)[:room]
            if partial and partial[-1]:
                partial[-1] = partial[-1].rstrip() + ELLIPSIS
                kept.append(" ".join(partial))
        return "\n".join(kept).rstrip(), True
    return "\n".join(kept).rstrip(), False


# --- building the column ------------------------------------------------------
def build_column(recipe: dict[str, Any]) -> Column:
    """Turn one recipe from the render document into a fitted column."""
    name = str(recipe.get("name") or "").strip()
    ingredients_text = str(recipe.get("ingredients") or "").strip()
    directions_text = str(recipe.get("directions") or "").strip()
    meta = " · ".join(
        part
        for part in (
            str(recipe.get("servings") or "").strip(),
            str(recipe.get("total_time") or "").strip(),
        )
        if part
    )
    items = [line.rstrip() for line in ingredients_text.split("\n")] if ingredients_text else []

    for font_px, line_px in STEPS:
        limit = chars_per_line(font_px)
        available = body_lines(name, bool(meta), line_px)
        cost, columns = ingredient_layout(items, font_px)
        needed = cost + len(wrap(directions_text, limit))
        if needed <= available:
            return Column(
                name, meta, items, directions_text, font_px, line_px, columns, False
            )

    # The floor, and it still does not fit: shorten (FSD §8.2, Festlegung P13).
    limit = chars_per_line(FLOOR_PX)
    # A shortened column carries the marker that says so, and it needs room.
    available = body_lines(name, bool(meta), FLOOR_LINE, reserve=CUT_BLOCK)
    cost, columns = ingredient_layout(items, FLOOR_PX)
    # The ingredients are protected, but not without limit: a column that is
    # nothing but an ingredient list shows no directions at all, which reads as
    # broken rather than as shortened.
    ingredient_budget = max(int(available * 0.6), 1)
    cut_ingredients = False
    if cost > ingredient_budget:
        keep = ingredient_budget * columns
        cut_ingredients = len(items) > keep
        items = items[:keep]
        cost, columns = ingredient_layout(items, FLOOR_PX)
    directions_text, cut_directions = cut_to_lines(
        directions_text, limit, available - cost
    )
    return Column(
        name,
        meta,
        items,
        directions_text,
        FLOOR_PX,
        FLOOR_LINE,
        columns,
        cut_ingredients or cut_directions,
    )


def build_columns(recipes: list[dict[str, Any]], slots: int = 3) -> list[Column]:
    """The selected recipes as columns, at most ``slots`` of them.

    The cap is belt and braces — the integration already clamps the selection
    (``recipes.MAX_SELECTION``) — but the layout is where a fourth column would
    actually break something, so it is refused here too.
    """
    return [build_column(recipe) for recipe in (recipes or [])[:slots]]
