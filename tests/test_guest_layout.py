"""The guest greeting: what fits, what shrinks, and what the page then draws.

Three things are checked here, and each one has a way of going wrong silently.

**The fit.** ``guest_layout`` measures a name with the very font file Chromium
will render it with, and shrinks the type until it fits the width. Nothing
fails when that is wrong — the name simply runs off the side of a panel nobody
is standing in front of. So the measurement is checked against the font, not
against a remembered number.

**The catalogue.** Three places name the same three faces: the add-on's
``FONTS``, the integration's ``GUEST_FONTS``, and the panel's dropdown. Two of
them are read here (the third through ``tests/test_translations.py``, which
insists every token has a label). A face added on one side and forgotten on the
other is a dropdown entry that renders in DejaVu.

**The page.** Same lesson as ``test_recipe_template``: the template *sets* in
CSS what the module *measured* in Python. A line height of 1.3 in one and 1.2
in the other mis-sizes the band behind the text by a line, and the greeting
slides out from under it.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import guest_layout as gl  # noqa: E402

TEMPLATE = REPO_ROOT / "addon-epaperengine" / "templates" / "guests.html.j2"
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"


class TestFontsShipAndOpen(unittest.TestCase):
    """A font file that is not there is a greeting set in DejaVu."""

    def test_every_declared_face_has_its_file(self) -> None:
        for token in gl.FONTS:
            path = gl.font_path(token)
            self.assertTrue(path.is_file(), f"{token}: {path} is missing")

    def test_every_face_opens_and_measures(self) -> None:
        for token in gl.FONTS:
            width = gl.width_of("Familie Berger", token, 180)
            self.assertGreater(width, 0, f"{token} measured nothing")
            # A sanity band, not a golden number: a name of fourteen characters
            # at 180 px is hundreds of pixels wide in any face, and never the
            # whole canvas.
            self.assertLess(width, gl.TEXT_W, f"{token}: 'Familie Berger' does not fit at 180 px")

    def test_the_licence_files_travel_with_the_fonts(self) -> None:
        """SIL OFL requires the licence to ship with the font. It also has to
        survive ``publish.py``, which copies the add-on directory wholesale."""
        licences = list(gl.FONT_DIR.glob("OFL-*.txt"))
        self.assertEqual(
            len(licences), len(gl.FONTS), f"one OFL per face expected, found {licences}"
        )

    def test_the_integration_knows_the_same_faces(self) -> None:
        """``const.GUEST_FONTS`` fills the panel dropdown; the add-on renders it.

        Read with ``ast`` rather than imported: ``const.py`` imports Home
        Assistant, and none of these tests may need it installed.
        """
        tree = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
        literals = {
            node.target.id: node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        tokens = tuple(
            str(literals[element.id].value)  # type: ignore[attr-defined]
            for element in literals["GUEST_FONTS"].elts  # type: ignore[attr-defined]
        )
        self.assertEqual(set(tokens), set(gl.FONTS), "const.GUEST_FONTS and FONTS differ")

        # ``DEFAULT_GUEST_FONT`` is an alias for one of the tokens above, so the
        # node is a Name and has to be looked up rather than read.
        default = literals["DEFAULT_GUEST_FONT"]
        self.assertEqual(
            str(literals[default.id].value if isinstance(default, ast.Name) else default.value),
            gl.DEFAULT_FONT,
        )

    def test_every_face_has_a_label_in_both_catalogs(self) -> None:
        """The dropdown shows ``t("guests.font.<token>")``. A face without a
        label falls back to the humanised key — "Great vibes", lower case."""
        import json

        for lang in ("en", "de"):
            catalog = json.loads(
                (COMPONENT / "frontend_i18n" / f"{lang}.json").read_text(encoding="utf-8")
            )
            for token in gl.FONTS:
                self.assertIn(f"guests.font.{token}", catalog, f"{lang}: no label for {token}")

    def test_the_panel_offers_the_same_faces(self) -> None:
        source = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        listed = re.search(r"const GUEST_FONTS = \[(.*?)\];", source, re.S)
        self.assertIsNotNone(listed, "GUEST_FONTS not found in the panel")
        tokens = set(re.findall(r'"([a-z_]+)"', listed.group(1)))
        self.assertEqual(tokens, set(gl.FONTS))


class TestFit(unittest.TestCase):
    """The wish is a starting point; the width is the constraint."""

    def test_a_short_name_keeps_its_size(self) -> None:
        block = gl.fit("Berger", gl.DEFAULT_FONT, 180, gl.NAME_MAX_LINES, gl.NAME_FLOOR_PX)
        self.assertEqual(block.font_px, 180)
        self.assertEqual(block.lines, ("Berger",))
        self.assertFalse(block.shrunk)

    def test_every_line_really_fits_the_width(self) -> None:
        """The property that matters, checked against the font rather than
        against a size somebody once wrote down."""
        for text in (
            "Familie Berger",
            "Familie Berger-Wiedemann und die Kinder",
            "Herzlich willkommen, liebe Familie Berger aus Oberbayern",
        ):
            block = gl.fit(text, gl.DEFAULT_FONT, 180, gl.NAME_MAX_LINES, gl.NAME_FLOOR_PX)
            for line in block.lines:
                self.assertLessEqual(
                    gl.width_of(line, gl.DEFAULT_FONT, block.font_px),
                    gl.TEXT_W,
                    f"{line!r} at {block.font_px} px is wider than the canvas allows",
                )

    def test_a_long_name_shrinks_rather_than_growing_a_third_line(self) -> None:
        long_name = "Familie Berger-Wiedemann und die ganze Verwandtschaft aus Oberbayern"
        block = gl.fit(long_name, gl.DEFAULT_FONT, 180, gl.NAME_MAX_LINES, gl.NAME_FLOOR_PX)
        self.assertLessEqual(len(block.lines), gl.NAME_MAX_LINES)
        self.assertTrue(block.shrunk)
        self.assertGreaterEqual(block.font_px, gl.NAME_FLOOR_PX)

    def test_the_floor_holds_and_the_text_is_never_cut(self) -> None:
        """FSD §8.4 has no "shortened" state for a greeting — unlike a recipe,
        where the directions give way. Everything typed reaches the wall."""
        essay = " ".join(["Wunderschön"] * 60)
        block = gl.fit(essay, gl.DEFAULT_FONT, 180, gl.NAME_MAX_LINES, gl.NAME_FLOOR_PX)
        self.assertEqual(block.font_px, gl.NAME_FLOOR_PX)
        self.assertEqual(" ".join(block.lines), essay)

    def test_nothing_typed_is_no_lines(self) -> None:
        for empty in ("", None, "   "):
            block = gl.fit(empty, gl.DEFAULT_FONT, 180, gl.NAME_MAX_LINES, gl.NAME_FLOOR_PX)
            self.assertEqual(block.lines, ())
            self.assertEqual(block.height, 0)

    def test_a_wish_below_the_floor_is_lifted_to_it(self) -> None:
        block = gl.fit("Berger", gl.DEFAULT_FONT, 12, gl.NAME_MAX_LINES, gl.NAME_FLOOR_PX)
        self.assertEqual(block.font_px, gl.NAME_FLOOR_PX)


class TestPlan(unittest.TestCase):
    """What the template is handed."""

    def test_defaults_survive_an_empty_section(self) -> None:
        plan = gl.plan({})
        self.assertEqual(plan.font_family, gl.FONTS[gl.DEFAULT_FONT]["family"])
        self.assertEqual(plan.name.lines, ())
        self.assertFalse(plan.band)

    def test_an_unknown_font_token_falls_back(self) -> None:
        """A typo in the store must not be the reason the wall goes dark."""
        plan = gl.plan({"name": "Berger", "font": "comic_sans"})
        self.assertEqual(plan.font_family, gl.FONTS[gl.DEFAULT_FONT]["family"])

    def test_the_band_needs_a_picture_and_some_text(self) -> None:
        both = gl.plan({"name": "Berger", "band": True}, "file:///b.jpg")
        self.assertTrue(both.band)
        # On flat white the band would be a grey stripe for nothing — and grey
        # on white is the one pairing that shows a dither raster behind the text.
        self.assertFalse(gl.plan({"name": "Berger", "band": True}).band)
        self.assertFalse(gl.plan({"band": True}, "file:///b.jpg").band)
        self.assertFalse(gl.plan({"name": "Berger", "band": False}, "file:///b.jpg").band)

    def test_the_band_covers_the_text_it_sits_behind(self) -> None:
        plan = gl.plan(
            {"name": "Familie Berger", "greeting": "Schön, dass ihr da seid!"}, "file:///b.jpg"
        )
        text = plan.name.height + gl.BLOCK_GAP + plan.greeting.height
        self.assertGreaterEqual(plan.band_height, text + 2 * gl.BAND_PAD_Y - 1)
        self.assertGreaterEqual(plan.band_top, 0)
        self.assertLessEqual(plan.band_top + plan.band_height, gl.CANVAS_H)

    def test_the_gap_is_only_counted_between_two_blocks(self) -> None:
        """The template adds the gap only when both are set; the band must be
        measured the same way or it comes out 48 px too short."""
        only_name = gl.plan({"name": "Berger"}, "file:///b.jpg")
        self.assertEqual(only_name.band_height, only_name.name.height + 2 * gl.BAND_PAD_Y)


class TestTemplateAgreesWithTheModel(unittest.TestCase):
    """The page sets in CSS what the module measured in Python."""

    def setUp(self) -> None:
        self.source = TEMPLATE.read_text(encoding="utf-8")

    def test_the_canvas_is_the_panel(self) -> None:
        self.assertIn(f"width: {gl.CANVAS_W}px", self.source)
        self.assertIn(f"height: {gl.CANVAS_H}px", self.source)

    def test_the_margin_matches(self) -> None:
        self.assertIn(f"padding: 0 {gl.MARGIN}px", self.source)

    def test_the_line_height_comes_from_the_model(self) -> None:
        """Not a literal in the CSS: it travels in as ``line_height`` so there
        is exactly one number, in ``guest_layout``."""
        self.assertIn("line-height: {{ line_height }}", self.source)
        self.assertNotRegex(self.source, r"line-height:\s*1\.\d")

    def test_the_type_sizes_come_from_the_plan(self) -> None:
        self.assertIn("font-size: {{ plan.name.font_px }}px", self.source)
        self.assertIn("font-size: {{ plan.greeting.font_px }}px", self.source)

    def test_the_lines_are_set_one_by_one_and_never_re_wrapped(self) -> None:
        """The whole point of measuring in Python: the browser must not get a
        second opinion on where the line ends."""
        self.assertIn("white-space: nowrap", self.source)
        self.assertIn("{% for line in plan.name.lines %}", self.source)
        self.assertIn("{% for line in plan.greeting.lines %}", self.source)


if __name__ == "__main__":
    unittest.main()
