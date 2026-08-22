"""How a recipe is fitted into its column (FSD §7, §8.2).

The policy, not the drawing — like ``outage.py`` and the integration's
``resolve.py``: a pure function over plain data, so the part that is worth
testing can be tested without Chromium, a panel or a wait.

**What the specification fixes** [Festlegung 2026-08-20]:

* three columns of 773 px, landscape only;
* type shrinks in steps **28 → 26 → 24 px, per column separately**, so one long
  recipe does not shrink the short ones next to it;
* **24 px is the floor** — colour carries down to 24 px on this panel and no
  further (FSD §7);
* below that the text is **shortened and the shortening is made visible**.

**What the specification leaves open, decided here** [Vorschlag 2026-08-22, in
need of a look at the real wall]: *which* part gets shortened. The ingredients
win. You cannot cook from directions whose ingredient list was cut off, while
directions that stop three steps in are still a recipe you can follow with a
phone in your other hand. The ingredients are capped at
``INGREDIENTS_SHARE`` of the column all the same — a recipe that is nothing but
a 2.000-character ingredient list would otherwise push the directions out
entirely, and a column that shows no directions at all looks broken rather than
shortened.

The capacity numbers are the ones FSD §7 computed for the recipe column (773 px
with a title, a meta line and two headings) and are marked **[Vorschlag, am
Panel zu prüfen]** there — measuring them on the real panel is the open point
FSD §15 carries. When that measurement lands, this table is the one place to
change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# (type size in px, characters the column carries at that size) — FSD §7.
STEPS: tuple[tuple[int, int], ...] = ((28, 950), (26, 1150), (24, 1350))

FLOOR_PX, FLOOR_BUDGET = STEPS[-1]

# Ceiling for the ingredients when everything has to be cut. Not a rule about
# normal recipes — at 1.350 characters this only bites when the ingredient list
# alone is longer than two thirds of the column.
INGREDIENTS_SHARE = 0.65

ELLIPSIS = "…"


@dataclass
class Column:
    """One recipe, ready for the template."""

    name: str
    meta: str
    ingredients: str
    directions: str
    font_px: int
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "meta": self.meta,
            "ingredients": self.ingredients,
            "directions": self.directions,
            "font_px": self.font_px,
            "truncated": self.truncated,
        }


def length(name: str, ingredients: str, directions: str) -> int:
    """What one column has to carry. The same sum the panel forecasts with."""
    return len(name) + len(ingredients) + len(directions)


def font_for(chars: int) -> int:
    """The largest step that still holds ``chars``; the floor if none does."""
    for size, budget in STEPS:
        if chars <= budget:
            return size
    return FLOOR_PX


def shorten(text: str, budget: int) -> tuple[str, bool]:
    """Cut to ``budget`` characters at a word boundary, marked with an ellipsis.

    Returns the text and whether anything was lost. A budget that leaves no room
    yields an empty string rather than a lone ellipsis — a column ending in a
    stray "…" under an empty heading reads as a bug, not as a shortening.
    """
    if len(text) <= budget:
        return text, False
    if budget <= len(ELLIPSIS):
        return "", True
    cut = text[: budget - len(ELLIPSIS)]
    # Back up to the last space, but never more than a quarter of the budget:
    # a single very long word must not empty the column.
    space = cut.rfind(" ")
    if space > len(cut) * 0.75:
        cut = cut[:space]
    return cut.rstrip() + ELLIPSIS, True


def build_column(recipe: dict[str, Any]) -> Column:
    """Turn one recipe from the render document into a fitted column."""
    name = str(recipe.get("name") or "").strip()
    ingredients = str(recipe.get("ingredients") or "").strip()
    directions = str(recipe.get("directions") or "").strip()
    meta = " · ".join(
        part
        for part in (
            str(recipe.get("servings") or "").strip(),
            str(recipe.get("total_time") or "").strip(),
        )
        if part
    )

    chars = length(name, ingredients, directions)
    font_px = font_for(chars)
    if chars <= FLOOR_BUDGET:
        return Column(name, meta, ingredients, directions, font_px, False)

    # Past the floor: shorten. The title is never cut — it is what identifies
    # the column from across the kitchen.
    budget = max(FLOOR_BUDGET - len(name), 0)
    ingredients, cut_ingredients = shorten(
        ingredients, min(len(ingredients), int(budget * INGREDIENTS_SHARE))
    )
    directions, cut_directions = shorten(directions, max(budget - len(ingredients), 0))
    return Column(
        name, meta, ingredients, directions, FLOOR_PX, cut_ingredients or cut_directions
    )


def build_columns(recipes: list[dict[str, Any]], slots: int = 3) -> list[Column]:
    """The selected recipes as columns, at most ``slots`` of them.

    The cap is belt and braces — the integration already clamps the selection
    (``recipes.MAX_SELECTION``) — but the layout is where a fourth column would
    actually break something, so it is refused here too.
    """
    return [build_column(recipe) for recipe in (recipes or [])[:slots]]
