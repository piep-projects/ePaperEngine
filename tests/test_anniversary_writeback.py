"""The nightly write-back of the year count, as something a test holds [P42].

The write-back itself has been testable since 2026-08-31 — ``anniversaries.py``
decides what a title should read and is exercised directly. What is new here is
the **clock**, and every way it can go wrong is quiet:

* the timer never armed — the panel then says "never written" forever, which
  reads exactly like "nothing needed changing";
* the nightly run made a *dry* run — a timer that fires on time, logs a
  success, and changes nothing;
* the clock turned into an interval — this is the one worth naming, because it
  looks like a simplification. ``caldav_writer`` reads each entry's **own next
  occurrence** searching from midnight of the current day, so the number an
  entry should carry changes at a *date* boundary. An interval clock drifts
  across that boundary and answers differently at 23:50 than at 00:10; a time
  of day cannot.
* the default silently flipped to off, or the store lost the key — both leave a
  feature that is built, documented and never runs.

Source-level, like ``test_push_switch.py`` and ``test_permissions.py``: Home
Assistant is not installed on the runner, so the wiring is read rather than
exercised.
"""

from __future__ import annotations

import ast
import json
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"
COORDINATOR = COMPONENT / "coordinator.py"
CONST = COMPONENT / "const.py"
STORE = COMPONENT / "store.py"
PANEL = COMPONENT / "panel" / "epaperengine-panel.js"

KEY = "anniversary_writeback"
ARM = "_async_arm_anniversary_timer"
TICK = "_async_anniversary_tick"


def _function(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name}() is gone")


def _assignments(source: str) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
    return out


class AnniversaryClockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = COORDINATOR.read_text(encoding="utf-8")
        self.const = CONST.read_text(encoding="utf-8")
        self.store = STORE.read_text(encoding="utf-8")

    def test_timer_is_armed_at_setup(self) -> None:
        """Built and never started is the failure that looks like success."""
        setup = ast.unparse(_function(self.coordinator, "async_setup"))
        self.assertIn(f"self.{ARM}()", setup)

    def test_timer_is_dropped_at_shutdown(self) -> None:
        """A reload must not leave last night's clock ticking as well."""
        shutdown = ast.unparse(_function(self.coordinator, "async_shutdown"))
        self.assertIn("_anniversary_timer", shutdown)

    def test_timer_is_rearmed_when_the_calendar_section_is_saved(self) -> None:
        """The switch is worthless if turning it on waits for a restart."""
        patch = ast.unparse(_function(self.coordinator, "async_set_config"))
        self.assertIn(f"self.{ARM}()", patch)

    def test_the_clock_is_a_time_of_day_not_an_interval(self) -> None:
        """The design decision, in the one place it can be read off."""
        arm = ast.unparse(_function(self.coordinator, ARM))
        self.assertIn("async_track_time_change", arm)
        self.assertNotIn("async_track_time_interval", arm)
        self.assertIn("ANNIVERSARY_SYNC_HOUR", arm)
        self.assertIn("ANNIVERSARY_SYNC_MINUTE", arm)

    def test_the_switch_turns_the_clock_off(self) -> None:
        """Off has to mean no timer, not a timer that fires and does nothing."""
        arm = ast.unparse(_function(self.coordinator, ARM))
        self.assertIn(KEY, arm)
        self.assertIn("DEFAULT_ANNIVERSARY_WRITEBACK", arm)

    def test_the_nightly_run_is_not_a_dry_run(self) -> None:
        """A dry run at a quarter past midnight helps nobody."""
        tick = ast.unparse(_function(self.coordinator, TICK))
        self.assertIn("async_write_back_anniversaries", tick)
        self.assertIn("dry_run=False", tick)

    def test_only_a_real_run_leaves_a_trace(self) -> None:
        """The panel line answers "when did we last touch the calendar"."""
        writeback = ast.unparse(_function(self.coordinator, "async_write_back_anniversaries"))
        self.assertIn("if not dry_run", writeback)
        self.assertIn("self.state['anniversaries']", writeback)
        self.assertIn("async_save_state", writeback)

    def test_the_status_document_carries_the_last_run_and_the_hour(self) -> None:
        status = ast.unparse(_function(self.coordinator, "status_document"))
        self.assertIn("'anniversaries'", status)
        self.assertIn("ANNIVERSARY_SYNC_HOUR", status)
        self.assertIn("ANNIVERSARY_SYNC_MINUTE", status)

    def test_the_hour_is_written_down_once(self) -> None:
        """The panel says "every night at 00:15" — it must not be told twice.

        The time reaches the frontend through the status document; a literal in
        a catalogue would go on saying 00:15 after somebody moved the constant.
        """
        values = _assignments(self.const)
        self.assertEqual(values["ANNIVERSARY_SYNC_HOUR"].value, 0)
        self.assertEqual(values["ANNIVERSARY_SYNC_MINUTE"].value, 15)
        for name in ("en", "de"):
            catalogue = json.loads(
                (COMPONENT / "frontend_i18n" / f"{name}.json").read_text(encoding="utf-8")
            )
            hint = catalogue["panel.calendar.anniv.auto.hint"]
            self.assertIn("{time}", hint)
            self.assertNotIn("00:15", hint)

    def test_the_default_is_on(self) -> None:
        """[Festlegung 2026-09-02, Wolfgang.] Off by default would leave every
        anniversary calendar without its counts until somebody found a switch."""
        values = _assignments(self.const)
        self.assertIs(values["DEFAULT_ANNIVERSARY_WRITEBACK"].value, True)
        self.assertIn(f'"{KEY}": DEFAULT_ANNIVERSARY_WRITEBACK', self.store)


class AnniversaryButtonTest(unittest.TestCase):
    """The manual press, which is the same operation without waiting a night."""

    def setUp(self) -> None:
        self.panel = PANEL.read_text(encoding="utf-8")

    def test_the_button_writes_rather_than_previewing(self) -> None:
        """[Festlegung 2026-09-02, Wolfgang: no dry run.]

        The wire default is ``true``; a call that leaves the flag out is a
        button that always reports "0 written" and looks broken.
        """
        start = self.panel.index("_writeAnniversaries()")
        body = self.panel[start : start + 900]
        self.assertIn("epaperengine/calendar/anniversaries", body)
        self.assertIn("dry_run: false", body)

    def test_the_button_is_offered_only_where_it_can_do_something(self) -> None:
        """No anniversary source means nothing to write back [P42]."""
        self.assertIn('source.kind === "birthdays"', self.panel)
        self.assertIn("hasAnniversaries", self.panel)

    def test_the_switch_reaches_the_draft(self) -> None:
        """A checkbox nobody collects is a checkbox that resets on save."""
        self.assertIn("calendar-anniv-auto", self.panel)
        self.assertIn("this._draft.calendar.anniversary_writeback", self.panel)


if __name__ == "__main__":
    unittest.main()
