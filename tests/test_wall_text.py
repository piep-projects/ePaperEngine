"""The language the wall speaks (FSD §3.0a, Festlegung P9 2026-08-21).

Two things are guarded here. That the *resolution* is right — region tags
dropped, unknown languages falling back to English rather than rendering keys —
and that the catalogs themselves stay congruent, which is the same guard
``tests/test_translations.py`` puts on the Home Assistant and frontend catalogs.
Without it the non-base language drifts silently, and the only one who notices
is the German user standing in front of the wall.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest
from datetime import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import wall_text  # noqa: E402

CATALOGS = REPO_ROOT / "addon-epaperengine" / "templates" / "i18n"
LANGUAGES = ("en", "de")
BASE_LANG = "en"

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _load(lang: str) -> dict[str, str]:
    return json.loads((CATALOGS / f"{lang}.json").read_text(encoding="utf-8"))


class TestCatalogs(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogs = {lang: _load(lang) for lang in LANGUAGES}
        self.base = self.catalogs[BASE_LANG]

    def test_flat_and_filled(self) -> None:
        for lang, catalog in self.catalogs.items():
            for key, value in catalog.items():
                self.assertIsInstance(value, str, f"{lang}: {key} is not a string")
                self.assertTrue(value.strip(), f"{lang}: {key} is empty")

    def test_every_language_is_complete(self) -> None:
        for lang, catalog in self.catalogs.items():
            self.assertEqual(
                self.base.keys(), catalog.keys(), f"key sets differ: {BASE_LANG} vs {lang}"
            )

    def test_placeholders_match(self) -> None:
        for lang, catalog in self.catalogs.items():
            for key, value in self.base.items():
                self.assertEqual(
                    set(_PLACEHOLDER.findall(value)),
                    set(_PLACEHOLDER.findall(catalog[key])),
                    f"{lang}: placeholders of {key} differ from {BASE_LANG}",
                )

    def test_every_language_can_format_a_date(self) -> None:
        """``format.datetime`` is a strftime pattern, not prose. A typo in it
        would only show up as a literal ``%Q`` on the wall."""
        moment = datetime(2026, 8, 21, 15, 4)
        for lang in LANGUAGES:
            rendered = wall_text.WallText(lang).moment(moment)
            self.assertNotIn("%", rendered, f"{lang}: unresolved strftime directive")
            self.assertIn("2026", rendered, f"{lang}: no year in the timestamp")
            self.assertIn("15:04", rendered, f"{lang}: no time in the timestamp")

    def test_every_view_has_the_keys_its_template_uses(self) -> None:
        """Read out of the templates rather than listed here — a hand-kept list
        drifts the moment somebody edits a page, which is the failure this test
        exists to catch. Every template is scanned, so a new view brings its
        strings with it or this goes red."""
        templates = sorted(
            (REPO_ROOT / "addon-epaperengine" / "templates").glob("*.html.j2")
        )
        self.assertTrue(templates, "no wall templates found — moved?")
        found_any = False
        for path in templates:
            used = set(
                re.findall(r"""t\(\s*["']([a-z0-9_.]+)["']""", path.read_text(encoding="utf-8"))
            )
            found_any = found_any or bool(used)
            for key in used:
                self.assertIn(key, self.base, f"{path.name} uses {key!r}, en.json has not")
        self.assertTrue(found_any, "no catalog keys found in any template — parser broken?")


class TestLanguageResolution(unittest.TestCase):
    def test_a_region_tag_is_dropped(self) -> None:
        self.assertEqual(wall_text.normalise("de-DE"), "de")

    def test_an_unknown_language_falls_back_to_the_base(self) -> None:
        for token in ("fr", "pt-BR", "", None, "  "):
            self.assertEqual(wall_text.normalise(token), "en", f"{token!r}")

    def test_german_is_actually_german(self) -> None:
        """Catches the failure where the catalog exists but never gets loaded —
        the whole thing would silently answer in English."""
        english = wall_text.WallText("en")("error.headline")
        german = wall_text.WallText("de-DE")("error.headline")
        self.assertNotEqual(english, german)
        self.assertIn("nicht", german)


class TestLookup(unittest.TestCase):
    """Deliberately forgiving where Jinja is strict: the one page that must
    never fail to render is the page that says everything else failed."""

    def test_placeholders_are_filled(self) -> None:
        text = wall_text.WallText("en")
        self.assertEqual(text("error.since", at="15:04"), "since 15:04")

    def test_an_unknown_key_renders_as_itself(self) -> None:
        self.assertEqual(wall_text.WallText("en")("no.such.key"), "no.such.key")

    def test_a_missing_placeholder_does_not_raise(self) -> None:
        self.assertIn("{at}", wall_text.WallText("en")("error.since"))

    def test_english_is_the_floor_under_every_language(self) -> None:
        """Belt and braces behind the catalog guard: the language catalog is
        layered *over* the base, not used instead of it, so a key added to en
        and forgotten in de renders English rather than the raw key."""
        for lang in ("de", "fr"):  # fr has no catalog at all
            strings = wall_text.WallText(lang)._strings  # noqa: SLF001
            self.assertLessEqual(
                set(_load(BASE_LANG)), set(strings), f"{lang}: base keys missing"
            )


if __name__ == "__main__":
    unittest.main()
