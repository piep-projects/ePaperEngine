"""Cooking a recipe for a different number of people (FSD §8.2, 2026-08-22).

Arithmetic that ends up in somebody's dinner, over free text somebody else
typed. Every rule below is a decision, and each of them is here because getting
it wrong is invisible until the cake does not rise:

* only the **leading** quantity of a line moves — "8 Saiblingsfilets à 60 g"
  doubles the fillets, not the sixty grams;
* a line with no quantity is left alone — that is "Salz", and 176 of this
  collection's 758 ingredient lines are that kind;
* **no rounding**, one decimal place [Festlegung Wolfgang]: 187,5 g is what the
  arithmetic says and the cook decides what to do about the half gram;
* the **directions are never touched**. A quantity repeated there is a mistake
  in the recipe, to be fixed in Paprika.

Pure stdlib with the usual stubs — ``scaling.py`` imports nothing but ``re``,
but it lives in the integration package, whose ``__init__`` pulls in half of
Home Assistant.
"""

from __future__ import annotations

import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

if "epaperengine" not in sys.modules:
    package = types.ModuleType("epaperengine")
    package.__path__ = [str(REPO_ROOT / "custom_components" / "epaperengine")]  # type: ignore[attr-defined]
    sys.modules["epaperengine"] = package

from epaperengine import scaling  # noqa: E402


class TestNumbers(unittest.TestCase):
    def test_the_forms_people_actually_type(self) -> None:
        for text, value in (
            ("2", 2.0), ("1,5", 1.5), ("1.5", 1.5), ("1/2", 0.5), ("½", 0.5), ("¾", 0.75),
        ):
            self.assertAlmostEqual(scaling.parse_number(text), value, msg=text)

    def test_what_is_not_a_number(self) -> None:
        for text in ("", "Salz", "etwas", "n/a", "1/0"):
            self.assertIsNone(scaling.parse_number(text), text)

    def test_one_decimal_place_and_no_trailing_zero(self) -> None:
        self.assertEqual(scaling.format_number(187.5), "187,5")
        self.assertEqual(scaling.format_number(200.0), "200")
        self.assertEqual(scaling.format_number(0.75), "0,8")
        self.assertEqual(scaling.format_number(1000.0), "1000", "a plain integer lost a zero")

    def test_the_recipe_s_own_decimal_separator_is_kept(self) -> None:
        self.assertEqual(scaling.scale_line("1.5 kg Mehl", 2), "3 kg Mehl")
        self.assertEqual(scaling.scale_line("0,5 l Sahne", 3), "1,5 l Sahne")


class TestLines(unittest.TestCase):
    def test_a_plain_quantity(self) -> None:
        self.assertEqual(scaling.scale_line("125 g Butter", 1.5), "187,5 g Butter")

    def test_a_countable_without_a_unit(self) -> None:
        """"1 Sellerie" is 76 % of the reason this works at all."""
        self.assertEqual(scaling.scale_line("6 Schalotten", 2), "12 Schalotten")

    def test_only_the_leading_quantity_moves(self) -> None:
        """The ``à 60 g`` is per piece."""
        self.assertEqual(
            scaling.scale_line("8 Saiblingsfilets à 60 g", 1.5),
            "12 Saiblingsfilets à 60 g",
        )

    def test_a_line_without_a_quantity_is_untouched(self) -> None:
        for line in ("Salz", "Pfeffer", "Salz, Pfeffer", "Etwas Olivenöl", ""):
            self.assertEqual(scaling.scale_line(line, 2), line)

    def test_a_range_scales_at_both_ends(self) -> None:
        self.assertEqual(scaling.scale_line("2-3 Zehen Knoblauch", 2), "4-6 Zehen Knoblauch")
        self.assertEqual(scaling.scale_line("2 bis 3 Eier", 2), "4 bis 6 Eier")

    def test_a_fraction_becomes_a_decimal(self) -> None:
        self.assertEqual(scaling.scale_line("1/2 TL Zimt", 3), "1,5 TL Zimt")
        self.assertEqual(scaling.scale_line("½ Vanilleschote", 2), "1 Vanilleschote")

    def test_an_approximation_keeps_its_word(self) -> None:
        self.assertEqual(scaling.scale_line("ca. 200 ml Brühe", 2), "ca. 400 ml Brühe")

    def test_a_dash_that_is_not_a_range_stays_put(self) -> None:
        self.assertEqual(scaling.scale_line("1 - Blumenkohl", 2), "2 - Blumenkohl")

    def test_factor_one_changes_nothing(self) -> None:
        self.assertEqual(scaling.scale_line("125 g Butter", 1), "125 g Butter")


class TestRecipe(unittest.TestCase):
    RECIPE = {
        "uid": "u1",
        "name": "Suppe",
        "servings": "4",
        "ingredients": "500 g Kürbis\n2 Zwiebeln\nSalz\n1/2 TL Curry",
        "directions": "Alles mit 500 g Kürbis kochen.",
    }

    def test_scaling_up(self) -> None:
        out = scaling.scaled(self.RECIPE, 6)
        self.assertEqual(
            out["ingredients"], "750 g Kürbis\n3 Zwiebeln\nSalz\n0,8 TL Curry"
        )
        self.assertEqual(out["servings"], "6")
        self.assertEqual(out["scaled_from"], "4")

    def test_the_directions_are_never_touched(self) -> None:
        """A quantity repeated there is a mistake in the recipe, and it belongs
        fixed in Paprika — not papered over here [Festlegung]."""
        self.assertEqual(scaling.scaled(self.RECIPE, 8)["directions"], self.RECIPE["directions"])

    def test_nothing_happens_without_a_target(self) -> None:
        for target in (None, 0, 4):
            self.assertEqual(
                scaling.scaled(self.RECIPE, target)["ingredients"], self.RECIPE["ingredients"]
            )

    def test_a_recipe_without_a_serving_count_cannot_be_scaled(self) -> None:
        """Eight of this collection's 53 have an empty field. Guessing four
        would silently produce wrong quantities."""
        recipe = {**self.RECIPE, "servings": ""}
        self.assertIsNone(scaling.base_servings(recipe))
        self.assertEqual(scaling.scaled(recipe, 8)["ingredients"], recipe["ingredients"])

    def test_a_text_serving_count_is_no_base_either(self) -> None:
        recipe = {**self.RECIPE, "servings": "1 Blech"}
        self.assertEqual(scaling.scaled(recipe, 2)["ingredients"], recipe["ingredients"])

    def test_the_original_is_not_modified(self) -> None:
        before = dict(self.RECIPE)
        scaling.scaled(self.RECIPE, 12)
        self.assertEqual(self.RECIPE, before)

    def test_scaling_down_works_too(self) -> None:
        out = scaling.scaled(self.RECIPE, 2)
        self.assertEqual(out["ingredients"].split("\n")[0], "250 g Kürbis")


if __name__ == "__main__":
    unittest.main()
