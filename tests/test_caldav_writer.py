"""The write-back transport (P42) — the one place this project changes data
that does not belong to it.

Everything here is exercised against fakes, and that is the point of the split:
``anniversaries.py`` decides *what* a title should read and is tested on plain
strings; this module decides *which object gets a PUT*, and getting that wrong
does not produce a wrong number on a wall — it destroys a real calendar.

The three failures worth a test each, all of them silent in production:

* **saving an expanded occurrence.** Measured on the live server: a search with
  ``expand=True`` returns one object per occurrence, each carrying **the
  master's URL** and a ``RECURRENCE-ID`` but no ``RRULE``. One ``save()`` on one
  of those replaces a yearly series with a single dated event, and every future
  anniversary is gone. Nobody notices until a birthday does not appear.
* **counting from the wrong day.** A series title carries one number. Run on
  20 December, the entry for 5 January has to read the January count — the same
  off-by-one P42 found on the wall, which is why each entry brings its own date.
* **writing when nothing changed.** A daily automation is only harmless if a run
  that finds everything current makes no request at all.

``homeassistant`` is stubbed rather than installed, the same trade
``test_recipes.py`` and ``test_resolve.py`` make: CI has no HA.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import types
import unittest
from datetime import date, datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _install_stubs() -> None:
    """Only the names ``caldav_writer`` touches at import time."""
    if "homeassistant.helpers.entity_registry" in sys.modules:
        return

    package = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object  # type: ignore[attr-defined]
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    registry = types.ModuleType("homeassistant.helpers.entity_registry")

    def async_get(hass: object) -> object:
        """The registry the fake hass carries — no global state in a test."""
        return hass.entity_registry  # type: ignore[attr-defined]

    registry.async_get = async_get  # type: ignore[attr-defined]

    sys.modules["homeassistant"] = package
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.entity_registry"] = registry


def _install_component_package() -> None:
    if "epaperengine" in sys.modules:
        return
    package = types.ModuleType("epaperengine")
    package.__path__ = [str(REPO_ROOT / "custom_components" / "epaperengine")]  # type: ignore[attr-defined]
    sys.modules["epaperengine"] = package


_install_stubs()
_install_component_package()

from epaperengine import caldav_writer as cw  # noqa: E402

DE = "— {years} Jahre"
CALENDAR_ID = "calendar~Eo62"
ENTRY_ID = "01M1C4WRYZB53B1SD9TC4VQFSS"


# --- the fakes ---------------------------------------------------------------


class _Dt:
    """``DTSTART`` as icalendar hands it over: a property with a ``.dt``."""

    def __init__(self, when: datetime) -> None:
        self.dt = when


class FakeObject:
    """One CalDAV resource. ``save()`` is the PUT, and it is counted."""

    def __init__(self, component: dict, url: str, log: list[str]) -> None:
        self.icalendar_component = component
        self.url = url
        self._log = log

    def save(self) -> None:
        self._log.append(str(self.icalendar_component.get("UID")))


class FakeCalendar:
    def __init__(self, masters: list[FakeObject], occurrences: list[FakeObject]) -> None:
        self.id = CALENDAR_ID
        self._masters = masters
        self._occurrences = occurrences
        self.searches: list[bool] = []

    def search(self, *, start, end, event, expand):  # noqa: ANN001, ANN202
        self.searches.append(expand)
        return self._occurrences if expand else self._masters


class FakeClient:
    def __init__(self, calendar: FakeCalendar) -> None:
        self._calendar = calendar

    def principal(self):  # noqa: ANN201
        return types.SimpleNamespace(calendars=lambda: [self._calendar])


class FakeEntry:
    def __init__(self, client: object | None) -> None:
        self.entry_id = ENTRY_ID
        self.runtime_data = client


class FakeRegistryEntry:
    def __init__(self, platform: str = "caldav", unique_id: str | None = None) -> None:
        self.platform = platform
        self.config_entry_id = ENTRY_ID
        self.unique_id = unique_id or f"{ENTRY_ID}-{CALENDAR_ID}"


class FakeHass:
    def __init__(self, entry: FakeEntry, entity: FakeRegistryEntry | None, language="de") -> None:
        self.config = types.SimpleNamespace(language=language)
        self.entity_registry = types.SimpleNamespace(async_get=lambda eid: entity)
        self.config_entries = types.SimpleNamespace(
            async_get_entry=lambda eid: entry if eid == ENTRY_ID else None
        )

    async def async_add_executor_job(self, func, *args):  # noqa: ANN001, ANN202
        return func(*args)


def _master(uid: str, summary: str, log: list[str]) -> FakeObject:
    return FakeObject(
        {"UID": uid, "SUMMARY": summary, "RRULE": "FREQ=YEARLY"},
        url=f"https://server/cal/{uid}.ics",
        log=log,
    )


def _occurrence(uid: str, when: date, log: list[str]) -> FakeObject:
    """As the server hands one back: the master's URL, a RECURRENCE-ID, no RRULE."""
    return FakeObject(
        {
            "UID": uid,
            "SUMMARY": "irrelevant",
            "RECURRENCE-ID": when.isoformat(),
            "DTSTART": _Dt(datetime(when.year, when.month, when.day, 9, 0)),
        },
        url=f"https://server/cal/{uid}.ics",
        log=log,
    )


def _setup(entries: list[tuple[str, str, date]], language: str = "de"):  # noqa: ANN202
    """``(hass, calendar, put_log)`` for a calendar holding these entries."""
    log: list[str] = []
    masters = [_master(uid, title, log) for uid, title, _on in entries]
    occurrences = [_occurrence(uid, on, log) for uid, _t, on in entries]
    calendar = FakeCalendar(masters, occurrences)
    hass = FakeHass(FakeEntry(FakeClient(calendar)), FakeRegistryEntry(), language)
    return hass, calendar, log


def _run(hass, **kwargs):  # noqa: ANN001, ANN202
    return asyncio.run(cw.async_write_back(hass, "calendar.jahrestage", **kwargs))


# --- the tests ---------------------------------------------------------------


class TestResolvingTheCalendar(unittest.TestCase):
    def test_it_finds_the_calendar_behind_the_entity(self) -> None:
        hass, _cal, _log = _setup([("u1", "Erika Müller (1946)", date(2026, 9, 5))])
        answer = _run(hass, today=date(2026, 8, 31))
        self.assertEqual(answer["total"], 1)

    def test_it_refuses_a_calendar_that_is_not_caldav(self) -> None:
        """A Local Calendar cannot be written to at all, and saying so beats a
        stack trace from a client that was never there."""
        hass = FakeHass(FakeEntry(None), FakeRegistryEntry(platform="local_calendar"))
        with self.assertRaises(cw.WriteBackError) as caught:
            _run(hass)
        self.assertIn("local_calendar", str(caught.exception))

    def test_it_refuses_an_unknown_entity(self) -> None:
        hass = FakeHass(FakeEntry(None), None)
        with self.assertRaises(cw.WriteBackError):
            _run(hass)

    def test_it_says_so_when_the_caldav_integration_hands_out_no_client(self) -> None:
        """The undocumented coupling of P42. It was accepted because it breaks
        where somebody can read it — this is that promise."""
        hass = FakeHass(FakeEntry(None), FakeRegistryEntry())
        with self.assertRaises(cw.WriteBackError) as caught:
            _run(hass)
        self.assertIn("CalDAV integration", str(caught.exception))

    def test_it_notices_a_unique_id_shape_it_does_not_understand(self) -> None:
        """The mapping rests on ``unique_id == f"{entry_id}-{calendar.id}"`` in
        somebody else's integration. If that ever changes, stop — do not write
        into a calendar picked by accident."""
        hass, cal, _log = _setup([("u1", "Erika (1946)", date(2026, 9, 5))])
        hass.entity_registry = types.SimpleNamespace(
            async_get=lambda eid: FakeRegistryEntry(unique_id="something-else")
        )
        with self.assertRaises(cw.WriteBackError):
            _run(hass)


class TestTheRecurrenceHazard(unittest.TestCase):
    """The failure that destroys data rather than displaying it wrongly."""

    def test_an_expanded_occurrence_is_never_writable(self) -> None:
        self.assertFalse(cw._is_writable({"UID": "u1", "RECURRENCE-ID": "2026-09-05"}))
        self.assertTrue(cw._is_writable({"UID": "u1", "RRULE": "FREQ=YEARLY"}))

    def test_only_the_unexpanded_search_is_ever_saved(self) -> None:
        """Both searches run, and both kinds of object carry the same URL — so
        the guard is the component, not the address."""
        hass, cal, log = _setup([("u1", "Erika Müller (1946)", date(2026, 9, 5))])
        _run(hass, dry_run=False, today=date(2026, 8, 31))
        self.assertEqual(cal.searches, [True, False], "both searches, expanded first")
        self.assertEqual(log, ["u1"], "exactly the master, exactly once")

    def test_an_occurrence_that_slips_into_the_master_list_is_still_refused(self) -> None:
        log: list[str] = []
        master = _master("u1", "Erika Müller (1946)", log)
        stray = _occurrence("u2", date(2026, 9, 5), log)
        cal = FakeCalendar([master, stray], [_occurrence("u1", date(2026, 9, 5), log)])
        hass = FakeHass(FakeEntry(FakeClient(cal)), FakeRegistryEntry())
        answer = _run(hass, dry_run=False, today=date(2026, 8, 31))
        self.assertEqual(answer["total"], 1, "the stray occurrence is not an entry")
        self.assertEqual(log, ["u1"])


class TestTheReferenceDate(unittest.TestCase):
    def test_each_entry_counts_from_its_own_next_occurrence(self) -> None:
        """Run on 20 December 2026 — the January entry belongs to 2027.

        This is the whole reason the writer reads the expanded search: without
        it, a phone would show "80" all through December for a birthday on
        5 January that the wall is already calling 81.
        """
        hass, _cal, _log = _setup(
            [
                ("dec", "Erika Müller (1946)", date(2026, 12, 22)),
                ("jan", "Hans Meier (1946)", date(2027, 1, 5)),
            ]
        )
        answer = _run(hass, today=date(2026, 12, 20))
        titles = {e["uid"]: e["new"] for e in answer["entries"]}
        self.assertEqual(titles["dec"], "Erika Müller (1946) — 80 Jahre")
        self.assertEqual(titles["jan"], "Hans Meier (1946) — 81 Jahre")

    def test_an_entry_with_no_occurrence_ahead_falls_back_to_today(self) -> None:
        log: list[str] = []
        cal = FakeCalendar([_master("u1", "Erika Müller (1946)", log)], [])
        hass = FakeHass(FakeEntry(FakeClient(cal)), FakeRegistryEntry())
        answer = _run(hass, today=date(2026, 8, 31))
        self.assertEqual(answer["entries"][0]["on"], "2026-08-31")


class TestWhatItWrites(unittest.TestCase):
    def test_a_dry_run_writes_nothing_and_still_reports_everything(self) -> None:
        hass, _cal, log = _setup([("u1", "Erika Müller (1946)", date(2026, 9, 5))])
        answer = _run(hass, today=date(2026, 8, 31))
        self.assertTrue(answer["dry_run"])
        self.assertEqual(answer["changed"], 1)
        self.assertEqual(answer["written"], 0)
        self.assertEqual(log, [], "a dry run must not touch the server")

    def test_nothing_to_change_means_no_request_at_all(self) -> None:
        """What makes a daily automation harmless."""
        hass, _cal, log = _setup(
            [("u1", "Erika Müller (1946) — 80 Jahre", date(2026, 9, 5))]
        )
        answer = _run(hass, dry_run=False, today=date(2026, 8, 31))
        self.assertEqual(answer["changed"], 0)
        self.assertEqual(log, [])

    def test_the_limit_caps_what_is_actually_saved(self) -> None:
        """"Try it on one entry first" has to mean one."""
        hass, _cal, log = _setup(
            [
                ("a", "Erika Müller (1946)", date(2026, 9, 5)),
                ("b", "Hans Meier (1950)", date(2026, 9, 6)),
                ("c", "Ulla & Christian (2006)", date(2026, 9, 7)),
            ]
        )
        answer = _run(hass, dry_run=False, limit=1, today=date(2026, 8, 31))
        self.assertEqual(answer["changed"], 3)
        self.assertEqual(answer["written"], 1)
        self.assertEqual(len(log), 1)

    def test_it_writes_the_new_title_into_the_component(self) -> None:
        """Through the parsed component, never the raw text: ``SUMMARY`` is
        folded at 75 octets and a long German name folds mid-sequence."""
        hass, cal, _log = _setup([("u1", "Erika Müller (1946)", date(2026, 9, 5))])
        _run(hass, dry_run=False, today=date(2026, 8, 31))
        self.assertEqual(
            cal._masters[0].icalendar_component["SUMMARY"],
            "Erika Müller (1946) — 80 Jahre",
        )

    def test_a_second_run_is_a_no_op(self) -> None:
        """The failure that compounds: an unrecognised suffix would be kept and
        a new one appended, every single day."""
        hass, cal, log = _setup([("u1", "Erika Müller (1946)", date(2026, 9, 5))])
        _run(hass, dry_run=False, today=date(2026, 8, 31))
        again = _run(hass, dry_run=False, today=date(2026, 8, 31))
        self.assertEqual(again["changed"], 0)
        self.assertEqual(len(log), 1)


class TestLanguage(unittest.TestCase):
    def test_it_speaks_the_language_the_wall_speaks(self) -> None:
        """Same catalogue, same string — that is why it is a shared file and not
        a constant retyped here (publish.py: SHARED)."""
        hass, _cal, _log = _setup(
            [("u1", "Erika Müller (1946)", date(2026, 9, 5))], language="en"
        )
        answer = _run(hass, today=date(2026, 8, 31))
        self.assertEqual(answer["language"], "en")
        self.assertEqual(answer["entries"][0]["new"], "Erika Müller (1946) — 80 years")

    def test_an_unknown_language_falls_back_to_the_base_one(self) -> None:
        hass, _cal, _log = _setup(
            [("u1", "Erika Müller (1946)", date(2026, 9, 5))], language="fr"
        )
        self.assertEqual(_run(hass, today=date(2026, 8, 31))["language"], "en")


if __name__ == "__main__":
    unittest.main()
