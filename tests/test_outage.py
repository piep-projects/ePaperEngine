"""The failure policy (FSD §12, Festlegung P10 2026-08-21).

Two of these cover cases you would otherwise only ever see by breaking the
system and then waiting a quarter of an hour: the grace run that keeps the
picture on the wall, and the frozen timestamp that keeps a standing error page
from pushing itself every 15 minutes.

Pure stdlib — ``outage.py`` has no Pillow and no aiohttp in it precisely so this
runs in CI, where nothing is installed.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from datetime import datetime, timedelta

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import outage  # noqa: E402

NOON = datetime(2026, 8, 21, 12, 0, 0)


class TestStreak(unittest.TestCase):
    def test_the_first_failure_leaves_the_picture_hanging(self) -> None:
        """One hiccup is not worth taking the family photo off the wall."""
        state: dict = {}
        hit = outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        self.assertEqual(hit.failures, 1)
        self.assertFalse(hit.show_on_wall)

    def test_the_second_failure_in_a_row_reaches_the_wall(self) -> None:
        state: dict = {}
        outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        hit = outage.note_failure(
            state, "photos", OSError("NAS still gone"), NOON + timedelta(minutes=15)
        )
        self.assertEqual(hit.failures, 2)
        self.assertTrue(hit.show_on_wall)

    def test_the_timestamp_is_the_start_of_the_streak(self) -> None:
        """Load-bearing, not cosmetic: a page carrying the *current* time would
        differ on every run, defeat the hash gate of FSD §11 and push every 15
        minutes. FSD §12 promises a permanent outage costs exactly one refresh —
        this is the line that makes that true."""
        state: dict = {}
        outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        for minutes in (15, 30, 45):
            hit = outage.note_failure(
                state, "photos", OSError("NAS gone"), NOON + timedelta(minutes=minutes)
            )
            self.assertEqual(hit.since, NOON, "the streak start moved")

    def test_a_successful_run_ends_the_streak(self) -> None:
        state: dict = {"image_hash": "abc"}
        outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        self.assertTrue(outage.clear(state))
        self.assertNotIn(outage.KEY_FAILURES, state)
        self.assertNotIn(outage.KEY_SINCE, state)
        self.assertNotIn(outage.KEY_LAST, state)
        # Everything the streak does not own stays untouched — the hash above is
        # what keeps the next run from re-pushing an identical image.
        self.assertEqual(state["image_hash"], "abc")

    def test_a_new_streak_gets_its_own_grace_run(self) -> None:
        state: dict = {}
        outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        outage.clear(state)
        later = NOON + timedelta(hours=3)
        hit = outage.note_failure(state, "photos", OSError("again"), later)
        self.assertEqual(hit.failures, 1)
        self.assertFalse(hit.show_on_wall)
        self.assertEqual(hit.since, later)

    def test_clear_on_a_clean_state_reports_nothing_to_clear(self) -> None:
        self.assertFalse(outage.clear({"image_hash": "abc"}))


class TestTechnicalLine(unittest.TestCase):
    """The one technical line of FSD §8.5 [Festlegung P11] — it hangs on a wall
    in a living room, so it says the view, the exception type and the message,
    and nothing else."""

    def test_it_names_view_type_and_message(self) -> None:
        line = outage.describe("recipes", RuntimeError("paprika sync failed"))
        self.assertEqual(line, "recipes · RuntimeError: paprika sync failed")

    def test_it_survives_an_exception_with_no_message(self) -> None:
        self.assertEqual(outage.describe("photos", ValueError()), "photos · ValueError: ")


class TestStanding(unittest.TestCase):
    """``error`` is one of the five view tokens (FSD §5), so it can be pinned by
    hand or won by a schedule — then the page shows what is on record."""

    def test_nothing_on_record_is_none(self) -> None:
        self.assertIsNone(outage.standing({}))
        self.assertIsNone(outage.standing({"last_error": {"text": "   "}}))

    def test_the_last_failure_is_returned_with_its_start(self) -> None:
        state: dict = {}
        outage.note_failure(state, "photos", OSError("NAS gone"), NOON)
        standing = outage.standing(state)
        assert standing is not None
        self.assertEqual(standing.technical, "photos · OSError: NAS gone")
        self.assertEqual(standing.since, NOON)


if __name__ == "__main__":
    unittest.main()
