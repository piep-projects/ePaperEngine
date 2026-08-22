"""The page and the model must agree on every measurement they share.

``recipe_layout.py`` decides whether a recipe fits by adding up a head, two
headings and a number of body lines. ``recipes.html.j2`` then *sets* those
things in CSS. If the two disagree — a title at 40 px in the page and 32 px in
the model — nothing fails, nothing logs, and every column is mis-measured by
the difference. The page clips with ``overflow: hidden``, so it comes out as
text quietly missing from the wall.

That happened: the model was moved to a 32 px title and the CSS was not, and
the page ran with the old 40 px for a full release cycle. This file is the
answer — the numbers are read straight out of the stylesheet and compared with
the constants.

Pure stdlib, no Jinja: the stylesheet is inside a ``{# … #}``-headed template
but the CSS itself is plain text, and the values wanted here are literals.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import recipe_layout as rl  # noqa: E402

TEMPLATE = REPO_ROOT / "addon-epaperengine" / "templates" / "recipes.html.j2"


def rules(selector: str, source: str) -> list[str]:
    """Every rule body whose selector list mentions ``selector``.

    A list, because a property can live in a grouped rule (``.heading, .group``)
    and the specific one further down.
    """
    found = [
        match.group(1)
        for match in re.finditer(rf"(?m)^\s*{re.escape(selector)}\s*[,{{]", source)
        for match in [re.search(r"\{(.*?)\}", source[match.start():], re.S)]
        if match
    ]
    assert found, f"no rule for {selector!r} in {TEMPLATE.name}"
    return found


def rule(selector: str, source: str) -> str:
    """All rule bodies for ``selector``, joined — for substring checks."""
    return "\n".join(rules(selector, source))


def px(selector: str, prop: str, source: str) -> int:
    """One pixel value out of the rules for ``selector``."""
    for body in rules(selector, source):
        match = re.search(rf"(?m)^\s*{re.escape(prop)}\s*:\s*(-?\d+)px", body)
        if match:
            return int(match.group(1))
    raise AssertionError(f"no {prop!r} in any rule for {selector!r}")


class TestTemplateMatchesTheModel(unittest.TestCase):
    def setUp(self) -> None:
        self.css = TEMPLATE.read_text(encoding="utf-8")

    def test_the_canvas(self) -> None:
        self.assertEqual(px("html,\n      body", "width", self.css), rl.CANVAS_W)
        self.assertEqual(px("html,\n      body", "height", self.css), rl.CANVAS_H)
        self.assertEqual(px("main", "padding", self.css), rl.MARGIN)
        self.assertEqual(px("main", "gap", self.css), rl.GUTTER)

    def test_the_head(self) -> None:
        """Title and meta are what ``head_lines`` adds up."""
        self.assertEqual(px(".title", "font-size", self.css), rl.TITLE_PX)
        self.assertEqual(px(".title", "line-height", self.css), rl.TITLE_LINE)
        self.assertEqual(px(".meta", "line-height", self.css), rl.META_LINE)
        self.assertEqual(px(".rule", "margin-bottom", self.css), rl.RULE_GAP)

    def test_the_blocks(self) -> None:
        self.assertEqual(px(".heading", "font-size", self.css), rl.HEADING_PX)
        self.assertEqual(px(".heading", "height", self.css), rl.HEADING_BLOCK)
        self.assertEqual(px(".group", "margin-bottom", self.css), rl.GROUP_GAP)
        self.assertEqual(px(".body", "column-gap", self.css), rl.GUTTER)

    def test_the_separator_sits_in_the_middle_of_the_gutter(self) -> None:
        # A 2 px line centred in the gutter spans −21…−19 of a 40 px gap.
        self.assertEqual(
            px(".column + .column::before", "left", self.css), -(rl.GUTTER // 2 + 1)
        )
        self.assertEqual(px(".column + .column::before", "width", self.css), 2)

    def test_the_body_steps_are_the_models(self) -> None:
        """Set inline from ``font_px``/``line_px``, so the template must not
        carry a competing font-size on the column."""
        self.assertIn("font-size: {{ column.font_px }}px", self.css)
        self.assertIn("line-height: {{ column.line_px }}px", self.css)
        self.assertIn("column-count: {{ column.body_columns }}", self.css)
        self.assertIn("column-count: {{ column.ingredient_columns }}", self.css)

    def test_the_shortening_marker_has_the_room_the_model_reserved(self) -> None:
        marker = px(".cut", "font-size", self.css) + px(".cut", "margin-top", self.css)
        self.assertLessEqual(marker, rl.CUT_BLOCK, "the cut marker outgrew its reserve")


class TestColour(unittest.TestCase):
    """Only the six Spectra primaries, plus the one grey FSD §7 allows.

    Anything else is dithered into a raster — measured on the wall: a 2 px
    #aaaaaa hairline came out as 67 % black pixels in one column and 33 % in the
    next, which is a dotted trail and not a rule.
    """

    SPECTRA = {"#fff", "#ffffff", "#000", "#000000", "#dc1e1e", "#1e8c46", "#1e3cb4", "#f0c81e"}
    ALLOWED_GREY = {"#555555"}  # the meta line, straight from the mockup

    def test_every_colour_is_a_primary(self) -> None:
        css = TEMPLATE.read_text(encoding="utf-8")
        # Strip both comment kinds: the Jinja header and the CSS notes name
        # colours that were *rejected*, and naming them is the point.
        css = re.sub(r"\{#.*?#\}", "", css, flags=re.S)
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for colour in set(re.findall(r"#[0-9a-fA-F]{3,6}", css)):
            self.assertIn(
                colour.lower(),
                self.SPECTRA | self.ALLOWED_GREY,
                f"{colour} is not a Spectra primary — it will be dithered",
            )

    def test_the_title_and_the_headings_share_the_green(self) -> None:
        css = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("#1e8c46", rule(".title", css))
        self.assertIn("#1e8c46", rule(".heading", css))


if __name__ == "__main__":
    unittest.main()
