"""Translation guard (i18n concept §12).

English is the base language; German is a fully maintained translation, not a
best-effort one. Nothing but a test keeps that true — a missing key silently
falls back to English, a missing placeholder silently renders a gap, and neither
shows up until someone switches Home Assistant to German.

Pure stdlib on purpose: no ``homeassistant`` import, so CI needs no HA install.
``VIEWS`` and the priority candidates are read out of ``const.py`` with ``ast``
for the same reason.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"
HA_CATALOGS = COMPONENT / "translations"
FRONTEND_CATALOGS = COMPONENT / "frontend_i18n"

BASE_LANG = "en"
LANGUAGES = ("en", "de")

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(obj: object, prefix: str = "") -> dict[str, str]:
    """Flatten a nested catalog to ``a.b.c`` → value."""
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        out[prefix] = str(obj)
    return out


def _const_tuple(name: str) -> tuple[str, ...]:
    """Read a module-level tuple of string literals out of ``const.py``."""
    tree = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
    literals = {
        node.target.id: node.value
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    value = literals[name]
    resolved: list[str] = []
    for element in value.elts:  # type: ignore[attr-defined]
        if isinstance(element, ast.Constant):
            resolved.append(str(element.value))
        elif isinstance(element, ast.Name):
            resolved.append(str(literals[element.id].value))  # type: ignore[attr-defined]
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unsupported element in {name}: {ast.dump(element)}")
    return tuple(resolved)


class TestHomeAssistantCatalogs(unittest.TestCase):
    """``strings.json`` is the source; ``translations/en.json`` mirrors it."""

    def test_en_mirrors_strings(self) -> None:
        source = _flatten(_load(COMPONENT / "strings.json"))
        mirror = _flatten(_load(HA_CATALOGS / "en.json"))
        self.assertEqual(source.keys(), mirror.keys())
        for key, value in source.items():
            if mirror[key].startswith("[%key:"):
                continue
            self.assertEqual(value, mirror[key], f"{key} differs from strings.json")

    def test_every_language_is_complete(self) -> None:
        base = _flatten(_load(HA_CATALOGS / f"{BASE_LANG}.json"))
        for lang in LANGUAGES:
            catalog = _flatten(_load(HA_CATALOGS / f"{lang}.json"))
            self.assertEqual(
                base.keys(), catalog.keys(), f"key sets differ: {BASE_LANG} vs {lang}"
            )
            for key, value in catalog.items():
                self.assertTrue(value.strip(), f"{lang}: {key} is empty")


class TestFrontendCatalogs(unittest.TestCase):
    """Shared card/panel catalogs — one flat JSON file per language."""

    def setUp(self) -> None:
        self.catalogs = {
            lang: _load(FRONTEND_CATALOGS / f"{lang}.json") for lang in LANGUAGES
        }
        self.base = self.catalogs[BASE_LANG]

    def test_flat_keys(self) -> None:
        for lang, catalog in self.catalogs.items():
            for key, value in catalog.items():
                self.assertIsInstance(value, str, f"{lang}: {key} is not a string")
                self.assertTrue(value.strip(), f"{lang}: {key} is empty")

    def test_every_language_is_complete(self) -> None:
        for lang, catalog in self.catalogs.items():
            self.assertEqual(
                self.base.keys(),
                catalog.keys(),
                f"key sets differ: {BASE_LANG} vs {lang}",
            )

    def test_placeholders_match(self) -> None:
        """``{n}`` in en but not in de renders an empty spot at runtime."""
        for lang, catalog in self.catalogs.items():
            for key, value in self.base.items():
                self.assertEqual(
                    set(_PLACEHOLDER.findall(value)),
                    set(_PLACEHOLDER.findall(catalog[key])),
                    f"{lang}: placeholders of {key} differ from {BASE_LANG}",
                )

    def test_view_tokens_have_labels(self) -> None:
        for view in _const_tuple("VIEWS"):
            self.assertIn(f"view.{view}", self.base, f"no label for view {view!r}")

    def test_priority_candidates_have_labels(self) -> None:
        views = set(_const_tuple("VIEWS"))
        for candidate in _const_tuple("DEFAULT_PRIORITY"):
            key = f"view.{candidate}" if candidate in views else f"candidate.{candidate}"
            self.assertIn(key, self.base, f"no label for candidate {candidate!r}")


if __name__ == "__main__":
    unittest.main()
