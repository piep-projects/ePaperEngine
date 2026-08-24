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

import ast
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


class TestWebSocketCommands(unittest.TestCase):
    """Every command the front-ends call has to exist and be registered.

    The one failure mode nothing else here catches: a command string is written
    twice — once in ``const.py`` and once in a template literal — and the two
    drift. The panel then sends ``epaperengine/calendar/snyc``, Home Assistant
    answers ``unknown_command``, and the only trace is a red note in the panel.

    Pure stdlib again: ``ast`` over ``websocket_api.py``, a regular expression
    over the two JavaScript files. No Home Assistant needed.
    """

    def setUp(self) -> None:
        self.commands = _ws_constants()
        self.registered, self.handlers = _ws_registered()

    def test_the_front_ends_only_call_known_commands(self) -> None:
        for path in FILES:
            source = path.read_text(encoding="utf-8")
            for command in re.findall(r'type:\s*"(epaperengine/[a-z_/]+)"', source):
                self.assertIn(
                    command,
                    self.commands.values(),
                    f"{path.name}: {command!r} is not defined in const.py",
                )

    def test_every_handler_is_registered(self) -> None:
        """A decorated handler that nobody lists in ``async_register`` never
        answers — the decorator alone does not register it."""
        for const_name, function in self.handlers.items():
            self.assertIn(
                function,
                self.registered,
                f"{function}() carries {const_name} but is missing from async_register",
            )

    def test_every_command_has_a_handler(self) -> None:
        for const_name in self.commands:
            self.assertIn(
                const_name,
                self.handlers,
                f"{const_name} is defined but no handler declares it",
            )


class TestWayBackToTheDashboard(unittest.TestCase):
    """The panel's one escape hatch, and the two storage keys it hangs on.

    A custom panel fills the whole frame. With the Home Assistant sidebar
    collapsed — which is what a narrow window or a tablet gives you — there is
    nothing left to click but the browser's Back, and that is unreliable here:
    the panel can also be entered straight from the sidebar entry, where there is
    no "back" to speak of. So the header carries a ``Dashboard`` button, and the
    card writes down where it should lead.

    The keys are written in **two files**, plain strings on both sides — exactly
    the drift this module was built for. If they part ways nothing errors: the
    button silently lands on the default dashboard instead of the one the visitor
    came from, and no log anywhere says so.
    """

    PANEL, CARD = FILES

    def _keys(self, path: pathlib.Path) -> set[str]:
        return set(re.findall(r'"(epaperengine:[a-z]+)"', path.read_text(encoding="utf-8")))

    def test_the_header_carries_the_button(self) -> None:
        source = self.PANEL.read_text(encoding="utf-8")
        self.assertIn('id="to-dashboard"', source, "no way out of the panel")
        self.assertIn('on("#to-dashboard"', source, "the button is drawn but never wired")

    def test_the_label_is_translated(self) -> None:
        """Not humanizeKey() — that would turn the key into "Dashboard title"."""
        catalogs = COMPONENT / "frontend_i18n"
        for key in ("panel.head.dashboard", "panel.head.dashboard_title"):
            for catalog in sorted(catalogs.glob("*.json")):
                self.assertIn(
                    key,
                    catalog.read_text(encoding="utf-8"),
                    f"{catalog.name}: {key} missing",
                )

    def test_both_files_use_the_same_storage_keys(self) -> None:
        panel, card = self._keys(self.PANEL), self._keys(self.CARD)
        self.assertEqual(
            panel,
            card,
            "panel and card disagree about the return-path keys",
        )
        self.assertEqual(len(panel), 2, f"expected two keys, found {sorted(panel)}")

    def test_the_card_writes_both(self) -> None:
        """One per route: the session key for the trip that started at the gear,
        the local one for the sidebar route, where no trip was ever started."""
        source = self.CARD.read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem(RETURN_KEY", source)
        self.assertIn("localStorage.setItem(DASHBOARD_KEY", source)

    def test_every_storage_access_is_guarded(self) -> None:
        """A browser in private mode throws on the *getter* too, not just on the
        write — an unguarded read takes the whole panel down with it."""
        for path in FILES:
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"(session|local)Storage\.(get|set)Item", source):
                before = source[max(0, match.start() - 200) : match.start()]
                self.assertIn(
                    "try {",
                    before,
                    f"{path.name}: unguarded {match.group(0)} at offset {match.start()}",
                )


def _ws_constants() -> dict[str, str]:
    """``{"WS_STATUS": "epaperengine/status", …}`` out of ``const.py``."""
    const = (COMPONENT / "const.py").read_text(encoding="utf-8")
    domain = re.search(r'^DOMAIN:\s*Final\s*=\s*"([^"]+)"', const, re.M)
    assert domain, "DOMAIN not found in const.py"
    found = re.findall(
        r'^(WS_[A-Z_]+):\s*Final\s*=\s*f"\{DOMAIN\}/([a-z_/]+)"', const, re.M
    )
    return {name: f"{domain.group(1)}/{path}" for name, path in found}


def _ws_registered() -> tuple[set[str], dict[str, str]]:
    """``({registered handler names}, {WS constant: handler name})``."""
    tree = ast.parse((COMPONENT / "websocket_api.py").read_text(encoding="utf-8"))
    registered: set[str] = set()
    handlers: dict[str, str] = {}
    for node in ast.walk(tree):
        # for handler in (ws_status, ws_render, …):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            registered |= {
                element.id for element in node.iter.elts if isinstance(element, ast.Name)
            }
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            for name in (
                child.id for child in ast.walk(node) if isinstance(child, ast.Name)
            ):
                if name.startswith("WS_"):
                    handlers[name] = node.name
    return registered, handlers


if __name__ == "__main__":
    unittest.main()
