"""The mirror (P53) — the one place this project **deletes** somebody's data.

``caldav_writer`` changes a title. This removes entries from a real calendar on
a real server, so the failures worth a test each are all of the destructive
kind, and every one of them is silent in production:

* **deleting what it did not write.** A target picked by mistake — the
  anniversary calendar, say — must come back as "64 foreign entries, nothing to
  delete", not as an empty calendar. The whole safety argument of P53 is that
  ownership is decided by the UID, and a UID scheme that stops naming its source
  does not raise anything: it simply lets the second mirror tidy away the first
  one's entries.
* **an unstable UID.** The identity of an entry is its content. If it were a
  random value or carried the run's timestamp, every night would delete all 30
  entries and create 30 new ones — which looks like it works, and moves every
  reminder on every phone once a day.
* **a dry run that writes.** It is the step that makes a wrong target visible
  *before* it is emptied, and it defaults to on everywhere. A dry run that
  reaches ``save_event`` or ``delete`` is worse than no preview at all.
* **the text.** ``SUMMARY`` is escaped and folded by hand (the library is never
  imported, P42), so a comma, a semicolon or an umlaut at octet 75 has to be
  exercised. A broken fold produces an entry a server accepts and a phone shows
  with half a word missing.

``homeassistant`` is stubbed rather than installed, the same trade the rest of
the suite makes: CI has no HA. ⚠ Which means the date helpers here are this
file's, not Home Assistant's — the shapes they are fed are the ones
``calendar.get_events`` actually returns, but a change in HA's parsing would not
show up here.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import types
import unittest
from datetime import date, datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LOCAL = timezone(timedelta(hours=2))


def _install_stubs() -> None:
    """Only the names ``calendar_mirror`` touches at import time."""
    if "homeassistant.util" in sys.modules:
        return

    package = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    core = sys.modules.get("homeassistant.core") or types.ModuleType("homeassistant.core")
    core.HomeAssistant = object  # type: ignore[attr-defined]
    core.callback = lambda func: func  # type: ignore[attr-defined]
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    registry = sys.modules.get(
        "homeassistant.helpers.entity_registry"
    ) or types.ModuleType("homeassistant.helpers.entity_registry")

    def async_get(hass: object) -> object:
        return hass.entity_registry  # type: ignore[attr-defined]

    registry.async_get = async_get  # type: ignore[attr-defined]

    util = types.ModuleType("homeassistant.util")
    dt_module = types.ModuleType("homeassistant.util.dt")

    def parse_date(value):  # noqa: ANN001, ANN202
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    def parse_datetime(value):  # noqa: ANN001, ANN202
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    dt_module.parse_date = parse_date  # type: ignore[attr-defined]
    dt_module.parse_datetime = parse_datetime  # type: ignore[attr-defined]
    dt_module.as_utc = lambda value: (  # type: ignore[attr-defined]
        value if value.tzinfo else value.replace(tzinfo=LOCAL)
    ).astimezone(timezone.utc)
    dt_module.as_local = lambda value: (  # type: ignore[attr-defined]
        value.replace(tzinfo=LOCAL) if value.tzinfo is None else value.astimezone(LOCAL)
    )
    dt_module.now = lambda: datetime(2026, 9, 3, 12, 0, tzinfo=LOCAL)  # type: ignore[attr-defined]
    util.dt = dt_module  # type: ignore[attr-defined]

    sys.modules["homeassistant"] = package
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.entity_registry"] = registry
    sys.modules["homeassistant.util"] = util
    sys.modules["homeassistant.util.dt"] = dt_module


def _install_component_package() -> None:
    if "epaperengine" in sys.modules:
        return
    package = types.ModuleType("epaperengine")
    package.__path__ = [str(REPO_ROOT / "custom_components" / "epaperengine")]  # type: ignore[attr-defined]
    sys.modules["epaperengine"] = package


_install_stubs()
_install_component_package()

from epaperengine import calendar_mirror as cm  # noqa: E402

SOURCE = "calendar.waste"
TARGET = "calendar.family_ha"
CALENDAR_ID = "calendar~Ho91"
ENTRY_ID = "01M1C4WRYZB53B1SD9TC4VQFSS"
TODAY = date(2026, 9, 3)
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=LOCAL)


# --- the fakes ---------------------------------------------------------------


class FakeObject:
    """One resource in the target calendar. ``delete()`` is counted."""

    def __init__(self, uid: str, log: list[str]) -> None:
        self.icalendar_component = {"UID": uid}
        self._log = log

    def delete(self) -> None:
        self._log.append("delete:" + str(self.icalendar_component["UID"]))


class FakeCalendar:
    def __init__(self, objects: list[FakeObject], log: list[str]) -> None:
        self.id = CALENDAR_ID
        self._objects = objects
        self._log = log
        self.searches: list[bool] = []
        self.saved: list[str] = []

    def search(self, *, start, end, event, expand):  # noqa: ANN001, ANN202
        self.searches.append(expand)
        return list(self._objects)

    def save_event(self, ical):  # noqa: ANN001, ANN202
        self.saved.append(ical)
        self._log.append("create")


class FakeClient:
    def __init__(self, calendar: FakeCalendar) -> None:
        self._calendar = calendar

    def principal(self):  # noqa: ANN201
        return types.SimpleNamespace(calendars=lambda: [self._calendar])


class FakeHass:
    def __init__(self, calendar: FakeCalendar, events: list[dict]) -> None:
        entity = types.SimpleNamespace(
            platform="caldav",
            config_entry_id=ENTRY_ID,
            unique_id=f"{ENTRY_ID}-{CALENDAR_ID}",
        )
        entry = types.SimpleNamespace(entry_id=ENTRY_ID, runtime_data=FakeClient(calendar))
        self.entity_registry = types.SimpleNamespace(async_get=lambda eid: entity)
        self.config_entries = types.SimpleNamespace(
            async_get_entry=lambda eid: entry if eid == ENTRY_ID else None
        )
        self.calls: list[dict] = []
        self.services = types.SimpleNamespace(async_call=self._async_call)
        self._events = events

    async def _async_call(self, domain, service, data, blocking=False, return_response=False):  # noqa: ANN001, ANN202
        self.calls.append({"domain": domain, "service": service, **data})
        return {data["entity_id"]: {"events": list(self._events)}}

    async def async_add_executor_job(self, func, *args):  # noqa: ANN001, ANN202
        return func(*args)


def _all_day(day: date, summary: str) -> dict:
    return {
        "start": day.isoformat(),
        "end": (day + timedelta(days=1)).isoformat(),
        "summary": summary,
    }


def _run(hass, **kwargs):  # noqa: ANN001, ANN202
    return asyncio.run(
        cm.async_mirror(hass, SOURCE, TARGET, today=TODAY, **kwargs)
    )


# --- the text ----------------------------------------------------------------


class TestTheText(unittest.TestCase):
    """RFC 5545 by hand, because the library is never imported [P42]."""

    def test_the_separators_are_escaped(self) -> None:
        self.assertEqual(cm.escape("Bio, Glas; Rest"), "Bio\\, Glas\\; Rest")

    def test_the_backslash_goes_first(self) -> None:
        """Escaping it last would escape the escapes this function just added."""
        self.assertEqual(cm.escape("a\\b,c"), "a\\\\b\\,c")

    def test_a_newline_becomes_the_two_characters(self) -> None:
        self.assertEqual(cm.escape("a\r\nb\nc"), "a\\nb\\nc")

    def test_a_short_line_is_left_alone(self) -> None:
        self.assertEqual(cm.fold("SUMMARY:Biomüll"), "SUMMARY:Biomüll")

    def test_a_long_line_folds_at_75_octets_with_a_leading_space(self) -> None:
        line = "SUMMARY:" + "a" * 200
        folded = cm.fold(line)
        parts = folded.split("\r\n")
        self.assertGreater(len(parts), 1)
        self.assertEqual(len(parts[0].encode("utf-8")), cm.FOLD_OCTETS)
        for part in parts[1:]:
            self.assertTrue(part.startswith(" "))
            self.assertLessEqual(len(part.encode("utf-8")), cm.FOLD_OCTETS)
        self.assertEqual(folded.replace("\r\n ", ""), line)

    def test_a_fold_never_cuts_an_umlaut_in_half(self) -> None:
        """The measured failure of the birthday tool: folding by characters
        splits a two-octet umlaut down the middle, and the entry arrives
        corrupt on a server that accepted it."""
        line = "SUMMARY:" + "ä" * 100
        folded = cm.fold(line)
        for part in folded.split("\r\n"):
            part.encode("utf-8").decode("utf-8")  # raises if a sequence was cut
        self.assertEqual(folded.replace("\r\n ", ""), line)

    def test_an_all_day_entry_is_a_date_value(self) -> None:
        item = cm.Wanted(uid="u", summary="Biomüll", start="2026-09-04",
                         end="2026-09-05", all_day=True)
        ics = cm.build_ics(item, now=NOW)
        self.assertIn("DTSTART;VALUE=DATE:20260904\r\n", ics)
        self.assertIn("DTEND;VALUE=DATE:20260905\r\n", ics)

    def test_a_timed_entry_is_written_in_utc(self) -> None:
        """Correct without shipping a VTIMEZONE nobody would read."""
        item = cm.Wanted(uid="u", summary="Abfuhr", start="2026-09-04T06:00:00+02:00",
                         end="2026-09-04T06:30:00+02:00", all_day=False)
        ics = cm.build_ics(item, now=NOW)
        self.assertIn("DTSTART:20260904T040000Z\r\n", ics)
        self.assertIn("DTEND:20260904T043000Z\r\n", ics)

    def test_every_line_ends_crlf_and_the_event_is_wrapped(self) -> None:
        ics = cm.build_ics(
            cm.Wanted(uid="u", summary="x", start="2026-09-04", end="2026-09-05",
                      all_day=True),
            now=NOW,
        )
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n\n", ics)
        for line in ics.split("\r\n"):
            self.assertNotIn("\n", line)


# --- what belongs there ------------------------------------------------------


class TestOwnership(unittest.TestCase):
    """The single rule that makes a wrong target harmless."""

    def test_the_uid_is_stable_for_the_same_entry(self) -> None:
        """An unstable UID would delete and recreate everything every night —
        which works, and moves every reminder on every phone once a day."""
        first = cm.uid_for(SOURCE, "2026-09-04", "2026-09-05", "Biomüll")
        second = cm.uid_for(SOURCE, "2026-09-04", "2026-09-05", "Biomüll")
        self.assertEqual(first, second)

    def test_a_moved_entry_is_a_different_entry(self) -> None:
        self.assertNotEqual(
            cm.uid_for(SOURCE, "2026-09-04", "2026-09-05", "Biomüll"),
            cm.uid_for(SOURCE, "2026-09-05", "2026-09-06", "Biomüll"),
        )

    def test_two_sources_never_own_each_others_entries(self) -> None:
        """The reason a UID names its source at all: one target calendar can
        carry the holidays *and* the bins, which is the likely setup — one extra
        subscription on a phone rather than two."""
        mine = cm.uid_for(SOURCE, "2026-09-04", "2026-09-05", "Biomüll")
        theirs = cm.uid_for("calendar.holidays", "2026-09-04", "2026-09-05", "Biomüll")
        self.assertNotEqual(mine, theirs)
        self.assertTrue(cm.owns(mine, SOURCE))
        self.assertFalse(cm.owns(mine, "calendar.holidays"))
        self.assertFalse(cm.owns(theirs, SOURCE))

    def test_a_foreign_uid_is_owned_by_nobody(self) -> None:
        for uid in ("", "20260904T060000Z-1234@webmail.example", "epe-@epaperengine"):
            self.assertFalse(cm.owns(uid, SOURCE), uid)

    def test_identical_events_collapse_into_one(self) -> None:
        wanted = cm.wanted_from_events(
            SOURCE, [_all_day(TODAY, "Biomüll"), _all_day(TODAY, "Biomüll")]
        )
        self.assertEqual(len(wanted), 1)

    def test_an_event_without_a_start_is_dropped_rather_than_guessed(self) -> None:
        wanted = cm.wanted_from_events(SOURCE, [{"summary": "Biomüll"}])
        self.assertEqual(wanted, [])


class TestThePlan(unittest.TestCase):
    def _wanted(self, *summaries: str) -> list[cm.Wanted]:
        return cm.wanted_from_events(
            SOURCE, [_all_day(TODAY, summary) for summary in summaries]
        )

    def test_a_fresh_target_gets_everything(self) -> None:
        plan = cm.plan(self._wanted("Biomüll", "Glas"), [], SOURCE)
        self.assertEqual(len(plan.create), 2)
        self.assertEqual(plan.delete, [])
        self.assertEqual(plan.foreign, 0)

    def test_an_unchanged_target_gets_nothing(self) -> None:
        wanted = self._wanted("Biomüll", "Glas")
        plan = cm.plan(wanted, [item.uid for item in wanted], SOURCE)
        self.assertEqual(plan.create, [])
        self.assertEqual(plan.delete, [])
        self.assertEqual(plan.keep, 2)

    def test_what_the_source_no_longer_names_is_deleted(self) -> None:
        gone = self._wanted("Sperrmüll")[0]
        wanted = self._wanted("Biomüll")
        plan = cm.plan(wanted, [wanted[0].uid, gone.uid], SOURCE)
        self.assertEqual(plan.delete, [gone.uid])
        self.assertEqual(plan.create, [])

    def test_foreign_entries_are_counted_and_left_alone(self) -> None:
        """The measured shape of the accident this guards against: pointing the
        mirror at the anniversary calendar, which holds 64 entries of somebody
        else's making."""
        foreign = [f"anniversary-{n}@webmail.example" for n in range(64)]
        plan = cm.plan(self._wanted("Biomüll"), foreign, SOURCE)
        self.assertEqual(plan.delete, [])
        self.assertEqual(plan.foreign, 64)
        self.assertEqual(len(plan.create), 1)

    def test_another_mirrors_entries_are_foreign_too(self) -> None:
        other = cm.uid_for("calendar.holidays", "2026-12-25", "2026-12-26", "Weihnachten")
        plan = cm.plan(self._wanted("Biomüll"), [other], SOURCE)
        self.assertEqual(plan.delete, [])
        self.assertEqual(plan.foreign, 1)


# --- the run -----------------------------------------------------------------


class TestTheRun(unittest.TestCase):
    def _hass(self, events, present=()):  # noqa: ANN001, ANN202
        log: list[str] = []
        calendar = FakeCalendar([FakeObject(uid, log) for uid in present], log)
        return FakeHass(calendar, events), calendar, log

    def test_a_dry_run_touches_nothing(self) -> None:
        """It is the step that makes a wrong target visible before it is
        emptied — one that wrote would be worse than no preview at all."""
        stale = cm.uid_for(SOURCE, "2026-01-01", "2026-01-02", "alt")
        hass, calendar, log = self._hass([_all_day(TODAY, "Biomüll")], present=[stale])
        answer = _run(hass, dry_run=True)
        self.assertEqual(log, [])
        self.assertEqual(calendar.saved, [])
        self.assertEqual(answer["created"], 0)
        self.assertEqual(answer["deleted"], 0)
        self.assertEqual(len(answer["create"]), 1)
        self.assertEqual(answer["delete"], [stale])

    def test_a_real_run_creates_and_deletes(self) -> None:
        stale = cm.uid_for(SOURCE, "2026-01-01", "2026-01-02", "alt")
        hass, calendar, log = self._hass([_all_day(TODAY, "Biomüll")], present=[stale])
        answer = _run(hass, dry_run=False)
        self.assertEqual(answer["created"], 1)
        self.assertEqual(answer["deleted"], 1)
        self.assertEqual(len(calendar.saved), 1)
        self.assertIn("SUMMARY:Biomüll", calendar.saved[0])

    def test_delete_happens_before_create(self) -> None:
        """An entry that moved is a delete of the old UID and a create of the
        new one. The other order leaves both on a server that refuses a
        duplicate."""
        stale = cm.uid_for(SOURCE, "2026-01-01", "2026-01-02", "alt")
        hass, _calendar, log = self._hass([_all_day(TODAY, "Biomüll")], present=[stale])
        _run(hass, dry_run=False)
        self.assertEqual(log, ["delete:" + stale, "create"])

    def test_a_second_run_writes_nothing(self) -> None:
        """Idempotence is what makes a nightly timer harmless."""
        events = [_all_day(TODAY, "Biomüll"), _all_day(TODAY + timedelta(days=7), "Glas")]
        wanted = cm.wanted_from_events(SOURCE, events)
        hass, calendar, log = self._hass(events, present=[item.uid for item in wanted])
        answer = _run(hass, dry_run=False)
        self.assertEqual((answer["created"], answer["deleted"]), (0, 0))
        self.assertEqual(log, [])

    def test_a_wrong_target_is_reported_rather_than_emptied(self) -> None:
        """The whole safety argument of P53, end to end."""
        foreign = [f"anniversary-{n}@webmail.example" for n in range(64)]
        hass, calendar, log = self._hass([_all_day(TODAY, "Biomüll")], present=foreign)
        answer = _run(hass, dry_run=False)
        self.assertEqual(answer["deleted"], 0)
        self.assertEqual(answer["foreign"], 64)
        self.assertEqual([line for line in log if line.startswith("delete")], [])

    def test_the_window_is_a_year_and_bounds_the_search(self) -> None:
        hass, _calendar, _log = self._hass([])
        _run(hass, dry_run=True)
        call = hass.calls[0]
        self.assertEqual(call["service"], "get_events")
        self.assertEqual(call["entity_id"], SOURCE)
        span = (
            datetime.fromisoformat(call["end_date_time"])
            - datetime.fromisoformat(call["start_date_time"])
        ).days
        self.assertEqual(span, cm.MIRROR_DAYS)

    def test_the_target_is_searched_unexpanded(self) -> None:
        """An expanded search hands back one object per occurrence, each
        carrying the master's URL — the hazard P42 measured, and a delete on one
        of those takes the whole series."""
        hass, calendar, _log = self._hass([])
        _run(hass, dry_run=True)
        self.assertEqual(calendar.searches, [False])

    def test_mirroring_a_calendar_onto_itself_is_refused(self) -> None:
        hass, _calendar, _log = self._hass([])
        with self.assertRaises(cm.MirrorError):
            asyncio.run(cm.async_mirror(hass, SOURCE, SOURCE, today=TODAY))

    def test_a_missing_target_is_refused(self) -> None:
        hass, _calendar, _log = self._hass([])
        with self.assertRaises(cm.MirrorError):
            asyncio.run(cm.async_mirror(hass, SOURCE, "", today=TODAY))


if __name__ == "__main__":
    unittest.main()
