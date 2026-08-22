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
import imaging  # noqa: E402

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

    def test_the_panel_offers_the_same_colours(self) -> None:
        source = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        listed = re.search(r"const GUEST_COLORS = \{(.*?)\};", source, re.S)
        self.assertIsNotNone(listed, "GUEST_COLORS not found in the panel")
        self.assertEqual(set(re.findall(r"(\w+):", listed.group(1))), set(gl.COLORS))

    def test_every_colour_has_a_label_in_both_catalogs(self) -> None:
        import json

        for lang in ("en", "de"):
            catalog = json.loads(
                (COMPONENT / "frontend_i18n" / f"{lang}.json").read_text(encoding="utf-8")
            )
            for token in gl.COLORS:
                self.assertIn(f"guests.color.{token}", catalog, f"{lang}: no label for {token}")

    def test_the_integration_knows_the_same_colours(self) -> None:
        tree = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
        literals = {
            node.target.id: node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        tokens = {
            str(element.value)  # type: ignore[attr-defined]
            for element in literals["GUEST_COLORS"].elts  # type: ignore[attr-defined]
        }
        self.assertEqual(tokens, set(gl.COLORS), "const.GUEST_COLORS and COLORS differ")

    def test_the_panel_offers_the_seam(self) -> None:
        source = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        for hook in ("guest-outline", "guest-outline-px", "data-outline-color"):
            self.assertIn(hook, source, f"the panel has no {hook}")

    def test_the_seam_labels_exist_in_both_catalogs(self) -> None:
        import json

        keys = (
            "panel.guests.outline",
            "panel.guests.outline.on",
            "panel.guests.outline.width",
            "panel.guests.outline.color",
        )
        for lang in ("en", "de"):
            catalog = json.loads(
                (COMPONENT / "frontend_i18n" / f"{lang}.json").read_text(encoding="utf-8")
            )
            for key in keys:
                self.assertIn(key, catalog, f"{lang}: no label for {key}")

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
        self.assertEqual(plan.color, gl.COLORS[gl.DEFAULT_COLOR])
        self.assertEqual(plan.angle, 0.0)

    def test_an_unknown_font_token_falls_back(self) -> None:
        """A typo in the store must not be the reason the wall goes dark."""
        plan = gl.plan({"name": "Berger", "font": "comic_sans"})
        self.assertEqual(plan.font_family, gl.FONTS[gl.DEFAULT_FONT]["family"])

    def test_the_colour_is_always_a_spectra_primary(self) -> None:
        """The whole reason the colour is a closed list [P23]: anything else is
        mixed out of these six by dithering, and on a glyph edge that reads as
        speckle rather than as a tint."""
        for token, rgb in gl.COLORS.items():
            self.assertIn(rgb, imaging.SPECTRA, f"{token} {rgb} is not a panel primary")
        self.assertEqual(len(gl.COLORS), len(imaging.SPECTRA))

    def test_an_unknown_colour_falls_back(self) -> None:
        self.assertEqual(gl.plan({"color": "puce"}).color, gl.COLORS[gl.DEFAULT_COLOR])

    def test_the_colour_reaches_the_template_as_css(self) -> None:
        self.assertEqual(gl.plan({"color": "white"}).as_dict()["color"], "rgb(255, 255, 255)")

    def test_the_angle_is_bounded_and_survives_nonsense(self) -> None:
        self.assertEqual(gl.plan({"angle": 90}).angle, gl.ANGLE_LIMIT)
        self.assertEqual(gl.plan({"angle": -90}).angle, -gl.ANGLE_LIMIT)
        self.assertEqual(gl.plan({"angle": "schräg"}).angle, 0.0)
        self.assertEqual(gl.plan({}).angle, 0.0)

    def test_a_tilted_block_still_fits_the_canvas(self) -> None:
        """The property the whole fitting loop exists for. A name that fits
        lying flat claims ``w·cos + h·sin`` once tilted — without this check it
        would hang over the edge of the panel and be clipped in silence."""
        long_name = "Familie Berger-Wiedemann und die ganze Verwandtschaft"
        for angle in (0, 10, 25, 40, 45, -30):
            plan = gl.plan(
                {"name": long_name, "greeting": "Schön, dass ihr da seid!", "angle": angle}
            )
            self.assertLessEqual(plan.box_w, gl.TEXT_W, f"{angle}°: too wide")
            self.assertLessEqual(plan.box_h, gl.TEXT_H, f"{angle}°: too tall")

    def test_tilting_costs_type_size_rather_than_the_canvas(self) -> None:
        """It has to give somewhere, and the specification says never the text
        (P21) — so it is the size that gives."""
        long_name = "Familie Berger-Wiedemann und die ganze Verwandtschaft"
        flat = gl.plan({"name": long_name, "angle": 0})
        steep = gl.plan({"name": long_name, "angle": 40})
        self.assertLess(steep.name.font_px, flat.name.font_px)
        self.assertEqual(" ".join(steep.name.lines), long_name)

    # --- the outline (FSD §8.4's third remedy, P24) ---------------------------
    def test_the_seam_is_off_until_it_is_asked_for(self) -> None:
        plan = gl.plan({"name": "Berger"})
        self.assertFalse(plan.outline)
        # Zero rather than "the configured width, unused": the template asks
        # ``plan.outline`` before it draws anything, and a stroke width left
        # standing would be a trap for whoever changes that condition next.
        self.assertEqual(plan.stroke_px, 0)

    def test_the_stylesheet_gets_twice_the_visible_width(self) -> None:
        """``-webkit-text-stroke`` centres its stroke and the fill covers the
        inner half, so half of what CSS is told is what can be seen. The factor
        lives in the module rather than in somebody's head."""
        plan = gl.plan({"name": "Berger", "outline": True, "outline_px": 8})
        self.assertEqual(plan.outline_px, 8)
        self.assertEqual(plan.stroke_px, 16)
        self.assertEqual(plan.as_dict()["stroke_px"], 16)

    def test_the_seam_width_is_bounded(self) -> None:
        """Below FSD §7's 2 px floor a seam breaks up into dots; above the
        ceiling the counter colour starts eating the letter it frames."""
        self.assertEqual(gl.plan({"outline": True, "outline_px": 0}).outline_px, gl.DEFAULT_OUTLINE_PX)
        self.assertEqual(gl.plan({"outline": True, "outline_px": 1}).outline_px, gl.OUTLINE_MIN_PX)
        self.assertEqual(gl.plan({"outline": True, "outline_px": 999}).outline_px, gl.OUTLINE_MAX_PX)
        self.assertEqual(gl.plan({"outline": True, "outline_px": "dick"}).outline_px, gl.DEFAULT_OUTLINE_PX)

    def test_the_seam_colour_is_a_primary_too(self) -> None:
        """Same reason as the fill, only more so: a seam is the thinnest feature
        on the page, and a dithered one would speckle exactly where it is meant
        to separate the letter from the picture."""
        self.assertIn(gl.COLORS[gl.DEFAULT_OUTLINE_COLOR], imaging.SPECTRA)
        plan = gl.plan({"outline": True, "outline_color": "puce"})
        self.assertEqual(plan.outline_color, gl.COLORS[gl.DEFAULT_OUTLINE_COLOR])

    def test_the_seam_widens_the_block_it_wraps(self) -> None:
        """It is drawn outside the glyphs, so it is part of the geometry — not
        something for the browser to discover at the edge of the canvas."""
        plain = gl.plan({"name": "Berger"})
        seamed = gl.plan({"name": "Berger", "outline": True, "outline_px": 12})
        self.assertEqual(seamed.width, plain.width + 24)
        self.assertEqual(seamed.height, plain.height + 24)

    def test_a_seam_and_a_tilt_together_still_fit(self) -> None:
        """The combination that broke the first two attempts at this loop."""
        for angle in (0, 25, 40, 45):
            for width in (2, 8, 16, 32):
                plan = gl.plan(
                    {
                        "name": "Ulla & Christian",
                        "greeting": "Schön, dass ihr da seid!",
                        "name_px": 240,
                        "greeting_px": 200,
                        "outline": True,
                        "outline_px": width,
                        "angle": angle,
                    }
                )
                self.assertFalse(plan.cramped, f"{angle}° / {width} px seam: {plan.box_w}×{plan.box_h}")

    def test_the_search_beats_shrinking_the_type_alone(self) -> None:
        """The measured case: a 52-character name at 40°.

        Walking the type size on its own drove it to one 1.563 px line at the
        72 px floor — over budget *and* barely readable. Wrapping it instead
        buys back type size, which is why the width budget is searched as well.
        """
        plan = gl.plan(
            {"name": "Familie Berger-Wiedemann und die ganze Verwandtschaft", "angle": 40}
        )
        self.assertFalse(plan.cramped)
        self.assertGreater(plan.name.font_px, gl.NAME_FLOOR_PX)
        self.assertEqual(len(plan.name.lines), 2)

    def test_the_rotated_box_maths(self) -> None:
        self.assertEqual(gl.rotated_box(1000, 400, 0), (1000, 400))
        self.assertEqual(gl.rotated_box(1000, 400, 90), (400, 1000))
        # 45° is the symmetric case: both sides become (w + h) / √2.
        self.assertEqual(gl.rotated_box(1000, 400, 45), gl.rotated_box(1000, 400, -45))

class TestTemplateAgreesWithTheModel(unittest.TestCase):
    """The page sets in CSS what the module measured in Python."""

    def setUp(self) -> None:
        self.source = TEMPLATE.read_text(encoding="utf-8")

    def test_the_canvas_is_the_panel(self) -> None:
        self.assertIn(f"width: {gl.CANVAS_W}px", self.source)
        self.assertIn(f"height: {gl.CANVAS_H}px", self.source)

    def test_the_block_is_shrink_wrapped_and_bounded(self) -> None:
        """The box the fit measured is the box the browser draws: shrink-wrapped
        and capped at the same width budget. A full-width container would turn
        every tilt into a diagonal several screens wide."""
        self.assertIn("width: max-content", self.source)
        self.assertIn(f"max-width: {gl.TEXT_W}px", self.source)

    def test_the_tilt_and_the_colour_come_from_the_plan(self) -> None:
        self.assertIn("rotate({{ plan.angle }}deg)", self.source)
        self.assertIn("color: {{ plan.color }}", self.source)

    def test_the_seam_is_painted_under_the_fill(self) -> None:
        """Without ``paint-order`` the stroke is painted over the fill and eats
        half its width out of the letter — on a script face that takes the thin
        connecting strokes first, which is the opposite of the point."""
        self.assertIn("-webkit-text-stroke: {{ plan.stroke_px }}px {{ plan.outline_color }}", self.source)
        self.assertIn("paint-order: stroke fill", self.source)
        self.assertIn("{%- if plan.outline %}", self.source)

    def test_the_notice_does_not_inherit_the_seam(self) -> None:
        block = self.source[self.source.index(".empty {"):]
        block = block[: block.index("}")]
        self.assertIn("-webkit-text-stroke: 0", block)

    def test_the_text_has_no_ground_of_its_own(self) -> None:
        """Festlegung P23. The band left, and nothing may creep back in as a
        background on the text box — that is the whole point of the change."""
        block = self.source[self.source.index(".text {"):]
        block = block[: block.index("}")]
        self.assertNotIn("background", block)

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
