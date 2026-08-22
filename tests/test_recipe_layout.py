"""How a recipe is fitted into its column (FSD §7, §8.2).

The interesting cases here are the ones nobody would catch by looking at the
wall: the step *between* two type sizes, and what exactly gets thrown away when
a recipe is longer than the panel can carry at 24 px. FSD §8.2 says "in the
example set every second recipe" is over that line — so truncation is the
normal case, not the exotic one, and it deserves a test rather than a glance.

Pure stdlib, like ``test_outage.py``: ``recipe_layout.py`` carries no Pillow and
no aiohttp precisely so this runs where nothing is installed.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import recipe_layout  # noqa: E402


def recipe(name: str = "Test", ingredients: str = "", directions: str = "", **extra):
    return {"name": name, "ingredients": ingredients, "directions": directions, **extra}


class TestTypeSize(unittest.TestCase):
    def test_a_short_recipe_gets_the_largest_size(self) -> None:
        column = recipe_layout.build_column(recipe(directions="x" * 100))
        self.assertEqual(column.font_px, 28)
        self.assertFalse(column.truncated)

    def test_the_steps_are_the_ones_the_panel_was_measured_with(self) -> None:
        """28 → 26 → 24 and nothing in between (FSD §7, Festlegung 2026-08-20)."""
        self.assertEqual([size for size, _ in recipe_layout.STEPS], [28, 26, 24])

    def test_each_step_holds_up_to_its_budget_and_not_one_character_more(self) -> None:
        for size, budget in recipe_layout.STEPS:
            self.assertEqual(recipe_layout.font_for(budget), size, f"{size} px at {budget}")
        self.assertEqual(recipe_layout.font_for(951), 26)
        self.assertEqual(recipe_layout.font_for(1151), 24)

    def test_below_the_floor_it_stays_at_24(self) -> None:
        """24 px is the floor — colour stops carrying below it (FSD §7)."""
        column = recipe_layout.build_column(recipe(directions="x" * 4000))
        self.assertEqual(column.font_px, 24)

    def test_one_long_recipe_does_not_shrink_the_short_one_beside_it(self) -> None:
        """The whole reason the step is decided per column (FSD §8.2)."""
        columns = recipe_layout.build_columns(
            [recipe("Short", directions="x" * 200), recipe("Long", directions="x" * 1300)]
        )
        self.assertEqual([column.font_px for column in columns], [28, 24])


class TestShortening(unittest.TestCase):
    def test_nothing_is_cut_while_it_fits(self) -> None:
        column = recipe_layout.build_column(
            recipe(ingredients="a" * 300, directions="b" * 900)
        )
        self.assertFalse(column.truncated)
        self.assertEqual(len(column.directions), 900)

    def test_the_ingredients_survive_and_the_directions_give_way(self) -> None:
        """You cannot cook from directions whose ingredient list was cut off."""
        column = recipe_layout.build_column(
            recipe(ingredients="a" * 400, directions="b" * 2000)
        )
        self.assertTrue(column.truncated)
        self.assertEqual(column.ingredients, "a" * 400)
        self.assertLess(len(column.directions), 2000)

    def test_the_title_is_never_cut(self) -> None:
        name = "A recipe with a deliberately long name"
        column = recipe_layout.build_column(recipe(name, directions="x" * 3000))
        self.assertEqual(column.name, name)

    def test_a_monstrous_ingredient_list_still_leaves_room_for_directions(self) -> None:
        """Otherwise a column shows no directions at all and reads as broken."""
        column = recipe_layout.build_column(
            recipe(ingredients="a " * 1500, directions="b " * 800)
        )
        self.assertTrue(column.directions.strip(), "no directions left")
        self.assertTrue(column.truncated)

    def test_the_column_stays_inside_the_floor_budget(self) -> None:
        column = recipe_layout.build_column(
            recipe("Name", ingredients="a " * 900, directions="b " * 900)
        )
        total = recipe_layout.length(column.name, column.ingredients, column.directions)
        self.assertLessEqual(total, recipe_layout.FLOOR_BUDGET)

    def test_shortening_is_marked_so_it_is_visible_on_the_wall(self) -> None:
        """FSD §8.2: "wird gekürzt und das sichtbar vermerkt"."""
        column = recipe_layout.build_column(recipe(directions="x" * 3000))
        self.assertTrue(column.truncated)
        self.assertTrue(column.directions.endswith(recipe_layout.ELLIPSIS))


class TestShorten(unittest.TestCase):
    def test_it_cuts_at_a_word_boundary(self) -> None:
        text, cut = recipe_layout.shorten("alpha beta gamma delta", 14)
        self.assertTrue(cut)
        self.assertFalse(text.replace(recipe_layout.ELLIPSIS, "").endswith(" "))
        self.assertLessEqual(len(text), 14)

    def test_a_single_long_word_does_not_empty_the_column(self) -> None:
        text, _ = recipe_layout.shorten("a" * 200, 50)
        self.assertGreater(len(text), 40)

    def test_no_room_means_nothing_rather_than_a_lone_ellipsis(self) -> None:
        self.assertEqual(recipe_layout.shorten("abcdef", 1), ("", True))


class TestColumns(unittest.TestCase):
    def test_three_is_the_ceiling(self) -> None:
        """Belt and braces behind the integration's own clamp — the layout is
        where a fourth column would actually break something."""
        columns = recipe_layout.build_columns([recipe(f"R{i}") for i in range(5)])
        self.assertEqual(len(columns), 3)

    def test_no_selection_is_no_columns_and_not_a_failure(self) -> None:
        self.assertEqual(recipe_layout.build_columns([]), [])

    def test_the_meta_line_joins_what_is_there(self) -> None:
        self.assertEqual(
            recipe_layout.build_column(recipe(servings="4", total_time="1 h")).meta,
            "4 · 1 h",
        )
        self.assertEqual(recipe_layout.build_column(recipe(servings="4")).meta, "4")
        self.assertEqual(recipe_layout.build_column(recipe()).meta, "")


if __name__ == "__main__":
    unittest.main()
