"""How a recipe is fitted into its column (FSD §7, §8.2, Mockup 09).

This file exists because the first version got it wrong in a way that was
invisible to every test it had: the column was budgeted in **characters**, FSD
§7's own figure, and the first real recipe ran off the bottom of the canvas and
was clipped in silence. Nineteen ingredients of fifteen characters are 285
characters — five lines by that model, nineteen lines on the wall.

So the load-bearing test here is ``TestItFits``: build the column, measure it
the way the page will be set, and assert it is inside 1.280 px. Everything else
is detail around that.

Pure stdlib, like ``test_outage.py``: ``recipe_layout.py`` carries no Pillow and
no aiohttp precisely so this runs where nothing is installed.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import recipe_layout as rl  # noqa: E402


def recipe(name: str = "Test", ingredients: str = "", directions: str = "", **extra):
    return {"name": name, "ingredients": ingredients, "directions": directions, **extra}


def height(column) -> int:
    """The height the template will set this column at, in pixels.

    Mirrors the CSS of ``recipes.html.j2``: the head spans the recipe's full
    width, the body flows in ``body_columns`` sub-columns below it, and the two
    headings travel inside that flow. In pixels rather than lines because the
    directions may be set one step smaller than the ingredients.
    """
    body = column.body_columns
    total = rl.chrome_px(bool(column.ingredients), bool(column.directions))
    if column.ingredients:
        cost, columns = rl.ingredient_layout(
            column.ingredients, column.font_px, column.width, body
        )
        assert columns == column.ingredient_columns, "ingredient sub-columns drifted"
        total += cost * column.line_px
    if column.directions:
        limit = rl.chars_per_line(column.directions_px, column.width // body)
        total += len(rl.wrap(column.directions, limit)) * column.directions_line
    # Balanced across the sub-columns — the tallest is what the canvas holds.
    tallest = -(-total // body)
    head = rl.head_lines(column.name, bool(column.meta), column.width)
    return head + tallest + (rl.CUT_BLOCK if column.truncated else 0)


# A real one: 69-character title (three lines at 40 px), 19 short ingredient
# lines, 1.500 characters of directions. Before the line model this rendered at
# 24 px and was cut off by the canvas edge with nothing to show for it.
LONG_TITLE = "Blumenkohl aus der Tajine mit gehobeltem Trüffel und Erbsenmousseline"
MANY_ITEMS = "\n".join(
    [
        "1 Blumenkohl", "6 Schalotten", "400 g Champignons", "400 g Sellerie",
        "125 g Butter", "1 Dose Trüffelfond", "Etwas Olivenöl", "Salz", "Pfeffer",
        "Muskat", "1 kleiner Sommertrüffel", "", "250 g Erbsen", "200 g Butter",
        "Salz", "Zucker", "Zitronensaft", "Pfeffer",
    ]
)


class TestMeasuring(unittest.TestCase):
    def test_characters_per_line_reproduces_the_fsd_table(self) -> None:
        """FSD §7: 52 characters per **773 px** column at 28 px, 45 at 32, 40 at 36.

        The width is now passed explicitly. FSD §7's table was measured against
        the mockup's 773 px column, and since P30 dropped the margin to 32 px
        the real column is 805 px — the *table* is still right, it simply no
        longer describes the current column. What is being checked here is the
        character model, not the layout: ``CHAR_RATIO`` is a property of DejaVu
        Sans and must keep reproducing all four rows.
        """
        for font_px, expected in ((28, 52), (32, 45), (36, 40), (24, 61)):
            self.assertEqual(rl.chars_per_line(font_px, 773), expected)

    def test_the_character_ratio_matches_the_real_font(self) -> None:
        """``CHAR_RATIO`` against DejaVu Sans itself [gemessen 2026-08-23, P32].

        It was derived from FSD §7's table and reproduced it, which is not the
        same as being right — the table could have been wrong too. So it is
        measured against the very file Chromium draws with, the way the guest
        greeting measures its script faces (P21).

        Two traps this guards. **The wrong DejaVu**: the add-on image also
        carries ``DejaVuSansCondensed``, and fontconfig lists it under the
        family "DejaVu Sans" as well — ``fc-match`` resolves to the Book face,
        but a future image might not. **The wrong sample**: measured on German
        recipe prose, not on an alphabet; average glyph width is a property of
        the language as much as of the typeface.

        Skipped where the font is not installed, so CI needs no font package.
        """
        candidates = [
            pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            pathlib.Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        ]
        path = next((c for c in candidates if c.exists()), None)
        if path is None:
            self.skipTest("DejaVu Sans is not installed here")
        try:
            from PIL import ImageFont
        except ImportError:
            self.skipTest("Pillow is not installed here")

        probe = (
            "Kürbis waschen, entkernen und in grobe Würfel schneiden — schälen muss "
            "man Hokkaido nicht. Zwiebel und Ingwer fein hacken und in Butter glasig "
            "dünsten, dabei nicht bräunen lassen."
        )
        for font_px in (22, 24, 26, 28, 32, 36):
            width = ImageFont.truetype(str(path), font_px).getlength(probe) / len(probe)
            for column in (773, rl.COLUMN_W):
                measured = int(column // width)
                self.assertLessEqual(
                    abs(rl.chars_per_line(font_px, column) - measured),
                    1,
                    f"{font_px} px on {column} px: model "
                    f"{rl.chars_per_line(font_px, column)}, font {measured}",
                )

    def test_the_wider_column_carries_more_of_a_line(self) -> None:
        """What P30 bought sideways, in the one number that shows it."""
        self.assertEqual(rl.COLUMN_W, 805)
        self.assertEqual(rl.chars_per_line(28), 54)

    def test_a_source_line_costs_a_line_however_short_it_is(self) -> None:
        """The whole reason the character budget failed."""
        self.assertEqual(len(rl.wrap("Salz\nPfeffer\nMuskat", 60)), 3)

    def test_a_blank_source_line_keeps_its_line(self) -> None:
        self.assertEqual(rl.wrap("a\n\nb", 60), ["a", "", "b"])

    def test_prose_wraps_greedily_at_the_limit(self) -> None:
        lines = rl.wrap("aaa bbb ccc ddd", 7)
        self.assertEqual(lines, ["aaa bbb", "ccc ddd"])

    def test_a_wrapping_title_eats_into_the_body(self) -> None:
        """The reason the title came down to 32 px: at 40 px this name was
        three lines and 168 px of a 1.280 px column."""
        short = rl.head_lines("Suppe", True)
        long = rl.head_lines(LONG_TITLE, True)
        self.assertGreater(long, short)
        self.assertLess(rl.body_room(LONG_TITLE, True, 34), rl.body_room("Suppe", True, 34))

    def test_the_title_is_the_largest_type_on_the_page(self) -> None:
        self.assertEqual(rl.TITLE_PX, 32)
        self.assertGreaterEqual(rl.TITLE_PX, rl.HEADING_PX)
        self.assertGreater(rl.TITLE_PX, rl.STEPS[0][0])


class TestTypeSize(unittest.TestCase):
    def test_the_steps_are_the_ones_the_panel_was_measured_with(self) -> None:
        """28 → 26 → 24 and nothing in between (FSD §7, Festlegung 2026-08-20)."""
        self.assertEqual([size for size, _ in rl.STEPS], [28, 26, 24])

    def test_a_short_recipe_gets_the_largest_size(self) -> None:
        column = rl.build_column(recipe("Suppe", "Salz\nPfeffer", "Kochen."))
        self.assertEqual(column.font_px, 28)
        self.assertFalse(column.truncated)

    def test_it_steps_down_before_it_shortens(self) -> None:
        """Shrinking is what the type steps are for; cutting is the last resort."""
        # 260 words fitted 28 px once the column grew by 96 px (P30) — the
        # case has to stay a case, so it grows with the column.
        column = rl.build_column(recipe("Suppe", "Salz", "Wort " * 340))
        self.assertLess(column.font_px, 28)
        self.assertFalse(column.truncated)

    def test_the_directions_go_one_step_below_the_floor_before_anything_is_cut(self) -> None:
        """[Festlegung 2026-08-22] Past FSD §7's 24 px floor, for the directions
        alone — a whole recipe at 22 px beats a shortened one at 24. The
        ingredient list stays at the column size: it is what gets read across
        the kitchen."""
        column = rl.build_column(recipe("Suppe", "Salz\nPfeffer", "Wort " * 400))
        self.assertEqual(column.font_px, rl.FLOOR_PX)
        self.assertEqual(column.directions_px, rl.CRAMPED_PX)
        self.assertFalse(column.truncated)

    def test_a_recipe_that_fits_keeps_the_directions_at_the_column_size(self) -> None:
        """The small step is a last resort, not a default."""
        column = rl.build_column(recipe("Suppe", "Salz", "Kochen."))
        self.assertEqual(column.directions_px, column.font_px)

    def test_below_the_floor_it_stays_at_24(self) -> None:
        """24 px is the floor — colour stops carrying below it (FSD §7)."""
        column = rl.build_column(recipe("Suppe", "Salz", "Wort " * 900))
        self.assertEqual(column.font_px, 24)
        self.assertTrue(column.truncated)

    def test_one_long_recipe_does_not_shrink_the_short_one_beside_it(self) -> None:
        """The whole reason the step is decided per column (FSD §8.2)."""
        columns = rl.build_columns(
            [recipe("Kurz", "Salz", "Kochen."), recipe("Lang", "Salz", "Wort " * 900)]
        )
        self.assertEqual(columns[0].font_px, 28)
        self.assertEqual(columns[1].font_px, 24)


class TestItFits(unittest.TestCase):
    """The regression that started all of this: a column must never be taller
    than the space it is set in. The page clips with ``overflow: hidden``, so
    the failure mode is silent — half a recipe, no marker, nothing in the log."""

    CASES = {
        "the recipe that was clipped": recipe(LONG_TITLE, MANY_ITEMS, "Schritt. " * 170),
        "nothing but ingredients": recipe("Einkauf", "\n".join(["Zutat"] * 60), ""),
        "nothing but directions": recipe("Text", "", "Wort " * 900),
        "one enormous word": recipe("Lang", "x" * 400, "y" * 4000),
        "a title of its own length": recipe("Sehr langer Name " * 6, "Salz", "Kochen."),
        "empty": recipe("Leer", "", ""),
        "the longest in the collection": recipe("Rezept", MANY_ITEMS, "Satz. " * 1600),
    }

    def test_every_column_stays_inside_the_canvas(self) -> None:
        """At every recipe count — the width and the sub-columns change with it."""
        for label, data in self.CASES.items():
            for count in (1, 2, 3):
                with self.subTest(f"{label} · {count} recipes"):
                    column = rl.build_columns([data] * count)[0]
                    self.assertLessEqual(
                        height(column),
                        rl.COLUMN_H,
                        f"{label} at {count}: {height(column)} px in {rl.COLUMN_H} px",
                    )

    def test_what_does_not_fit_says_so(self) -> None:
        """FSD §8.2: "wird gekürzt und das sichtbar vermerkt".

        The fixture had to grow when P30 gave every column 96 px more height:
        the recipe that used to be clipped at three abreast now fits. That is
        the change working, not the rule weakening — so the case is made large
        enough that no type step and no cramped directions can save it.
        """
        huge = recipe("Suppe", "Salz\nPfeffer", "Wort " * 900)
        column = rl.build_columns([huge] * 3)[0]
        self.assertTrue(column.truncated)


class TestTheWholeScreen(unittest.TestCase):
    """[Festlegung 2026-08-22] Two recipes get half the canvas each, one gets
    all of it. The earlier version kept 773 px columns and centred the row,
    which left a third of a 32" display white."""

    def test_the_recipes_fill_the_canvas(self) -> None:
        for count in (1, 2, 3):
            used = count * rl.slot_width(count) + (count - 1) * rl.GUTTER
            self.assertGreaterEqual(used, rl.CONTENT_W - count, f"{count} recipes")
            self.assertLessEqual(used, rl.CONTENT_W, f"{count} recipes")

    def test_the_widths_follow_the_margin(self) -> None:
        """The mockup generator writes COL3 = 773 and COL2 = 1180 — both are
        (2400 − gutters) / n, i.e. the **80 px** margin it was drawn with. Since
        P30 the margin is 32 px, so the same arithmetic gives 805 and 1228. The
        rule is unchanged; only the number the rule is applied to moved, and
        this test exists so the two cannot drift apart silently.
        """
        self.assertEqual(rl.slot_width(3), (rl.CONTENT_W - 2 * rl.GUTTER) // 3)
        self.assertEqual(rl.slot_width(2), (rl.CONTENT_W - rl.GUTTER) // 2)
        self.assertEqual(rl.slot_width(1), rl.CONTENT_W)
        self.assertEqual((rl.slot_width(3), rl.slot_width(2), rl.slot_width(1)), (805, 1228, 2496))

    def test_one_recipe_flows_in_three_sub_columns(self) -> None:
        """Not one line 160 characters wide (FSD §7)."""
        column = rl.build_columns([recipe("Suppe", "Salz", "Kochen.")])[0]
        self.assertEqual(column.body_columns, 3)
        self.assertLessEqual(rl.chars_per_line(28, column.width // column.body_columns), 60)

    def test_the_extra_width_is_what_stops_the_shortening(self) -> None:
        """The point of the change: a recipe that had to be cut into a third of
        the screen fits when it gets half or all of it."""
        data = recipe(LONG_TITLE, MANY_ITEMS, "Schritt für Schritt. " * 100)
        self.assertTrue(rl.build_columns([data] * 3)[0].truncated)
        self.assertFalse(rl.build_columns([data] * 2)[0].truncated)
        self.assertFalse(rl.build_columns([data])[0].truncated)


class TestIngredients(unittest.TestCase):
    """The list splits into as many sub-columns as a sensible item width allows
    — ~390 px, which is a 773 px column halved and a 1.180 px column in thirds
    [Festlegung 2026-08-22]. It is where the room for the directions comes from."""

    def test_the_split_follows_the_width(self) -> None:
        items = MANY_ITEMS.split("\n")
        for count, expected in ((3, 2), (2, 3)):
            width = rl.slot_width(count)
            cost, columns = rl.ingredient_layout(items, 24, width, rl.sub_columns(count))
            self.assertEqual(columns, expected, f"{count} recipes at {width} px")
            self.assertLess(cost, len(items))

    def test_three_columns_beat_two(self) -> None:
        """The point of the change: at two recipes the same list costs a third."""
        items = MANY_ITEMS.split("\n")
        narrow, _ = rl.ingredient_layout(items, 24, rl.slot_width(3), 1)
        wide, _ = rl.ingredient_layout(items, 24, rl.slot_width(2), 1)
        self.assertLess(wide, narrow)

    def test_a_short_list_stays_in_one(self) -> None:
        """A split that leaves one item alone under the heading reads as a slip."""
        cost, columns = rl.ingredient_layout(["Salz", "Pfeffer", "Muskat"], 28)
        self.assertEqual((cost, columns), (3, 1))

    def test_long_items_stay_in_one_because_splitting_only_rewraps_them(self) -> None:
        items = ["Eine ziemlich lange Zutatenzeile mit vielen Wörtern darin"] * 8
        _cost, columns = rl.ingredient_layout(items, 28)
        self.assertEqual(columns, 1)

    def test_a_flowing_body_keeps_its_list_in_one(self) -> None:
        """One recipe already flows in three 773 px sub-columns; a second
        multi-column nested inside is a layout nobody can predict."""
        items = MANY_ITEMS.split("\n")
        _cost, columns = rl.ingredient_layout(items, 24, rl.slot_width(1), rl.sub_columns(1))
        self.assertEqual(columns, 1)

    def test_no_ingredients_costs_nothing(self) -> None:
        self.assertEqual(rl.ingredient_layout([], 28), (0, 1))


class TestShortening(unittest.TestCase):
    def test_the_ingredients_survive_and_the_directions_give_way(self) -> None:
        """You cannot cook from directions whose ingredient list was cut off."""
        column = rl.build_column(recipe("Suppe", MANY_ITEMS, "Satz. " * 400))
        self.assertTrue(column.truncated)
        self.assertEqual(len(column.ingredients), len(MANY_ITEMS.split("\n")))
        self.assertLess(len(column.directions), 400 * 6)

    def test_the_title_is_never_cut(self) -> None:
        column = rl.build_column(recipe(LONG_TITLE, MANY_ITEMS, "Satz. " * 400))
        self.assertEqual(column.name, LONG_TITLE)

    def test_a_monstrous_ingredient_list_still_leaves_room_for_directions(self) -> None:
        """Otherwise a column shows no directions at all and reads as broken."""
        column = rl.build_column(recipe("Einkauf", "\n".join(["Zutat"] * 80), "Satz. " * 60))
        self.assertTrue(column.directions.strip(), "no directions left")
        self.assertTrue(column.truncated)

    def test_whole_steps_are_kept_rather_than_half_sentences(self) -> None:
        """A recipe that stops after a step reads as shortened; one that stops
        mid-word reads as broken."""
        text = "\n".join(f"Schritt {i} mit etwas Text dahinter." for i in range(60))
        kept, cut = rl.cut_to_lines(text, 60, 10)
        self.assertTrue(cut)
        self.assertEqual(len(kept.split("\n")), 10)
        self.assertTrue(kept.endswith("."))

    def test_no_room_at_all_is_empty_rather_than_a_lone_ellipsis(self) -> None:
        self.assertEqual(rl.cut_to_lines("abc", 60, 0), ("", True))


class TestMarkup(unittest.TestCase):
    """Paprika's directions carry ``**emphasis**`` — in this collection the
    section headings of a multi-part recipe. Raw asterisks on a wall are noise."""

    def test_a_closed_run_becomes_bold(self) -> None:
        self.assertEqual(
            rl.runs("Vor **Blumenkohl** danach"),
            [
                {"text": "Vor ", "bold": False},
                {"text": "Blumenkohl", "bold": True},
                {"text": " danach", "bold": False},
            ],
        )

    def test_two_runs_in_one_line(self) -> None:
        self.assertEqual(
            [run["bold"] for run in rl.runs("**a** und **b**")], [True, False, True]
        )

    def test_an_unclosed_marker_leaves_the_rest_plain(self) -> None:
        """Somebody typed one and never closed it; the recipe must not turn
        bold from there to the end."""
        self.assertEqual([run["bold"] for run in rl.runs("Text **ab hier")], [False, False])

    def test_the_markers_are_gone_from_the_plain_text(self) -> None:
        column = rl.build_column(recipe("R", "Salz", "**Teil eins**\nKochen."))
        self.assertNotIn("*", column.directions)
        self.assertEqual(column.direction_lines[0], [{"text": "Teil eins", "bold": True}])

    def test_a_blank_line_survives_as_a_blank_line(self) -> None:
        column = rl.build_column(recipe("R", "Salz", "eins\n\nzwei"))
        self.assertEqual(len(column.direction_lines), 3)
        self.assertEqual(column.direction_lines[1], [])


class TestServings(unittest.TestCase):
    def test_a_bare_number_gets_its_word(self) -> None:
        """A lone "4" under the title says nothing."""
        column = rl.build_column(recipe(servings="4"), servings_label="{value} Portionen")
        self.assertEqual(column.meta, "4 Portionen")

    def test_what_the_user_typed_is_left_alone(self) -> None:
        column = rl.build_column(recipe(servings="2 Gläser"), servings_label="{value} Portionen")
        self.assertEqual(column.meta, "2 Gläser")

    def test_no_servings_no_meta(self) -> None:
        self.assertEqual(rl.build_column(recipe()).meta, "")


class TestMeta(unittest.TestCase):
    """The line under the title: servings, times, difficulty, each with a mark
    [Festlegung 2026-08-22]."""

    def test_preparation_and_cooking_are_shown_apart(self) -> None:
        """"20 min Vorbereitung, 40 min Kochen" tells a cook something the sum
        does not."""
        parts = rl.build_meta(
            {"servings": "4", "prep_time": "20 min", "cook_time": "40 min"},
            "{value} Portionen",
        )
        self.assertEqual(
            [(p["icon"], p["text"]) for p in parts],
            [("servings", "4 Portionen"), ("prep", "20 min"), ("cook", "40 min")],
        )

    def test_the_total_stands_in_when_neither_half_is_filled_in(self) -> None:
        """The common case in an imported collection."""
        parts = rl.build_meta({"total_time": "1 h"})
        self.assertEqual([(p["icon"], p["text"]) for p in parts], [("time", "1 h")])

    def test_the_total_is_dropped_once_the_halves_are_there(self) -> None:
        parts = rl.build_meta({"prep_time": "20 min", "total_time": "1 h"})
        self.assertNotIn("time", [p["icon"] for p in parts])

    def test_difficulty_comes_last(self) -> None:
        parts = rl.build_meta({"servings": "2", "difficulty": "Mittel"})
        self.assertEqual(parts[-1], {"icon": "difficulty", "text": "Mittel"})

    def test_a_bare_number_gets_its_word_and_anything_else_is_left_alone(self) -> None:
        self.assertEqual(
            rl.build_meta({"servings": "4"}, "{value} Portionen")[0]["text"], "4 Portionen"
        )
        self.assertEqual(
            rl.build_meta({"servings": "2 Gläser"}, "{value} Portionen")[0]["text"], "2 Gläser"
        )

    def test_an_empty_recipe_has_no_meta_line(self) -> None:
        self.assertEqual(rl.build_meta({}), [])

    def test_a_long_meta_line_costs_a_second_line_of_head(self) -> None:
        """It is no longer guaranteed to be one line, and a head measured one
        line short is text quietly missing from the bottom of the column."""
        short = rl.head_lines("Suppe", "4 Portionen", rl.COLUMN_W)
        long = rl.head_lines(
            "Suppe",
            "4 Portionen · 25 Minuten Vorbereitung · 90 Minuten Kochzeit · anspruchsvoll",
            rl.COLUMN_W,
        )
        self.assertEqual(long - short, rl.META_LINE)


class TestColumns(unittest.TestCase):
    def test_three_is_the_ceiling(self) -> None:
        """Belt and braces behind the integration's own clamp — the layout is
        where a fourth column would actually break something."""
        self.assertEqual(len(rl.build_columns([recipe(f"R{i}") for i in range(5)])), 3)

    def test_no_selection_is_no_columns_and_not_a_failure(self) -> None:
        self.assertEqual(rl.build_columns([]), [])

    def test_the_meta_line_joins_what_is_there(self) -> None:
        self.assertEqual(
            rl.build_column(recipe(servings="4 Portionen", total_time="1 h")).meta,
            "4 Portionen · 1 h",
        )
        self.assertEqual(rl.build_column(recipe(servings="4")).meta, "4")
        self.assertEqual(rl.build_column(recipe()).meta, "")
        self.assertEqual(rl.build_column(recipe()).meta_parts, [])

    def test_the_ingredients_reach_the_template_as_source_lines(self) -> None:
        """The template bullets them one by one, and a blank line is a group
        break the height model already paid for."""
        column = rl.build_column(recipe("R", "Salz\n\nPfeffer", "Kochen."))
        self.assertEqual(column.ingredients, ["Salz", "", "Pfeffer"])


if __name__ == "__main__":
    unittest.main()
