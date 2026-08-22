"""Guards for the two front-end files that no linter here would catch.

Both build their markup with **template literals**, and a backtick inside one
ends it. What follows is then parsed as a *tagged template call* — syntactically
valid, so ``node --check`` stays silent, and it throws at runtime the first time
the method runs.

That happened, and it cost an afternoon: a CSS comment written in the same
double-backtick style as the Python docstrings around it —

    /* ``.btn`` is for the one control … */

— sat inside the stylesheet of ``_build()``. The module imported fine, the
element registered fine, every page function returned fine; only ``_build()``
threw, the shadow root stayed empty, and the panel was a **white page** with the
sidebar entry present and no error anywhere on the server. Every layer measured
green: the panel was registered, the file served with the right MIME type, the
WebSocket commands answered.

Pure stdlib on purpose: no node, no jsdom, so this runs where nothing is
installed — the same trade the other guards make.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"

FILES = (
    COMPONENT / "panel" / "epaperengine-panel.js",
    COMPONENT / "epaperengine-card.js",
)


def styles(source: str) -> list[str]:
    """Every ``<style>…</style>`` block — they are written inside literals."""
    return re.findall(r"<style>(.*?)</style>", source, re.S)


class TestNoBackticksInMarkup(unittest.TestCase):
    def test_the_stylesheets_carry_no_backtick(self) -> None:
        for path in FILES:
            source = path.read_text(encoding="utf-8")
            blocks = styles(source)
            self.assertTrue(blocks, f"{path.name}: no <style> block found — moved?")
            for block in blocks:
                for number, line in enumerate(block.splitlines(), start=1):
                    self.assertNotIn(
                        "`",
                        line,
                        f"{path.name}: backtick in the stylesheet (line {number} of the "
                        f"block) ends the template literal: {line.strip()!r}",
                    )

    def test_the_build_method_holds_exactly_one_literal(self) -> None:
        """Two backticks in ``_build()``: the one that opens the markup and the
        one that closes it. Any other number means the literal was broken open
        somewhere in between."""
        source = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        start = source.index("  _build() {")
        end = source.index("this._built = true;", start)
        body = source[start:end]
        self.assertEqual(
            body.count("`"),
            2,
            "_build() should hold exactly one template literal — a stray backtick "
            "turns the rest into a tagged template call that throws at runtime",
        )


class TestElementRegistration(unittest.TestCase):
    """The panel is dead without this line, and it is easy to lose in an edit."""

    def test_the_custom_element_is_defined(self) -> None:
        source = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        self.assertIn('customElements.define("epaperengine-panel"', source)
        # The guard matters too: a name can only be registered once per page, so
        # defining it unconditionally throws on a second module load.
        self.assertIn('customElements.get("epaperengine-panel")', source)

    def test_the_tag_matches_what_the_integration_registers(self) -> None:
        const = (COMPONENT / "const.py").read_text(encoding="utf-8")
        name = re.search(r'PANEL_CUSTOM_NAME:\s*Final\s*=\s*"([^"]+)"', const)
        self.assertIsNotNone(name, "PANEL_CUSTOM_NAME not found in const.py")
        source = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        self.assertIn(f'customElements.define("{name.group(1)}"', source)


if __name__ == "__main__":
    unittest.main()
