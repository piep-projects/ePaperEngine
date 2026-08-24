"""The one-display rule of FSD §14, as something a test can hold [P39].

There is exactly **one** panel on the wall, and only one Home Assistant instance
may push to it — two renderers would overwrite each other every quarter of an
hour. Until now that rule was a paragraph in the specification. It is now a
switch, and a switch is worth only as much as the chain behind it: the default
in ``store.py``, the key in the render document the coordinator builds, the
branch in the add-on that acts on it, and the checkbox that sets it.

Four files, one contract. A key renamed in one of them and not the others fails
silently — the add-on would simply never see ``push_enabled``, read its default
``True``, and push from the instance that was supposed to stay quiet. That is
the same class of bug the WebSocket-command guard in ``test_frontend_js.py``
was written for, and it is caught the same way: by reading the sources.

Source-level rather than behavioural, because ``server.py`` needs aiohttp and
Pillow and this suite runs where neither is installed.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"
ADDON = REPO_ROOT / "addon-epaperengine"

KEY = "push_enabled"
RESULT = "push_off"


def _dict_literal(source: str, function: str, section: str) -> ast.Dict:
    """The ``section`` sub-dictionary of the dict ``function`` returns."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    for key, value in zip(inner.keys, inner.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == section
                            and isinstance(value, ast.Dict)
                        ):
                            return value
    raise AssertionError(f"no {section!r} dict in {function}()")


def _keys(node: ast.Dict) -> dict[str, ast.expr]:
    return {
        key.value: value
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


class TestTheSwitchExistsEverywhereItHasTo(unittest.TestCase):
    def test_a_fresh_installation_pushes(self) -> None:
        """On by default. The first instance somebody installs is the one that
        serves the wall — asking for a switch to be found before anything
        appears on the panel would be a poor first five minutes."""
        display = _dict_literal(
            (COMPONENT / "store.py").read_text("utf-8"), "default_config", "display"
        )
        value = _keys(display).get(KEY)
        self.assertIsNotNone(value, "store.py: display section has no push_enabled")
        assert isinstance(value, ast.Constant)
        self.assertIs(value.value, True)

    def test_the_render_document_carries_it(self) -> None:
        """The add-on cannot read the store; whatever it acts on has to travel
        in the document (FSD §4)."""
        source = (COMPONENT / "coordinator.py").read_text("utf-8")
        self.assertRegex(
            source,
            rf'"{KEY}":\s*cfg\["display"\]\.get\("{KEY}",\s*True\)',
            "coordinator.py: push_enabled is not in the render document",
        )

    def test_a_document_without_the_key_still_pushes(self) -> None:
        """Both readers default to ``True``. An installation that predates the
        switch must not go quiet on its own — silence is the one failure mode
        nobody would report as a bug."""
        self.assertIn(
            f'display_cfg.get("{KEY}", True)', (ADDON / "server.py").read_text("utf-8")
        )

    def test_the_switch_is_on_the_settings_page(self) -> None:
        """Administrator-only, set once — the rule of P19."""
        panel = (COMPONENT / "panel" / "epaperengine-panel.js").read_text("utf-8")
        self.assertIn('id="display-push"', panel)
        self.assertIn("this._draft.display.push_enabled", panel)

    def test_the_outcome_is_a_state_of_its_own(self) -> None:
        """Not ``pushed`` (nothing was) and not ``push_failed`` (nothing broke).
        A run whose push was switched off is a normal outcome, and the status
        sensor has to be able to say so."""
        const = (COMPONENT / "const.py").read_text("utf-8")
        self.assertIn(f'RESULT_PUSH_OFF: Final = "{RESULT}"', const)
        block = re.search(r"RUN_RESULTS[^=]*=\s*\((.*?)\)", const, re.S)
        assert block is not None
        self.assertIn("RESULT_PUSH_OFF", block.group(1))
        self.assertIn(f"RESULT_PUSH_OFF = \"{RESULT}\"", (ADDON / "server.py").read_text("utf-8"))

    def test_both_front_end_catalogs_name_it(self) -> None:
        for language in ("en", "de"):
            catalog = json.loads(
                (COMPONENT / "frontend_i18n" / f"{language}.json").read_text("utf-8")
            )
            for key in (f"result.{RESULT}", "panel.display.push", "panel.display.push.hint"):
                self.assertIn(key, catalog, f"{language}: {key}")


class TestTheHashIsNotStoredWhileThePushIsOff(unittest.TestCase):
    """The subtle half, and the reason this file exists at all.

    ``state["image_hash"]`` means *what this instance last put on the wall*.
    With the push off it put nothing there. Storing the hash anyway would arm
    the gate of FSD §11 against a picture the display never received: switching
    the push back on would answer ``unchanged`` and leave whatever hangs there
    hanging — with no error, no log line and nothing to look at but a stale
    wall.
    """

    def setUp(self) -> None:
        source = (ADDON / "server.py").read_text("utf-8")
        tree = ast.parse(source)
        self.branch = None
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and KEY in ast.unparse(node.test):
                self.branch = node
        self.assertIsNotNone(self.branch, "server.py: no branch on push_enabled")

    def test_the_branch_writes_no_state(self) -> None:
        body = "\n".join(ast.unparse(stmt) for stmt in self.branch.body)
        self.assertNotIn("_write_state", body)

    def test_the_branch_still_serves_the_preview(self) -> None:
        """The panel preview and the media copy are not the display. They stay
        current so the instance remains usable for development — that is the
        whole point of a switch rather than an empty host field."""
        body = "\n".join(ast.unparse(stmt) for stmt in self.branch.body)
        for call in ("save_png", "PREVIEW_PATH.write_bytes", "copy_to_media"):
            self.assertIn(call, body)

    def test_the_branch_reports_the_new_result(self) -> None:
        body = "\n".join(ast.unparse(stmt) for stmt in self.branch.body)
        self.assertIn("RESULT_PUSH_OFF", body)


if __name__ == "__main__":
    unittest.main()
