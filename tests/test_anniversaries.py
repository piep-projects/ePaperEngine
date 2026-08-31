"""The write-back rule (P42) — what an entry should read, before anything is written.

The dangerous part of this feature is not the HTTP. It is deciding what to put
in somebody's real calendar, and getting that wrong overwrites entries nobody
has a copy of. So the decision is a pure function and this file is where it is
held to account.

The load-bearing test is ``TestAgainstTheRealCatalogue``: the suffix pattern is
*derived* from the wall catalogue, and this proves the derivation still fits the
strings that actually ship — in both languages. If it ever stops fitting, the
sync would no longer recognise its own previous suffix and would append a second
one, growing the title a little every single day.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest
from datetime import date

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "epaperengine"))

import anniversaries as an  # noqa: E402

DE = "— {years} Jahre"
EN = "— {years} years"
TODAY = date(2026, 8, 31)


class TestYearInTitle(unittest.TestCase):
    def test_a_trailing_bracket(self) -> None:
        self.assertEqual(an.year_in_title("Erika Müller (1946)"), 1946)

    def test_a_bracket_with_a_suffix_behind_it(self) -> None:
        """After the first write-back the year is no longer at the end."""
        self.assertEqual(an.year_in_title("Erika Müller (1946) — 80 Jahre"), 1946)

    def test_the_last_bracket_wins(self) -> None:
        self.assertEqual(
            an.year_in_title("Hochzeit (Standesamt) Ulla & Christian (2006)"), 2006
        )

    def test_a_note_in_brackets_is_not_a_year(self) -> None:
        self.assertIsNone(an.year_in_title("Erika Müller (Tante)"))
        self.assertIsNone(an.year_in_title("Erika Müller (42)"))

    def test_no_bracket_at_all(self) -> None:
        self.assertIsNone(an.year_in_title("Namenstag Christian"))


class TestWantedTitle(unittest.TestCase):
    def test_a_fresh_entry_gets_its_count(self) -> None:
        self.assertEqual(
            an.wanted_title("Erika Müller (1946)", TODAY, DE),
            "Erika Müller (1946) — 80 Jahre",
        )

    def test_last_years_count_is_replaced_not_repeated(self) -> None:
        self.assertEqual(
            an.wanted_title("Erika Müller (1946) — 79 Jahre", TODAY, DE),
            "Erika Müller (1946) — 80 Jahre",
        )

    def test_it_is_idempotent(self) -> None:
        """A daily run must do nothing on a day when nothing changed."""
        once = an.wanted_title("Erika Müller (1946)", TODAY, DE)
        self.assertEqual(an.wanted_title(once, TODAY, DE), once)
        self.assertEqual(an.wanted_title(an.wanted_title(once, TODAY, DE), TODAY, DE), once)

    def test_an_entry_without_a_year_is_left_alone(self) -> None:
        self.assertEqual(
            an.wanted_title("Namenstag Christian", TODAY, DE), "Namenstag Christian"
        )

    def test_a_year_in_the_future_is_a_typo_not_an_anniversary(self) -> None:
        """Better an untouched title than "— -4 Jahre" in a real calendar."""
        self.assertEqual(an.wanted_title("Jubiläum (2030)", TODAY, DE), "Jubiläum (2030)")

    def test_it_works_for_an_anniversary_that_is_not_a_birthday(self) -> None:
        self.assertEqual(
            an.wanted_title("Hochzeit Ulla & Christian (2006)", TODAY, DE),
            "Hochzeit Ulla & Christian (2006) — 20 Jahre",
        )

    def test_the_count_follows_the_calendar_year_of_the_run(self) -> None:
        self.assertEqual(
            an.wanted_title("Erika Müller (1946)", date(2027, 1, 4), DE),
            "Erika Müller (1946) — 81 Jahre",
        )


class TestSuffixPattern(unittest.TestCase):
    def test_it_tolerates_whitespace_a_calendar_app_normalised(self) -> None:
        p = an.suffix_pattern(DE)
        self.assertEqual(an.strip_suffix("Erika (1946)  —   80   Jahre", p), "Erika (1946)")

    def test_it_does_not_eat_a_name_that_merely_ends_in_a_number(self) -> None:
        p = an.suffix_pattern(DE)
        self.assertEqual(an.strip_suffix("Werkstatt 80", p), "Werkstatt 80")


class TestPlan(unittest.TestCase):
    def test_it_reports_what_it_would_not_touch(self) -> None:
        changes = an.plan(
            [("a", "Erika Müller (1946)"), ("b", "Namenstag Christian")], TODAY, DE
        )
        self.assertEqual([c.changed for c in changes], [True, False])


class TestAgainstTheRealCatalogue(unittest.TestCase):
    """The guard. Both catalogues ship; both must round-trip."""

    def _catalogue(self, lang: str) -> str:
        path = REPO_ROOT / "addon-epaperengine" / "templates" / "i18n" / f"{lang}.json"
        return json.loads(path.read_text(encoding="utf-8"))["calendar.years"]

    def test_the_shipped_strings_are_the_ones_this_module_assumes(self) -> None:
        self.assertEqual(self._catalogue("de"), DE)
        self.assertEqual(self._catalogue("en"), EN)

    def test_every_language_recognises_its_own_suffix(self) -> None:
        """Derived from the catalogue, so a reworded string keeps working —
        but only if it still contains {years}. That is what this proves."""
        for lang in ("de", "en"):
            with self.subTest(lang=lang):
                text = self._catalogue(lang)
                once = an.wanted_title("Erika Müller (1946)", TODAY, text)
                self.assertIn("80", once)
                self.assertEqual(an.wanted_title(once, TODAY, text), once,
                                 "the sync would append a second suffix every day")

    def test_a_reworded_catalogue_still_round_trips(self) -> None:
        """The reason the pattern is derived instead of written down twice."""
        for text in ("({years} Jahre)", "· {years} J.", "{years} years old"):
            with self.subTest(text=text):
                once = an.wanted_title("Erika Müller (1946)", TODAY, text)
                self.assertEqual(an.wanted_title(once, TODAY, text), once)


if __name__ == "__main__":
    unittest.main()
