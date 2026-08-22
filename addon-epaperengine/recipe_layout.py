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
CANVAS_W = 2560
CANVAS_H = 1440
MARGIN = 80
GUTTER = 40
CONTENT_W = CANVAS_W - 2 * MARGIN  # 2400
COLUMN_H = CANVAS_H - 2 * MARGIN   # 1280

# The base column of FSD §8.2 and the mockup: 773 px, the width the character
# figures in FSD §7 were measured at.
COLUMN_W = 773

# **The whole screen is used, whatever the number of recipes**
# [Festlegung 2026-08-22]. Two recipes get half the canvas each, one gets all of
# it — the earlier version kept 773 px columns and centred the row, which left a
# third of a 32" display white.
#
# How the width is *used* is the craft part, and it is not "one line across
# 2.400 px": FSD §7 measures that as ~161 characters a line, and a line that
# long is hard to return from at cooking distance however large the type. So a
# recipe that is given more than one base column's worth of width flows its body
# in sub-columns of roughly 773 px.
#
#   3 recipes → 773 px each, one sub-column   (unchanged, the mockup)
#   2 recipes → 1.180 px each, one sub-column (79 characters a line; wide, but
#               a second sub-column of 570 px would be 37 and choppy for prose)
#   1 recipe  → 2.400 px, three sub-columns of 773 px
#
# The side effect is the point: a column of 1.180 px carries about twice the
# text, and 58 % of this household's recipes were over the three-column budget.
SUB_COLUMNS = {1: 3, 2: 1, 3: 1}

# Character width of DejaVu Sans as a fraction of the type size. Derived from
# FSD §7's own table — 52 characters per 773 px at 28 px — and it reproduces the
# other rows: 45 at 32 px, 40 at 36 px, ~61 at 24 px (the figure the mockup
# generator uses).
CHAR_RATIO = 0.531

# The mockup sets the recipe title at 40 px. **32 px** [Festlegung 2026-08-22]:
# the real collection has names like "Blumenkohl aus der Tajine mit gehobeltem
# Trüffel und Erbsenmousseline" — 69 characters, three lines and 168 px of a
# 1.280 px column at 40 px, before a word of recipe. At 32 px the same name is
# two lines, and it is still the largest type on the page.
TITLE_PX = 32
TITLE_LINE = 46  # advance per wrapped title line (56 at the mockup's 40 px)
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

# **One step below the floor, for the directions alone** [Festlegung 2026-08-22,
# Wolfgang: "die Schrift bei Zubereitung, wenn es nötig ist, noch etwas kleiner"].
#
# This goes past what FSD §7 measured: 24 px is the floor there, and the reason
# given is that colour stops carrying below it. The directions are black on
# white and carry no colour, and the trade this buys is the one that matters —
# a whole recipe at 22 px instead of a shortened one at 24. It applies **only**
# when the alternative is cutting text, and **only** to the directions: the
# ingredient list is what gets read across the kitchen, the directions are read
# from an arm's length away.
#
# [ungeprüft] whether 22 px is still legible at 1 m on the real panel. That is
# an eye at the wall, not a number in this file.
CRAMPED_PX, CRAMPED_LINE = 22, 31

# Ingredient items are short — "400 g Champignons" is seventeen characters — so
# the list is set in as many sub-columns as a **sensible item width** allows,
# rather than in a fixed two. The target below is what a 773 px column splits
# into two of, and it is the same width that a 1.180 px column splits into three
# of [Festlegung 2026-08-22]:
#
#   773 px   → 2 sub-columns of ~386 px   (three recipes)
#   1.180 px → 3 sub-columns of ~393 px   (two recipes)
#
# A list only splits when it has at least two items per sub-column, and only
# when the narrower measure does not cost more re-wrapped lines than the split
# saves — a list of long items stays in one column.
INGREDIENT_SUB_W = 390
INGREDIENT_WRAP_TOLERANCE = 1.15

ELLIPSIS = "…"

# Paprika's directions carry ``**emphasis**`` — in this household's collection
# the section headings of a multi-part recipe ("**Erbsenmousseline**"). Raw
# asterisks on a wall are noise, so the markers are turned into bold runs here
# rather than left to be read out loud. Nothing else of Markdown is honoured:
# guessing at a syntax the field does not promise would be worse than plain text.
MARKUP = "**"


@dataclass
class Column:
    """One recipe, measured and ready for the template."""

    name: str
    meta: str
    ingredients: list[str] = field(default_factory=list)  # source lines, "" = a gap
    directions: str = ""  # plain text, markers stripped — what was measured
    direction_lines: list[list[dict[str, Any]]] = field(default_factory=list)
    font_px: int = FLOOR_PX
    line_px: int = FLOOR_LINE
    ingredient_columns: int = 1
    truncated: bool = False
    width: int = COLUMN_W
    body_columns: int = 1
    # The directions may be set one step below the column (see CRAMPED_PX).
    directions_px: int = FLOOR_PX
    directions_line: int = FLOOR_LINE

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "meta": self.meta,
            "ingredients": self.ingredients,
            "directions": self.directions,
            "direction_lines": self.direction_lines,
            "font_px": self.font_px,
            "line_px": self.line_px,
            "ingredient_columns": self.ingredient_columns,
            "truncated": self.truncated,
            "width": self.width,
            "body_columns": self.body_columns,
            "directions_px": self.directions_px,
            "directions_line": self.directions_line,
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


def slot_width(count: int) -> int:
    """How wide one recipe is when ``count`` of them share the canvas."""
    count = max(count, 1)
    return (CONTENT_W - (count - 1) * GUTTER) // count


def sub_columns(count: int) -> int:
    """How many text columns one recipe's body flows in."""
    return SUB_COLUMNS.get(max(count, 1), 1)


def head_lines(name: str, has_meta: bool, width: int = COLUMN_W) -> int:
    """Height of title + meta + rule, in pixels.

    The head spans the recipe's **full** width — the body flows in sub-columns
    below it, the title does not.
    """
    title = max(len(wrap(name, chars_per_line(TITLE_PX, width))), 1)
    return title * TITLE_LINE + (META_LINE if has_meta else 0) + RULE_GAP


def body_room(
    name: str,
    has_meta: bool,
    line_px: int,
    width: int = COLUMN_W,
    reserve: int = 0,
) -> int:
    """Pixels one sub-column has for the body, once the head is off.

    In **pixels**, not lines: since the directions may be set one step smaller
    than the ingredients, two line heights are in play and a line count would
    have to pick one of them. ``line_px`` is only used for the safety margin.
    """
    room = COLUMN_H - head_lines(name, has_meta, width) - reserve
    return max(room - SAFETY_LINES * line_px, 0)


def chrome_px(has_ingredients: bool, has_directions: bool) -> int:
    """What the two headings and the gap between the blocks cost, in pixels.

    They travel **inside** the flow: with three sub-columns "Directions" may
    start half way down the second one, so this is part of the total rather
    than a reserve at the top.
    """
    cost = 0
    if has_ingredients:
        cost += HEADING_BLOCK
    if has_directions:
        cost += HEADING_BLOCK
    if has_ingredients and has_directions:
        cost += GROUP_GAP
    return cost


def ingredient_layout(
    items: list[str], font_px: int, width: int = COLUMN_W, columns: int = 1
) -> tuple[int, int]:
    """``(lines the block costs, number of sub-columns for the list)``.

    Splitting a list of short items is where the room for the directions comes
    from: nineteen ingredients are nineteen lines in one column, ten in two and
    seven in three.

    Only when the body itself is a single column. Once the recipe already flows
    in three sub-columns of 773 px, splitting the list again would give 386 px
    of item, and nesting a second multi-column inside the first is a layout
    neither this model nor the browser would agree on.
    """
    if not items:
        return 0, 1
    text = "\n".join(items)
    full = len(wrap(text, chars_per_line(font_px, width)))
    if columns > 1:
        return full, 1

    target = max(round(width / INGREDIENT_SUB_W), 1)
    for count in range(target, 1, -1):
        # Two items per sub-column at least — a split that leaves one item
        # standing alone under a heading looks like a mistake, not a layout.
        if len(items) < 2 * count:
            continue
        lines = len(wrap(text, chars_per_line(font_px, width // count)))
        if lines <= full * INGREDIENT_WRAP_TOLERANCE:
            return math.ceil(lines / count), count
    return full, 1


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


def runs(line: str) -> list[dict[str, Any]]:
    """One source line as ``[{"text": …, "bold": …}, …]``.

    An odd number of markers means somebody typed one and never closed it; the
    remainder stays plain rather than turning the rest of the recipe bold.
    """
    parts = line.split(MARKUP)
    closed = len(parts) % 2 == 1  # an even number of markers: every run is closed
    out: list[dict[str, Any]] = []
    for index, text in enumerate(parts):
        if not text:
            continue
        bold = index % 2 == 1 and (closed or index < len(parts) - 1)
        out.append({"text": text, "bold": bold})
    return out


def as_lines(text: str) -> list[list[dict[str, Any]]]:
    """The directions as runs per source line, ready for the template."""
    return [runs(line) for line in text.split("\n")] if text else []


def plain(text: str) -> str:
    """The text as it will be read — markers gone."""
    return text.replace(MARKUP, "")


# --- building the column ------------------------------------------------------
def build_column(
    recipe: dict[str, Any],
    servings_label: str = "{value}",
    width: int = COLUMN_W,
    columns: int = 1,
) -> Column:
    """Turn one recipe from the render document into a fitted column.

    ``servings_label`` carries the word for the number: Paprika stores
    ``servings`` as free text, and this household's recipes hold a bare ``4``.
    A lone digit under the title says nothing, so a plain number gets the word
    from the wall catalog — anything the user actually typed ("2 Gläser") is
    left exactly as written.
    """
    name = str(recipe.get("name") or "").strip()
    ingredients_text = str(recipe.get("ingredients") or "").strip()
    directions_text = str(recipe.get("directions") or "").strip()
    servings = str(recipe.get("servings") or "").strip()
    if servings.isdigit():
        servings = servings_label.format(value=servings)
    meta = " · ".join(
        part for part in (servings, str(recipe.get("total_time") or "").strip()) if part
    )
    items = [line.rstrip() for line in ingredients_text.split("\n")] if ingredients_text else []

    chrome = chrome_px(bool(items), bool(directions_text))

    def fits(font_px: int, line_px: int, dir_px: int, dir_line: int) -> tuple[bool, int]:
        """Does it fit at these sizes? Also hands back the ingredient columns."""
        cost, item_columns = ingredient_layout(items, font_px, width, columns)
        total = (
            chrome
            + cost * line_px
            + len(wrap(directions_text, chars_per_line(dir_px, width // columns))) * dir_line
        )
        room = body_room(name, bool(meta), line_px, width)
        return -(-total // columns) <= room, item_columns

    # The ladder: 28 → 26 → 24 for the whole column (FSD §8.2), and then one more
    # step for the **directions alone** before anything is cut.
    ladder = [(px, line, px, line) for px, line in STEPS]
    ladder.append((FLOOR_PX, FLOOR_LINE, CRAMPED_PX, CRAMPED_LINE))

    for font_px, line_px, dir_px, dir_line in ladder:
        ok, item_columns = fits(font_px, line_px, dir_px, dir_line)
        if ok:
            return Column(
                name,
                meta,
                items,
                plain(directions_text),
                as_lines(directions_text),
                font_px,
                line_px,
                item_columns,
                False,
                width,
                columns,
                dir_px,
                dir_line,
            )

    # Past the last step and it still does not fit: shorten (Festlegung P13).
    # The directions stay at the smaller size — more of them survive the cut.
    limit = chars_per_line(CRAMPED_PX, width // columns)
    # A shortened column carries the marker that says so, and it needs room.
    room = body_room(name, bool(meta), FLOOR_LINE, width, reserve=CUT_BLOCK) * columns
    available = max(room - chrome, 0)
    cost, item_columns = ingredient_layout(items, FLOOR_PX, width, columns)
    # The ingredients are protected, but not without limit: a column that is
    # nothing but an ingredient list shows no directions at all, which reads as
    # broken rather than as shortened.
    ingredient_budget = max(int(available * 0.6), FLOOR_LINE)
    cut_ingredients = False
    if cost * FLOOR_LINE > ingredient_budget:
        keep = (ingredient_budget // FLOOR_LINE) * item_columns
        cut_ingredients = len(items) > keep
        items = items[:keep]
        cost, item_columns = ingredient_layout(items, FLOOR_PX, width, columns)
    directions_text, cut_directions = cut_to_lines(
        directions_text, limit, max(available - cost * FLOOR_LINE, 0) // CRAMPED_LINE
    )
    return Column(
        name,
        meta,
        items,
        plain(directions_text),
        as_lines(directions_text),
        FLOOR_PX,
        FLOOR_LINE,
        item_columns,
        cut_ingredients or cut_directions,
        width,
        columns,
        CRAMPED_PX,
        CRAMPED_LINE,
    )


def build_columns(
    recipes: list[dict[str, Any]], slots: int = 3, servings_label: str = "{value}"
) -> list[Column]:
    """The selected recipes, sharing the whole canvas between them.

    The cap is belt and braces — the integration already clamps the selection
    (``recipes.MAX_SELECTION``) — but the layout is where a fourth column would
    actually break something, so it is refused here too.
    """
    chosen = (recipes or [])[:slots]
    if not chosen:
        return []
    width = slot_width(len(chosen))
    columns = sub_columns(len(chosen))
    return [
        build_column(recipe, servings_label, width, columns) for recipe in chosen
    ]
