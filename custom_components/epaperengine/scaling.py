"""Cooking a recipe for a different number of people (FSD §8.2, Festlegung 2026-08-22).

FSD §8.2 rules portion scaling out — ``ingredients`` is free text at Paprika, so
it would need parsing. It was right about the parsing and wrong about the
conclusion, and the collection says so: of **758 ingredient lines, 582 (76 %)
open with a quantity** [gemessen 2026-08-22]. The 176 that do not are almost
entirely "Salz", "Pfeffer", "Zitronensaft" — the lines nobody would scale
anyway, so leaving them untouched is the correct behaviour rather than a gap.

**The rules, as decided** [Wolfgang, 2026-08-22]:

* **only the ingredients.** The directions are left exactly as written. A
  quantity repeated in the directions is a mistake in the recipe and belongs
  fixed in Paprika — this module neither scales it nor looks for it.
* **no rounding.** One decimal place, and the cook rounds in the kitchen:
  187,5 g of butter is an honest number, "190 g" is an invention with an
  opinion in it.
* **only the leading quantity of a line.** "8 Saiblingsfilets à 60 g" doubles
  to sixteen fillets of sixty grams, which is what a cook means; the ``à 60 g``
  is per piece and must not move.

Pure functions on plain strings — no Home Assistant, no store, no network — so
the whole thing is testable, which for arithmetic that ends up in somebody's
dinner is the least it can be.
"""

from __future__ import annotations

import re
from typing import Any

# Fractions Paprika's users actually type, plus the ASCII form.
VULGAR = {
    "½": 0.5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 0.25, "¾": 0.75,
    "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6, "⅛": 0.125,
    "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}

_NUMBER = r"\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|\d+\s*/\s*\d+|[" + "".join(VULGAR) + r"]"

# A leading quantity, optionally a range ("2-3", "2 bis 3"). Anything before it
# other than "ca." means the line does not open with a quantity and is left be.
LEADING = re.compile(
    rf"^(\s*(?:ca\.?\s*|etwa\s*)?)({_NUMBER})(\s*(?:-|–|—|bis)\s*)?({_NUMBER})?",
    re.IGNORECASE,
)


def parse_number(text: str) -> float | None:
    """``"1,5"``, ``"1/2"``, ``"½"`` → a float. ``None`` if it is not a number."""
    token = text.strip()
    if not token:
        return None
    if token in VULGAR:
        return VULGAR[token]
    if "/" in token:
        top, _, bottom = token.partition("/")
        try:
            return float(top.strip().replace(",", ".")) / float(bottom.strip().replace(",", "."))
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def format_number(value: float, decimal: str = ",") -> str:
    """One decimal place, and no decimal at all when it would be ``.0``.

    Not rounded to anything friendlier [Festlegung]: 187,5 g is what the
    arithmetic says, and the person at the stove is better placed to decide
    what to do about the half gram than this function is.
    """
    text = f"{value:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(".", decimal)


def _decimal_separator(line: str) -> str:
    """Write numbers back the way this recipe writes them."""
    return "," if re.search(r"\d,\d", line) else ("." if re.search(r"\d\.\d", line) else ",")


def scale_line(line: str, factor: float) -> str:
    """Multiply the quantity a line opens with. Everything else is untouched."""
    if factor == 1:
        return line
    match = LEADING.match(line)
    if not match:
        return line
    lead, first, joiner, second = match.groups()
    start = parse_number(first)
    if start is None:
        return line
    decimal = _decimal_separator(line)

    scaled = format_number(start * factor, decimal)
    if joiner and second is not None:
        end = parse_number(second)
        if end is not None:
            scaled += joiner + format_number(end * factor, decimal)
        else:  # pragma: no cover - the regex cannot produce this
            scaled += joiner + second
    else:
        # A joiner without a second number is not a range ("2-3") but a dash
        # that belongs to the text ("1 - Blumenkohl"); leave it where it was.
        scaled += joiner or ""
    return lead + scaled + line[match.end():]


def scale_ingredients(text: str, factor: float) -> str:
    """Every line of the ingredient list, scaled where it opens with a quantity."""
    if factor == 1:
        return text
    return "\n".join(scale_line(line, factor) for line in (text or "").split("\n"))


def base_servings(recipe: dict[str, Any]) -> float | None:
    """The number a recipe is written for — ``None`` when it does not say.

    Eight of this household's 53 recipes have an empty ``servings`` field
    [gemessen 2026-08-22]. Without a base there is nothing to scale *from*, and
    guessing four would silently produce wrong quantities.
    """
    return parse_number(str(recipe.get("servings") or ""))


def scaled(recipe: dict[str, Any], target: float | None) -> dict[str, Any]:
    """A copy of the recipe cooked for ``target`` people.

    Returns the recipe unchanged when there is nothing to do: no target, no
    usable base, or a target that equals the base. ``servings`` is rewritten to
    the target — the wall must never show quantities for six next to the word
    "four".
    """
    base = base_servings(recipe)
    if not target or not base or base <= 0 or target <= 0 or target == base:
        return dict(recipe)
    factor = target / base
    out = dict(recipe)
    out["ingredients"] = scale_ingredients(str(recipe.get("ingredients") or ""), factor)
    out["servings"] = format_number(float(target))
    out["scaled_from"] = format_number(base)
    return out
