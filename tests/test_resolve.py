"""The priority resolution (FSD §5).

Worth its own test file because two of its cases are otherwise only reachable by
waiting: the manual override running out, and two schedule windows overlapping.
Neither shows up in a live test on the instance unless somebody sits there for
four hours.

Home Assistant is not installed on the CI runner, and ``resolve.py`` imports
``const.py`` for its tokens — which in turn imports ``homeassistant.const``. So a
minimal stub is planted in ``sys.modules`` before the import: it costs six lines
and keeps the rule testable without a 300 MB dependency, which is the same trade
``test_translations.py`` makes with ``ast``.
"""

from __future__ import annotations

import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _install_homeassistant_stub() -> None:
    """Enough ``homeassistant`` for ``const.py`` to import."""
    if "homeassistant.const" in sys.modules:
        return
    package = types.ModuleType("homeassistant")
    const = types.ModuleType("homeassistant.const")

    class Platform(str):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        SENSOR = "sensor"

    const.Platform = Platform  # type: ignore[attr-defined]
    package.const = const  # type: ignore[attr-defined]
    sys.modules["homeassistant"] = package
    sys.modules["homeassistant.const"] = const


def _install_component_package() -> None:
    """Make ``epaperengine.<module>`` importable without running its ``__init__``.

    The real package initialiser pulls in half of Home Assistant — the frontend,
    the HTTP component, the config-entry machinery. A bare namespace package
    with the right ``__path__`` gives access to the leaf modules and to nothing
    else, which is precisely the boundary this test wants to hold.
    """
    if "epaperengine" in sys.modules:
        return
    package = types.ModuleType("epaperengine")
    package.__path__ = [str(REPO_ROOT / "custom_components" / "epaperengine")]  # type: ignore[attr-defined]
    sys.modules["epaperengine"] = package


_install_homeassistant_stub()
_install_component_package()

from epaperengine import resolve as resolve_module  # noqa: E402
from epaperengine.const import (  # noqa: E402
    CANDIDATE_FALLBACK,
    CANDIDATE_MANUAL,
    CANDIDATE_SCHEDULE,
    DEFAULT_PRIORITY,
    VIEW_CALENDAR,
    VIEW_GUESTS,
    VIEW_PHOTOS,
    VIEW_RECIPES,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def config(**overrides: object) -> dict:
    """A config document with the shipped defaults, patched section-wise."""
    document: dict = {
        "views": {
            "priority": list(DEFAULT_PRIORITY),
            "manual_timeout_h": 4,
            "manual_exceptions": [VIEW_GUESTS],
            "fallback": VIEW_CALENDAR,
        },
        "schedule": {},
        "recipes": {"selection": []},
    }
    for section, values in overrides.items():
        document[section] = {**document.get(section, {}), **values}  # type: ignore[dict-item]
    return document


def state(**overrides: object) -> dict:
    return {"manual": None, "guests_active": False, **overrides}


class TestFallback(unittest.TestCase):
    def test_nothing_active_means_fallback(self) -> None:
        result = resolve_module.resolve(config(), state(), {}, NOW)
        self.assertEqual(result.view, VIEW_CALENDAR)
        self.assertEqual(result.source, CANDIDATE_FALLBACK)

    def test_unknown_fallback_view_does_not_reach_the_display(self) -> None:
        """A typo in the store must not put an unrenderable token on the wall."""
        result = resolve_module.resolve(
            config(views={"fallback": "kalender"}), state(), {}, NOW
        )
        self.assertEqual(result.view, VIEW_CALENDAR)


class TestManualOverride(unittest.TestCase):
    def test_manual_wins_while_it_lasts(self) -> None:
        manual = {
            "view": VIEW_PHOTOS,
            "at": NOW.isoformat(),
            "until": (NOW + timedelta(hours=2)).isoformat(),
        }
        result = resolve_module.resolve(config(), state(manual=manual), {}, NOW)
        self.assertEqual(result.view, VIEW_PHOTOS)
        self.assertEqual(result.source, CANDIDATE_MANUAL)
        self.assertEqual(result.detail["until"], manual["until"])

    def test_manual_lapses_at_its_deadline(self) -> None:
        manual = {
            "view": VIEW_PHOTOS,
            "at": (NOW - timedelta(hours=5)).isoformat(),
            "until": (NOW - timedelta(minutes=1)).isoformat(),
        }
        result = resolve_module.resolve(config(), state(manual=manual), {}, NOW)
        self.assertEqual(result.source, CANDIDATE_FALLBACK)

    def test_manual_without_deadline_never_lapses(self) -> None:
        """``manual_timeout_h: 0``, and the guest exemption, both land here."""
        manual = {"view": VIEW_GUESTS, "at": NOW.isoformat(), "until": None}
        result = resolve_module.resolve(
            config(), state(manual=manual), {}, NOW + timedelta(days=3)
        )
        self.assertEqual(result.view, VIEW_GUESTS)
        self.assertEqual(result.source, CANDIDATE_MANUAL)

    def test_unreadable_deadline_keeps_the_override_standing(self) -> None:
        """Better a pin that stays visible than one that expires invisibly."""
        manual = {"view": VIEW_PHOTOS, "at": NOW.isoformat(), "until": "übermorgen"}
        result = resolve_module.resolve(config(), state(manual=manual), {}, NOW)
        self.assertEqual(result.source, CANDIDATE_MANUAL)


class TestConditions(unittest.TestCase):
    def test_guests_beat_recipes(self) -> None:
        result = resolve_module.resolve(
            config(recipes={"selection": ["uid-1"]}),
            state(guests_active=True),
            {},
            NOW,
        )
        self.assertEqual(result.view, VIEW_GUESTS)

    def test_recipes_are_active_once_something_is_picked(self) -> None:
        result = resolve_module.resolve(
            config(recipes={"selection": ["uid-1", "uid-2"]}), state(), {}, NOW
        )
        self.assertEqual(result.view, VIEW_RECIPES)
        self.assertEqual(result.detail["selected"], 2)

    def test_order_is_configuration(self) -> None:
        """The whole point of FSD §5: reordering the list changes the answer,
        and no code changes with it."""
        reordered = config(
            views={"priority": [VIEW_RECIPES, CANDIDATE_MANUAL, CANDIDATE_FALLBACK]}
        )
        manual = {
            "view": VIEW_PHOTOS,
            "at": NOW.isoformat(),
            "until": (NOW + timedelta(hours=2)).isoformat(),
        }
        result = resolve_module.resolve(
            reordered,
            state(manual=manual),
            {},
            NOW,
        )
        self.assertEqual(result.source, CANDIDATE_MANUAL)  # nothing picked yet

        result = resolve_module.resolve(
            {**reordered, "recipes": {"selection": ["uid-1"]}},
            state(manual=manual),
            {},
            NOW,
        )
        self.assertEqual(result.view, VIEW_RECIPES)  # recipes now sit above manual

    def test_a_view_without_a_condition_is_skipped(self) -> None:
        """``photos`` carries no activity rule in FSD §5, so it cannot win by
        being listed — otherwise it would swallow everything below it."""
        result = resolve_module.resolve(
            config(views={"priority": [VIEW_PHOTOS, CANDIDATE_FALLBACK]}),
            state(),
            {},
            NOW,
        )
        self.assertEqual(result.source, CANDIDATE_FALLBACK)


class TestSchedules(unittest.TestCase):
    def _config(self) -> dict:
        return config(
            schedule={
                VIEW_CALENDAR: {"entity_id": "schedule.epaper_calendar", "rank": 1},
                VIEW_PHOTOS: {"entity_id": "schedule.epaper_photos", "rank": 2},
                VIEW_RECIPES: {"entity_id": "schedule.epaper_cooking", "rank": 3},
            }
        )

    def test_a_running_window_wins_over_the_fallback(self) -> None:
        result = resolve_module.resolve(
            self._config(),
            state(),
            {"schedule.epaper_photos": "on"},
            NOW,
        )
        self.assertEqual(result.view, VIEW_PHOTOS)
        self.assertEqual(result.source, CANDIDATE_SCHEDULE)
        self.assertEqual(result.detail["rank"], 2)
        self.assertFalse(result.detail["overlapping"])

    def test_overlapping_windows_are_decided_by_rank(self) -> None:
        """FSD §5: overlapping windows are not an error — the lowest rank wins."""
        result = resolve_module.resolve(
            self._config(),
            state(),
            {
                "schedule.epaper_photos": "on",
                "schedule.epaper_calendar": "on",
                "schedule.epaper_cooking": "on",
            },
            NOW,
        )
        self.assertEqual(result.view, VIEW_CALENDAR)
        self.assertEqual(result.detail["rank"], 1)
        self.assertTrue(result.detail["overlapping"])

    def test_an_entry_without_a_rank_sorts_last(self) -> None:
        """An unconfigured rank must not outrank a deliberate one."""
        cfg = config(
            schedule={
                VIEW_PHOTOS: {"entity_id": "schedule.a", "rank": None},
                VIEW_CALENDAR: {"entity_id": "schedule.b", "rank": 9},
            }
        )
        result = resolve_module.resolve(
            cfg, state(), {"schedule.a": "on", "schedule.b": "on"}, NOW
        )
        self.assertEqual(result.view, VIEW_CALENDAR)

    def test_an_unavailable_helper_is_not_running(self) -> None:
        result = resolve_module.resolve(
            self._config(),
            state(),
            {"schedule.epaper_photos": "unavailable"},
            NOW,
        )
        self.assertEqual(result.source, CANDIDATE_FALLBACK)


if __name__ == "__main__":
    unittest.main()
