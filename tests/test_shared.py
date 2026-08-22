"""The layout module exists twice, and it must be the same file (publish.py).

``recipe_layout.py`` decides how a recipe is fitted into its column. The add-on
**renders** with it; the integration **forecasts** with it, so the panel can say
"this one will be shortened" before somebody picks it and waits a minute for the
wall to answer.

They cannot import from one another — an add-on is a container, an integration
is a package inside Home Assistant — so the file is copied by
``scripts/publish.py`` and by ``scripts/deploy.py``. This test is what makes the
copy trustworthy: it fails the moment somebody edits one of the two by hand.

The alternative was tried and did not survive a day. A coarse re-implementation
in the integration told the user that a recipe would be shortened while the wall
was rendering it in full, because it did not know that the ingredient list
splits into sub-columns.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

SHARED = (
    (
        REPO_ROOT / "addon-epaperengine" / "recipe_layout.py",
        REPO_ROOT / "custom_components" / "epaperengine" / "recipe_layout.py",
    ),
)


class TestSharedModules(unittest.TestCase):
    def test_the_copies_are_identical(self) -> None:
        for origin, copy in SHARED:
            self.assertTrue(origin.exists(), f"missing original: {origin}")
            self.assertTrue(
                copy.exists(), f"missing copy: {copy} — run scripts/publish.py"
            )
            self.assertEqual(
                origin.read_bytes(),
                copy.read_bytes(),
                f"{copy.name} has drifted from {origin} — run scripts/publish.py",
            )

    def test_the_shared_module_needs_nothing_a_hass_install_lacks(self) -> None:
        """It travels into Home Assistant, where ``requirements`` is empty on
        purpose (manifest.json). Standard library only."""
        allowed = {"math", "dataclasses", "typing", "__future__"}
        for origin, _copy in SHARED:
            tree = ast.parse(origin.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in names:
                    self.assertIn(name, allowed, f"{origin.name} imports {name}")


if __name__ == "__main__":
    unittest.main()
