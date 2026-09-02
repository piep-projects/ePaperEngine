"""Who may do what — the permission line, as something a test holds.

The rule has been stable since phase 4 and was sharpened twice since:

* **Whoever may change what hangs on the shared wall may change it.** The card
  is for the whole household, so pinning a view, switching guest mode on,
  asking for a render — and, since 2026-08-31, picking tonight's recipes and
  pressing "sync now" — are open to every logged-in user.
* **Configuration is administrator business.** ``config/set`` carries the MDC
  PIN and the Paprika account (FSD §4 keeps them out of plain YAML precisely so
  they are not lying around), and anything that does work on somebody else's
  server on our behalf goes with it.

Both halves fail *silently* when they drift. A ``require_admin`` dropped by
accident does not raise; it just quietly lets the whole household read a
password. A ``require_admin`` added by accident does not raise either; the
button simply stops working for everybody but one person, and that is exactly
how "recipes may only be picked by an administrator" survived for a week
without anybody deciding it.

Source-level, like ``test_push_switch.py``: Home Assistant is not installed on
the runner, so the decorators are read rather than exercised.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"
WEBSOCKET_API = COMPONENT / "websocket_api.py"
COORDINATOR = COMPONENT / "coordinator.py"

# The whole table, on purpose. A new command has to be entered here, and
# entering it is the moment somebody decides which side of the line it is on.
OPEN_TO_THE_HOUSEHOLD = {
    "WS_CONFIG_GET",  # reading, with the secrets redacted — see _visible_config
    "WS_STATUS",
    "WS_RENDER",  # [2026-08-24, Wolfgang: "offen lassen"]
    "WS_SET_VIEW",
    "WS_PHOTOS_LIST",
    "WS_RECIPES_SEARCH",
    "WS_RECIPES_GET",
    "WS_RECIPES_SYNC",  # [2026-08-31, Wolfgang] rate-limited instead of locked
    "WS_RECIPES_SELECT",  # [2026-08-31, Wolfgang] tonight's dinner, not config
    "WS_GUESTS_SET",
    # [2026-09-02, Wolfgang] It writes into a calendar outside this house,
    # which is why it was locked — but it can only write the number the wall
    # is already showing, into calendars an administrator configured, and
    # since the same day a nightly timer does it unattended. What was left
    # was a button only one person could press.
    "WS_CALENDAR_ANNIVERSARIES",
}

ADMIN_ONLY = {
    "WS_CONFIG_SET",  # the MDC PIN and the Paprika account go through here
    "WS_DISPLAY_TEST",
    "WS_GUESTS_BACKGROUNDS",  # rescans a folder
    "WS_CALENDAR_PROBE",
    "WS_CALENDAR_SYNC",
}


def _commands() -> dict[str, bool]:
    """``{constant name: is admin-only}`` read off the decorators."""
    tree = ast.parse(WEBSOCKET_API.read_text(encoding="utf-8"))
    found: dict[str, bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        admin = False
        command: str | None = None
        for decorator in node.decorator_list:
            source = ast.unparse(decorator)
            if "require_admin" in source:
                admin = True
            if "websocket_command" in source:
                for inner in ast.walk(decorator):
                    if isinstance(inner, ast.Name) and inner.id.startswith("WS_"):
                        command = inner.id
        if command is not None:
            found[command] = admin
    return found


def _function(path: pathlib.Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from {path.name}")


class TestThePermissionLine(unittest.TestCase):
    def test_every_command_is_on_exactly_one_side_of_the_line(self) -> None:
        """A new command that nobody classified fails here rather than shipping
        with whatever decorator happened to be copied along with it."""
        commands = _commands()
        listed = OPEN_TO_THE_HOUSEHOLD | ADMIN_ONLY
        self.assertEqual(
            set(commands),
            listed,
            "a WebSocket command is missing from this table — decide which side "
            "it belongs on and add it",
        )
        self.assertFalse(OPEN_TO_THE_HOUSEHOLD & ADMIN_ONLY)

    def test_the_open_commands_are_open(self) -> None:
        commands = _commands()
        for name in sorted(OPEN_TO_THE_HOUSEHOLD):
            with self.subTest(command=name):
                self.assertFalse(
                    commands[name],
                    f"{name} became administrator-only — the household lost a "
                    "button, and nothing would have said so",
                )

    def test_the_admin_commands_are_admin(self) -> None:
        commands = _commands()
        for name in sorted(ADMIN_ONLY):
            with self.subTest(command=name):
                self.assertTrue(
                    commands[name],
                    f"{name} lost its require_admin — this is the failure that "
                    "hands out a password without raising anything",
                )


class TestTheNarrowRecipeCommand(unittest.TestCase):
    """Why picking recipes could be opened without opening configuration.

    ``recipes.selection`` lives in the same store section as
    ``recipes.paprika_login``. Relaxing ``config/set`` would therefore have
    handed the account to everybody. The narrow command exists because it builds
    its own patch — and that is the property worth guarding, because a later
    "just forward what the caller sent" would look like a simplification.
    """

    def test_it_writes_exactly_two_keys_and_names_them_itself(self) -> None:
        node = _function(COORDINATOR, "async_set_recipe_selection")
        source = ast.unparse(node)
        # Every string literal in the body, docstring aside. The keys are
        # written out here — as dict entries and as subscripts — so any other
        # section name appearing would be a new door into the store.
        body = node.body[1:] if ast.get_docstring(node) else node.body
        strings = {
            sub.value
            for statement in body
            for sub in ast.walk(statement)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
        }
        self.assertEqual(
            strings,
            {"selection", "servings", "recipes"},
            "the patch is no longer built from literal keys — a caller's dict "
            "reaching async_set_config is the hole this command was built to avoid",
        )
        self.assertNotIn(
            "paprika", source, "the account must not be nameable from here either"
        )

    def test_the_panel_picks_through_the_narrow_command(self) -> None:
        """Not through config/set — that one is still administrator-only, so
        picking would fail on the round trip for everybody else."""
        panel = (COMPONENT / "panel" / "epaperengine-panel.js").read_text(encoding="utf-8")
        start = panel.index("async _saveSelection()")
        body = panel[start : start + 400]
        self.assertIn("epaperengine/recipes/select", body)
        self.assertNotIn("config/set", body)


class TestTheRateLimitThatReplacedALock(unittest.TestCase):
    """"Sync now" was administrator-only *because* Paprika bans by IP (FSD §9.2).

    Opening it without putting something in its place would turn a button
    anybody can hold down into an IP ban. The gap is that something, so it is
    not decoration — it is the other half of the decision.
    """

    def test_the_sync_is_rate_limited(self) -> None:
        source = ast.unparse(_function(COORDINATOR, "async_sync_recipes"))
        self.assertIn("RECIPE_SYNC_MIN_GAP_S", source)

    def test_the_gap_is_far_below_the_sync_interval(self) -> None:
        """Otherwise the guard would start skipping *scheduled* syncs, and the
        collection would quietly stop updating."""
        constants = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
        values: dict[str, int] = {}
        for node in ast.walk(constants):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                    values[node.target.id] = node.value.value
        gap = values["RECIPE_SYNC_MIN_GAP_S"]
        interval_h = values["DEFAULT_RECIPE_SYNC_INTERVAL_H"]
        self.assertLess(gap, interval_h * 3600 / 10)

    def test_the_clock_is_stamped_before_the_request(self) -> None:
        """A sync that hangs must not hold the door open for a second one."""
        node = _function(COORDINATOR, "async_sync_recipes")
        lines = ast.unparse(node).splitlines()
        stamp = next(i for i, line in enumerate(lines) if "_recipe_synced_at = now" in line)
        call = next(i for i, line in enumerate(lines) if "recipes.async_sync()" in line)
        self.assertLess(stamp, call)


if __name__ == "__main__":
    unittest.main()
