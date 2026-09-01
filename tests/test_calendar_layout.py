"""The calendar wall: what is shown, in what order, and where it stops.

Four things are checked, and each of them fails silently on the wall.

**The palette.** A colour bar is 6 px wide — the thinnest feature on the page.
Off the Spectra palette it is not a tint but a speckle, the same lesson the
grey hairline of 0.3.3 and the guest greeting of 0.11.0 taught. Three places
name the same colours: the add-on's ``COLORS``, the integration's
``CALENDAR_COLORS`` and the panel's picker. They are read here.

**The birthday.** The year travels in the description, or as a bracket in the
title, and nowhere else — ``calendar.get_events`` hands out five fields
[belegt]. A missing year has to cost the *age*, never the entry, and never a
line reading "turns NaN".

**The fill.** Day block after day block, whole ones only [Festlegung
2026-08-20]. Nothing enforces that but arithmetic: a column that overflows is
clipped by ``overflow: hidden`` without a word, which is exactly how the first
recipe image lost its bottom third.

**The page.** Same rule as ``test_recipe_template``: the template *sets* in CSS
what this module *measured* in Python. A day head of 66 px here and 68 px there
is one appointment quietly falling off the bottom of the third column.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import re
import sys
import unittest
from datetime import date, datetime, timedelta

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "addon-epaperengine"))

import calendar_layout as cl  # noqa: E402
import imaging  # noqa: E402
import wall_text  # noqa: E402

COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"
TEMPLATE = REPO_ROOT / "addon-epaperengine" / "templates" / "calendar.html.j2"
PANEL = COMPONENT / "panel" / "epaperengine-panel.js"

TEXT = wall_text.WallText("de")
TODAY = date(2026, 8, 23)


def _source(entity_id="calendar.a", color="blue", kind=cl.KIND_EVENTS, person="A"):
    return cl.Source(entity_id=entity_id, person=person, color=color, kind=kind)


def _event(day, start="09:00", end="10:00", summary="Termin", **extra):
    """A timed event the way ``calendar.get_events`` writes one."""
    return {
        "start": f"{day.isoformat()}T{start}:00+02:00",
        "end": f"{day.isoformat()}T{end}:00+02:00",
        "summary": summary,
        **extra,
    }


class TestPalette(unittest.TestCase):
    """Every bar colour is a Spectra primary, and all three lists agree."""

    def test_every_colour_is_a_panel_primary(self) -> None:
        primaries = {"#%02x%02x%02x" % rgb for rgb in imaging.SPECTRA}
        for token, value in cl.COLORS.items():
            self.assertIn(value, primaries, f"{token} is not a Spectra primary")

    def test_white_is_not_offered(self) -> None:
        """A white bar on a white page is no bar."""
        self.assertNotIn("#ffffff", cl.COLORS.values())

    def test_the_integration_offers_the_same_tokens(self) -> None:
        tree = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
        tokens = {
            node.target.id: node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }["CALENDAR_COLORS"]
        names = {element.value for element in tokens.elts}  # type: ignore[attr-defined]
        self.assertEqual(names, set(cl.COLORS))

    def test_the_panel_picker_offers_the_same_hex_values(self) -> None:
        block = re.search(r"const CALENDAR_COLORS = \{(.*?)\};", PANEL.read_text("utf-8"), re.S)
        assert block is not None, "the panel no longer declares CALENDAR_COLORS"
        pairs = dict(re.findall(r"(\w+):\s*\"(#[0-9a-f]{6})\"", block.group(1)))
        self.assertEqual(pairs, cl.COLORS)


class TestKinds(unittest.TestCase):
    """The three lists of source kinds, held together [P48].

    The kind is a bare string in three files: the add-on decides what to *draw*
    from it, ``const.py`` decides what the store accepts, and the panel builds
    the dropdown out of its own copy. A kind missing from one of them fails in
    a different way each time and none of them is loud: the panel would offer a
    kind the store rejects, or the store would hold one the panel cannot show —
    and ``read_source`` quietly turns anything it does not know into
    ``events``, which is a calendar that simply stops being a holiday list.
    """

    def _panel(self) -> list[str]:
        block = re.search(r"const CALENDAR_KINDS = \[(.*?)\];", PANEL.read_text("utf-8"))
        assert block is not None, "the panel no longer declares CALENDAR_KINDS"
        return re.findall(r'"(\w+)"', block.group(1))

    def test_the_integration_offers_the_same_kinds(self) -> None:
        tree = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
        literals = {
            node.target.id: node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        names = [
            str(literals[element.id].value)  # type: ignore[attr-defined,union-attr]
            for element in literals["CALENDAR_KINDS"].elts  # type: ignore[attr-defined]
        ]
        self.assertEqual(names, list(cl.KINDS))

    def test_the_panel_offers_the_same_kinds(self) -> None:
        self.assertEqual(self._panel(), list(cl.KINDS))

    def test_an_unknown_kind_falls_back_to_appointments(self) -> None:
        """An old store, or a kind removed from a later build."""
        self.assertEqual(cl.read_source({"entity_id": "calendar.a"}).kind, cl.KIND_EVENTS)
        self.assertEqual(
            cl.read_source({"entity_id": "calendar.a", "kind": "bank_holidays"}).kind,
            cl.KIND_EVENTS,
        )
        self.assertEqual(
            cl.read_source({"entity_id": "calendar.a", "kind": "holidays"}).kind,
            cl.KIND_HOLIDAYS,
        )


class TestHolidays(unittest.TestCase):
    """A holiday says what the day *is* [Festlegung P48, 2026-09-01].

    Three things were decided and each of them fails silently: the badge turns
    red like a Sunday, the name stands in a line of its own without a time and
    without a bar, and the source is in no legend because it belongs to nobody.
    """

    def _days(self, events, **kwargs):
        return cl.build_days(
            [_source(kind=cl.KIND_HOLIDAYS, person="Feiertage")],
            {"calendar.a": events},
            today=TODAY,
            text=TEXT,
            **kwargs,
        )

    def _all_day(self, day, summary):
        return {"start": day.isoformat(), "end": (day + timedelta(days=1)).isoformat(),
                "summary": summary}

    def test_the_badge_turns_red_on_a_weekday(self) -> None:
        """The whole request: „den Tag dann in rot wie einen Sonntag"."""
        day = self._days([self._all_day(TODAY + timedelta(days=2), "Tag der Arbeit")])[2]
        self.assertFalse(day.sunday)          # 2026-08-25 is a Tuesday
        self.assertTrue(day.red)
        self.assertIs(day.as_dict()["red"], True)
        self.assertIs(day.as_dict()["sunday"], False)

    def test_a_sunday_stays_red_and_a_plain_weekday_does_not(self) -> None:
        days = self._days([self._all_day(TODAY + timedelta(days=2), "Feiertag")])
        self.assertTrue(days[0].red)          # TODAY is a Sunday
        self.assertFalse(days[1].red)
        self.assertTrue(days[2].red)

    def test_the_name_is_shown(self) -> None:
        day = self._days([self._all_day(TODAY, "1. Weihnachtsfeiertag")])[0]
        self.assertEqual([h.lines for h in day.holidays], [["1. Weihnachtsfeiertag"]])
        self.assertEqual(day.as_dict()["holidays"][0]["lines"], ["1. Weihnachtsfeiertag"])

    def test_it_is_not_an_entry(self) -> None:
        """No time column, no colour bar, no legend — the entry list stays empty
        so nothing downstream can draw it as an appointment."""
        day = self._days([self._all_day(TODAY, "Tag der Deutschen Einheit")])[0]
        self.assertEqual(day.entries, [])
        self.assertEqual(day.as_dict()["entries"], [])
        self.assertNotIn("time", day.as_dict()["holidays"][0])
        self.assertNotIn("color", day.as_dict()["holidays"][0])

    def test_a_day_with_only_a_holiday_is_not_empty(self) -> None:
        """It carries a name and a red badge; "empty" drives nothing but a
        class, and calling this day empty would be a lie in the document."""
        # Two days out, not today: today is kept whatever it holds, so a holiday
        # standing on it would prove nothing about the rule.
        days = self._days(
            [self._all_day(TODAY + timedelta(days=2), "Feiertag")], show_empty_days=False
        )
        self.assertEqual([day.day for day in days],
                         [TODAY, TODAY + timedelta(days=2)])
        self.assertIs(days[-1].as_dict()["empty"], False)
        self.assertTrue(days[-1].red)

    def test_the_run_of_days_reaches_a_holiday_beyond_the_last_appointment(self) -> None:
        """``last`` is the end of the run. A holiday four days out with nothing
        after it would otherwise be cut off with the filler."""
        far = TODAY + timedelta(days=4)
        days = self._days([self._all_day(far, "Feiertag")], show_empty_days=True)
        self.assertEqual(days[-1].day, far)
        self.assertTrue(days[-1].red)

    def test_it_costs_nothing_on_a_day_that_holds_nothing_else(self) -> None:
        """46 px against a badge floor of 98 — the saving falls on busy days,
        which is where the column is tight."""
        day = self._days([self._all_day(TODAY, "Feiertag")])[0]
        self.assertEqual(day.height, cl.BADGE_MIN_H + cl.DAY_GAP)
        self.assertEqual(day.body_height, cl.HOLIDAY_H)

    def test_the_name_is_wrapped_at_the_full_body_width(self) -> None:
        """40 characters, not the title's 27 [P48].

        The line gives up the time column, so it has 673 px where an entry has
        458. Wrapping it at the title width would be silent — the name would
        simply break a line early and the badge would grow with it — so the two
        widths are held apart here by a name that fits one and not the other.
        """
        self.assertGreater(cl.HOLIDAY_CHARS, cl.TITLE_CHARS)
        name = "Tag der Deutschen Einheit und mehr"  # 34 characters
        self.assertGreater(len(name), cl.TITLE_CHARS)
        self.assertLessEqual(len(name), cl.HOLIDAY_CHARS)
        day = self._days([self._all_day(TODAY, name)])[0]
        self.assertEqual(day.holidays[0].lines, [name])
        self.assertEqual(day.holidays[0].height, cl.HOLIDAY_H)

    def test_a_wrapped_name_costs_a_line_and_raises_the_badge_with_it(self) -> None:
        """Two lines still hide under the 98 px badge floor; three do not.

        Both halves are worth pinning: the first says a wrapped name is free
        where the floor covers it, the second that the badge really does grow
        rather than clipping the name — which is how it would fail, silently,
        because the badge has ``overflow: hidden``.
        """
        two = "Fest der Verkündigung des Herrn und aller Heiligen im Bistum"
        day = self._days([self._all_day(TODAY, two)])[0]
        self.assertEqual(len(day.holidays[0].lines), 2)
        self.assertEqual(day.body_height, cl.HOLIDAY_H + cl.HOLIDAY_LINE_H)
        self.assertEqual(day.badge_height, cl.BADGE_MIN_H)   # 84 < 98, still free

        three = two + " Fulda und im Erzbistum Paderborn zu Ehren aller"
        day = self._days([self._all_day(TODAY, three)])[0]
        self.assertEqual(len(day.holidays[0].lines), 3)
        self.assertEqual(day.body_height, cl.HOLIDAY_H + 2 * cl.HOLIDAY_LINE_H)
        self.assertEqual(day.badge_height, day.body_height)
        self.assertGreater(day.badge_height, cl.BADGE_MIN_H)

    def test_it_is_never_spanned(self) -> None:
        """[Wolfgang: „vorerst gar nicht spannen"] — a multi-day entry in a
        holiday list stands on its first day and nowhere else, and draws no
        stripe: a fortnight of red badges would leave red saying nothing."""
        days = self._days(
            [{"start": TODAY.isoformat(),
              "end": (TODAY + timedelta(days=5)).isoformat(),
              "summary": "Weihnachtsferien"}]
        )
        self.assertEqual([len(day.holidays) for day in days], [1])
        self.assertEqual(days[0].spans, {})

    def test_it_survives_the_past_appointment_filter(self) -> None:
        """Like an anniversary: it is not something anybody can be late for, and
        a wall that dropped Christmas Day at 00:01 because the feed wrote it as
        a timed 00:00–00:00 entry would be a trap, not a setting."""
        days = cl.build_days(
            [_source(kind=cl.KIND_HOLIDAYS)],
            {"calendar.a": [_event(TODAY, "00:00", "00:00", summary="Feiertag")]},
            today=TODAY,
            now=datetime(TODAY.year, TODAY.month, TODAY.day, 18, 0),
            show_past_today=False,
            text=TEXT,
        )
        self.assertEqual([h.lines for h in days[0].holidays], [["Feiertag"]])

    def test_a_nameless_entry_says_so_rather_than_going_blank(self) -> None:
        day = self._days([self._all_day(TODAY, "")])[0]
        self.assertEqual(day.holidays[0].lines, [TEXT("calendar.untitled")])

    def test_the_source_is_in_no_legend(self) -> None:
        """A legend says whose appointment wears which colour; a holiday is
        nobody's, and a chip beside its name would point at nothing on the
        page. It also buys the third column a 36 px line of foot."""
        page = cl.build_page(
            {
                "calendar": {
                    "sources": [
                        {"entity_id": "calendar.a", "person": "Wolfgang", "color": "blue"},
                        {"entity_id": "calendar.f", "person": "Feiertage",
                         "color": "red", "kind": "holidays"},
                    ],
                    "events": {"calendar.a": [], "calendar.f": []},
                }
            },
            now=datetime(TODAY.year, TODAY.month, TODAY.day, 9, 0),
            text=TEXT,
        )
        labels = [who["label"] for row in page.legend for who in row]
        self.assertEqual(labels, ["Wolfgang"])

    def test_a_cut_day_keeps_its_holiday(self) -> None:
        """A day too tall for a column loses appointments from the tail."""
        entry = cl.Entry(time_text="09:00", title_lines=["x"], location="", color="#000")
        day = cl.Day(day=TODAY, entries=[entry] * 40,
                     holidays=[cl.Holiday(lines=["1. Weihnachtsfeiertag"])])
        kept = cl._fit(day, cl.COLUMN_H)
        assert kept is not None
        self.assertGreater(kept.cut, 0)
        self.assertEqual(kept.holidays, day.holidays)
        self.assertLessEqual(kept.height, cl.COLUMN_H)

    def test_a_day_whose_every_appointment_is_cut_keeps_its_holiday(self) -> None:
        """The case the guard in ``_fit`` is actually for [P48].

        One appointment whose title is long enough that it does not fit a column
        even alone: the tail-dropping loop empties the list, and without the
        guard the whole block is returned as ``None`` — the red badge and the
        name go with it, and the run of days loses Christmas Day because too
        much was happening on it. Reachable with a single entry, which is why
        the forty-appointment case above does not prove it: there the loop
        always stops with something left.
        """
        lines = (cl.COLUMN_H // cl.ENTRY_LINE_H) + 2
        entry = cl.Entry(time_text="", title_lines=["x"] * lines, location="", color="#000")
        holiday = cl.Holiday(lines=["1. Weihnachtsfeiertag"])
        self.assertGreater(entry.height + holiday.height, cl.COLUMN_H)

        day = cl.Day(day=TODAY, entries=[entry], holidays=[holiday])
        kept = cl._fit(day, cl.COLUMN_H)
        assert kept is not None, "the day was dropped and took its holiday with it"
        self.assertEqual(kept.entries, [])
        self.assertEqual(kept.cut, 1)
        self.assertEqual(kept.holidays, [holiday])
        self.assertTrue(kept.red)
        self.assertLessEqual(kept.height, cl.COLUMN_H)

        # Without a holiday the same day is still dropped: there is nothing left
        # to draw, and an empty badge with a cut marker says nothing.
        self.assertIsNone(cl._fit(cl.Day(day=TODAY, entries=[entry]), cl.COLUMN_H))


class TestBirthYear(unittest.TestCase):
    def test_the_description_carries_the_year(self) -> None:
        self.assertEqual(cl.anniversary_year("Erika Müller", "1946"), ("Erika Müller", 1946))

    def test_a_bracket_in_the_title_carries_the_year(self) -> None:
        """kalenderkonzept §6.1, since P41 the way the entries are written."""
        self.assertEqual(
            cl.anniversary_year("Erika Müller (1946)", ""), ("Erika Müller (1946)", 1946)
        )

    def test_the_bracket_stays_on_the_displayed_name(self) -> None:
        """P41: the wall shows the title the phone shows, plus the age.

        The reverse of what this asserted until 2026-08-31 — see the docstring
        of ``anniversary_year``. The year is in the title *so that* it is visible.
        """
        title, year = cl.anniversary_year("Erika Müller (1946)", "")
        self.assertEqual(title, "Erika Müller (1946)")
        self.assertEqual(year, 1946)

    def test_a_title_without_a_year_is_left_alone(self) -> None:
        """A bracket that is not a year is part of the name, not a carrier."""
        self.assertEqual(
            cl.anniversary_year("Erika Müller (Tante)", ""), ("Erika Müller (Tante)", None)
        )

    def test_a_note_in_the_description_is_not_a_year(self) -> None:
        self.assertEqual(cl.anniversary_year("Erika", "ruft immer an"), ("Erika", None))

    def test_an_implausible_number_is_not_a_year(self) -> None:
        self.assertEqual(cl.anniversary_year("Erika", "42"), ("Erika", None))

    def test_the_description_wins_over_the_title(self) -> None:
        """Only over the *year*. The title reads as written either way (P41)."""
        self.assertEqual(cl.anniversary_year("Erika (1900)", "1946"), ("Erika (1900)", 1946))
        self.assertEqual(cl.anniversary_year("Erika", "1946"), ("Erika", 1946))

    def test_the_count_is_a_difference_of_years(self) -> None:
        """And that is the whole 29 February answer — the source picks the day."""
        self.assertEqual(cl.years_since(date(2026, 2, 28), 1946), 80)
        self.assertEqual(cl.years_since(date(2026, 3, 1), 1946), 80)


class TestDays(unittest.TestCase):
    def test_events_land_on_their_day_and_sort_by_time(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [
                _event(TODAY, "17:00", "18:00", "spät"),
                _event(TODAY, "08:00", "09:00", "früh"),
            ]},
            today=TODAY,
            text=TEXT,
        )
        self.assertEqual(len(days), 1)
        self.assertEqual([e.title_lines[0] for e in days[0].entries], ["früh", "spät"])

    def test_an_all_day_entry_comes_first_and_says_so(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [
                _event(TODAY, "08:00", "09:00", "Termin"),
                {"start": TODAY.isoformat(), "end": (TODAY + timedelta(1)).isoformat(),
                 "summary": "Betriebsausflug"},
            ]},
            today=TODAY,
            text=TEXT,
        )
        first = days[0].entries[0]
        self.assertEqual(first.title_lines[0], "Betriebsausflug")
        self.assertEqual(first.time_text, TEXT("calendar.all_day"))

    def test_a_multi_day_entry_is_named_at_both_ends_and_striped_between(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [{
                "start": TODAY.isoformat(),
                "end": (TODAY + timedelta(3)).isoformat(),   # exclusive, as iCalendar writes it
                "summary": "Urlaub",
            }]},
            today=TODAY,
            text=TEXT,
        )
        # [P46] Named on the first and last day, a stripe in between — the
        # middle day carries the span but no entry of its own.
        self.assertEqual([len(day.entries) for day in days], [1, 0, 1])
        self.assertTrue(all(day.spans for day in days))
        self.assertEqual(len({key for day in days for key in day.spans}), 1)

    def test_a_gap_between_two_appointments_is_shown_as_an_empty_day(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [_event(TODAY), _event(TODAY + timedelta(2))]},
            today=TODAY,
            text=TEXT,
        )
        self.assertEqual([bool(day.entries) for day in days], [True, False, True])
        self.assertEqual(days[1].height, cl.BADGE_MIN_H + cl.DAY_GAP)

    def test_empty_days_can_be_switched_off(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [_event(TODAY), _event(TODAY + timedelta(2))]},
            today=TODAY,
            show_empty_days=False,
            text=TEXT,
        )
        self.assertEqual(len(days), 2)

    def test_the_run_of_days_stops_at_the_last_appointment(self) -> None:
        """Trailing empty days are filler, and filler costs appointments."""
        days = cl.build_days(
            [_source()],
            {"calendar.a": [_event(TODAY + timedelta(1))]},
            today=TODAY,
            horizon=TODAY + timedelta(30),
            text=TEXT,
        )
        self.assertEqual([day.day for day in days], [TODAY, TODAY + timedelta(1)])

    def test_an_empty_collection_still_shows_today(self) -> None:
        days = cl.build_days([_source()], {"calendar.a": []}, today=TODAY, text=TEXT)
        self.assertEqual(len(days), 1)
        self.assertTrue(days[0].today)
        self.assertEqual(days[0].entries, [])

    def test_today_is_marked_but_no_longer_says_so(self) -> None:
        """[P46, Wolfgang: „heute braucht es nicht — heute steht immer ganz
        oben"]. The flag survives because the model still needs to know which
        day is today; nothing on the wall repeats it."""
        days = cl.build_days([_source()], {"calendar.a": [_event(TODAY)]}, today=TODAY, text=TEXT)
        self.assertTrue(days[0].today)
        self.assertEqual(days[0].as_dict()["number"], f"{TODAY.day:02d}")
        for language in ("en", "de"):
            self.assertNotIn("calendar.today", wall_text.WallText(language)._strings)

    def test_a_long_title_wraps_and_the_entry_grows_with_it(self) -> None:
        long = "Schulung Datenschutz und Informationssicherheit für alle Bereiche"
        days = cl.build_days(
            [_source()], {"calendar.a": [_event(TODAY, summary=long)]}, today=TODAY, text=TEXT
        )
        entry = days[0].entries[0]
        self.assertGreater(len(entry.title_lines), 1)
        self.assertEqual(entry.height, cl.ENTRY_H + cl.ENTRY_LINE_H * (len(entry.title_lines) - 1))

    def test_the_title_wraps_where_the_column_actually_ends(self) -> None:
        """FSD §8.1 says "~31 characters", measured against the mockup's 773 px
        column. P30 grew the column to 805 px and the figure to 35; P46 took
        132 px back for the badge rail and it is 27. The model never changed —
        only the width it is applied to."""
        self.assertEqual(cl.TITLE_W, cl.COLUMN_W - cl.RAIL_W - cl.TITLE_DX)
        self.assertEqual(cl.TITLE_CHARS, cl.chars_per_line(cl.TITLE_PX, cl.TITLE_W))
        self.assertIn(cl.TITLE_CHARS, range(25, 30))


class TestSpannedAppointments(unittest.TestCase):
    """A timed appointment that covers several days [Festlegung 2026-08-31].

    Reported from the wall: "1 September 10:00 – 14 September 15:00" stood on a
    single day, labelled "10:00–15:00" — the start of the first day beside the
    end of the last, which reads as a five-hour appointment. Only all-day
    entries were ever spanned.

    The evening keeps its old reading, and that is what makes this a rule rather
    than a swap: 23:00–01:00 is one appointment on the evening it belongs to.
    """

    def _timed(self, start, end, summary="Urlaub", **extra):
        return {"start": start, "end": end, "summary": summary, **extra}

    def _days(self, event, today=TODAY, now=None):
        return cl.build_days(
            [_source()], {"calendar.a": [event]}, today=today, now=now, text=TEXT
        )

    def _run(self, event, today=TODAY, now=None):
        return [(day.day, entry.time_text)
                for day in self._days(event, today, now) for entry in day.entries]

    def _striped(self, event, today=TODAY, now=None):
        return [day.day for day in self._days(event, today, now) if day.spans]

    def test_the_reported_case_covers_every_day_it_runs_through(self) -> None:
        """The 2026-08-31 report, re-read under P46.

        It is still on the wall for all fourteen days — as an unbroken stripe
        rather than as fourteen entries. What it costs is the middle: the 7th
        no longer names the appointment, it only carries the colour.
        """
        event = self._timed(
            "2026-09-01T10:00:00+02:00", "2026-09-14T15:00:00+02:00",
        )
        today = date(2026, 8, 31)
        drawn = self._run(event, today=today)
        self.assertEqual(drawn, [
            (date(2026, 9, 1), TEXT("calendar.spans_from", time="10:00")),
            (date(2026, 9, 14), TEXT("calendar.spans_until", time="15:00")),
        ])
        self.assertEqual(
            self._striped(event, today=today),
            [date(2026, 9, n) for n in range(1, 15)],
        )

    def test_a_running_appointment_that_began_before_today_is_on_the_wall(self) -> None:
        """The worst of the three, because it is silent.

        The old code put a timed appointment on its start day only, and
        ``build_days`` drops days before today — so an appointment that started
        last week and runs all next week produced **no entry at all** while it
        was running.
        """
        event = self._timed(
            "2026-08-18T10:00:00+02:00", "2026-08-27T15:00:00+02:00",
        )
        now = datetime(2026, 8, 23, 20, 0)
        # **The first day shown is not the first day it has** — so it opens with
        # "durchgehend", not "ab 10:00". Which end of a span gets which label is
        # decided before the day filtering, and read off again after it [P46].
        self.assertEqual(self._run(event, now=now), [
            (TODAY, TEXT("calendar.spans_through")),
            (TODAY + timedelta(4), TEXT("calendar.spans_until", time="15:00")),
        ])
        self.assertEqual(self._striped(event, now=now),
                         [TODAY + timedelta(n) for n in range(5)])

    def test_an_evening_that_runs_past_midnight_stays_one_appointment(self) -> None:
        drawn = self._run(self._timed(
            "2026-08-23T23:00:00+02:00", "2026-08-24T01:00:00+02:00", "Konzert",
        ))
        self.assertEqual(drawn, [(TODAY, "23:00–01:00")])

    def test_past_the_morning_hour_it_is_two_days(self) -> None:
        drawn = self._run(self._timed(
            "2026-08-23T22:00:00+02:00", "2026-08-24T07:00:00+02:00", "Nachtschicht",
        ))
        self.assertEqual(drawn, [
            (TODAY, TEXT("calendar.spans_from", time="22:00")),
            (TODAY + timedelta(1), TEXT("calendar.spans_until", time="07:00")),
        ])

    def test_a_day_left_before_the_morning_is_not_a_day_it_was_on(self) -> None:
        """And the day before it is run through, not finished.

        "bis 00:00" reads as "ends when the day begins"; the appointment is on
        that day from midnight to midnight.
        """
        drawn = self._run(self._timed(
            "2026-08-23T09:00:00+02:00", "2026-08-25T00:00:00+02:00", "Messe",
        ))
        self.assertEqual(drawn, [
            (TODAY, TEXT("calendar.spans_from", time="09:00")),
            (TODAY + timedelta(1), TEXT("calendar.spans_through")),
        ])

    def test_the_end_of_a_span_sorts_with_the_all_day_entries(self) -> None:
        """It has no time of its own, so it cannot sort by one.

        Since P46 this is only visible at the **ends** of a span: the days in
        between carry the stripe and no entry, so there is nothing left there
        to sort. The last day is the one that keeps the point — it began at
        midnight, before anything else that day, and "bis 15:00" is when it
        stops rather than when it starts.
        """
        days = cl.build_days(
            [_source()],
            {"calendar.a": [
                _event(TODAY + timedelta(3), "08:00", "09:00", "früh"),
                self._timed("2026-08-23T10:00:00+02:00",
                            "2026-08-26T15:00:00+02:00", "Urlaub"),
            ]},
            today=TODAY,
            text=TEXT,
        )
        self.assertEqual([e.title_lines[0] for e in days[3].entries], ["Urlaub", "früh"])
        # The 24th and the 25th are run through: the stripe, and nothing else.
        for middle in (days[1], days[2]):
            self.assertEqual(middle.entries, [])
            self.assertTrue(middle.spans)

    def test_an_anniversary_is_a_day_and_never_a_span(self) -> None:
        """A wedding day drawn across a week is one line, not seven."""
        drawn = self._run(
            self._timed("2026-08-23T09:00:00+02:00",
                        "2026-08-30T09:15:00+02:00", "Hochzeitstag"),
        )
        timed = cl.build_days(
            [_source(kind=cl.KIND_BIRTHDAYS)],
            {"calendar.a": [self._timed("2026-08-23T09:00:00+02:00",
                                        "2026-08-30T09:15:00+02:00", "Hochzeitstag")]},
            today=TODAY,
            text=TEXT,
        )
        # As an ordinary event: two ends and a stripe over all eight days.
        self.assertEqual(len(drawn), 2)
        self.assertEqual(
            len(self._striped(self._timed("2026-08-23T09:00:00+02:00",
                                          "2026-08-30T09:15:00+02:00", "Hochzeitstag"))),
            8,
        )
        # As an anniversary: one day, one entry, no stripe at all.
        self.assertEqual(sum(len(d.entries) for d in timed), 1)
        self.assertEqual([d.day for d in timed if d.spans], [])

    def test_a_single_day_appointment_is_untouched(self) -> None:
        self.assertEqual(self._run(_event(TODAY, "09:00", "10:00")),
                         [(TODAY, "09:00–10:00")])

    def test_the_days_are_the_rule_on_its_own(self) -> None:
        """``_timed_days`` without the labelling around it."""
        span = cl._timed_days(datetime(2026, 9, 1, 10, 0), datetime(2026, 9, 3, 15, 0))
        self.assertEqual(span, [date(2026, 9, n) for n in (1, 2, 3)])
        # An end before the start is broken data, not a negative span.
        self.assertEqual(cl._timed_days(datetime(2026, 9, 3, 10, 0),
                                        datetime(2026, 9, 1, 10, 0)),
                         [date(2026, 9, 3)])
        # No end at all is the start day.
        self.assertEqual(cl._timed_days(datetime(2026, 9, 1, 10, 0), None),
                         [date(2026, 9, 1)])

    def test_every_span_label_fits_the_time_column(self) -> None:
        """The column is 185 px with ``overflow: hidden`` — it truncates silently.

        "durchgehend" is the longest of them and clears the budget by 13 px, so
        a third catalog is the case this guards: a longer word would be cut on
        the wall with nothing in the log. Measured against the file Chromium
        draws with, the way ``CHAR_RATIO`` is (P32); skipped where it is absent
        so CI needs no font package.
        """
        candidates = [
            pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            pathlib.Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        ]
        path = next((c for c in candidates if c.exists()), None)
        if path is None:
            self.skipTest("DejaVu Sans is not installed here")
        try:
            from PIL import ImageFont
        except ImportError:
            self.skipTest("Pillow is not installed here")

        font = ImageFont.truetype(str(path), cl.TIME_PX)
        for language in ("en", "de"):
            say = wall_text.WallText(language)
            for text in (say("calendar.spans_from", time="22:00"),
                         say("calendar.spans_through"),
                         say("calendar.spans_until", time="15:00"),
                         say("calendar.all_day")):
                self.assertLessEqual(
                    font.getlength(text), cl.TIME_W,
                    f"{language}: {text!r} is wider than the {cl.TIME_W} px time column",
                )


class TestAnniversaryEntries(unittest.TestCase):
    """Not only birthdays [P41]: weddings, name days, a jubilee — one wording."""

    def _days(self, description="1985", summary="Anna Berger"):
        return cl.build_days(
            [_source(kind=cl.KIND_BIRTHDAYS, color="red")],
            {"calendar.a": [
                _event(TODAY, "09:00", "09:15", summary, description=description)
            ]},
            today=TODAY,
            text=TEXT,
        )

    def test_the_year_count_is_appended(self) -> None:
        entry = self._days()[0].entries[0]
        self.assertEqual(entry.title_lines[0], "Anna Berger — 41 Jahre")

    def test_the_year_may_ride_in_the_title(self) -> None:
        """P41: it is written there so a phone's calendar app shows it, and the
        wall shows the title as written rather than a second version of it."""
        entry = self._days(summary="Anna Berger (1985)", description="")[0].entries[0]
        # Two lines since P46 — 29 characters against a 27-character column.
        # The bracket is the measured price of the year in the title [P41].
        self.assertEqual(" ".join(entry.title_lines), "Anna Berger (1985) — 41 Jahre")

    def test_the_wording_fits_an_anniversary_that_is_not_a_birthday(self) -> None:
        """The reason the sentence is neutral: "wird 20" would be wrong here,
        and ``get_events`` hands over no field that could say which kind it is
        (kalenderkonzept §3.1 — five fields, and CATEGORIES is not among them).
        What is being celebrated stands in the title, written by the household."""
        entry = self._days(summary="Hochzeit Ulla & Christian (2006)",
                           description="")[0].entries[0]
        self.assertEqual(
            " ".join(entry.title_lines),
            "Hochzeit Ulla & Christian (2006) — 20 Jahre",
        )
        # Und er braucht zwei Zeilen: 43 Zeichen bei ~35 je Zeile. Das ist der
        # gemessene Preis des Jahres im Titel (P41) — 38 px, gut 0,45 Termine.
        self.assertEqual(len(entry.title_lines), 2)
        self.assertEqual(entry.height, cl.ENTRY_H + cl.ENTRY_LINE_H)

    def test_a_missing_year_costs_the_count_not_the_entry(self) -> None:
        entry = self._days(description="")[0].entries[0]
        self.assertEqual(entry.title_lines[0], "Anna Berger")

    def test_a_written_back_suffix_is_replaced_not_doubled(self) -> None:
        """P42: the calendar may already carry a count, put there by the sync.

        Without stripping it the wall would read "… — 41 Jahre — 41 Jahre", and
        it would grow by one suffix for every catalogue the entry passes."""
        entry = self._days(summary="Anna Berger (1985) — 40 Jahre",
                           description="")[0].entries[0]
        self.assertEqual(" ".join(entry.title_lines), "Anna Berger (1985) — 41 Jahre")

    def test_the_wall_computes_rather_than_trusting_the_stored_count(self) -> None:
        """The reason for P42, measured: a series title carries **one** number
        while the wall looks 30 days ahead. Here the stored count is a year
        stale — as it is for a January anniversary during all of December — and
        the wall still shows the right one for the day it is drawing."""
        entry = self._days(summary="Anna Berger (1985) — 3 Jahre",
                           description="")[0].entries[0]
        self.assertEqual(" ".join(entry.title_lines), "Anna Berger (1985) — 41 Jahre")

    def test_an_unrecognised_suffix_costs_the_suffix_not_the_year(self) -> None:
        """A hand-typed line, or one from an older catalogue wording: the year
        is still found under it, because the bracket is looked for anywhere."""
        entry = self._days(summary="Anna Berger (1985) wird bald 41",
                           description="")[0].entries[0]
        self.assertEqual(
            " ".join(entry.title_lines), "Anna Berger (1985) wird bald 41 — 41 Jahre"
        )

    def test_a_name_day_has_no_year_and_gets_no_number(self) -> None:
        entry = self._days(summary="Namenstag Christian", description="")[0].entries[0]
        self.assertEqual(entry.title_lines[0], "Namenstag Christian")

    def test_only_the_start_time_is_shown(self) -> None:
        """09:00–09:15 is a slot, not a duration (kalenderkonzept §6.1)."""
        self.assertEqual(self._days()[0].entries[0].time_text, "09:00")

    def test_the_bar_carries_the_source_colour(self) -> None:
        self.assertEqual(self._days()[0].entries[0].color, cl.COLORS["red"])


class TestTodayFilter(unittest.TestCase):
    """``show_past_today`` — and the two exemptions that keep it from being a trap."""

    NOW = datetime(2026, 8, 23, 18, 0, tzinfo=None)

    def _entries(self, events, kind=cl.KIND_EVENTS, show_past=False):
        days = cl.build_days(
            [_source(kind=kind)],
            {"calendar.a": events},
            today=TODAY,
            now=self.NOW,
            show_past_today=show_past,
            text=TEXT,
        )
        return days[0].entries if days else []

    def test_a_finished_appointment_is_dropped(self) -> None:
        self.assertEqual(self._entries([_event(TODAY, "08:00", "09:00")]), [])

    def test_it_is_kept_when_the_household_asked_for_it(self) -> None:
        self.assertEqual(len(self._entries([_event(TODAY, "08:00", "09:00")], show_past=True)), 1)

    def test_a_running_appointment_stays(self) -> None:
        self.assertEqual(len(self._entries([_event(TODAY, "17:00", "19:00")])), 1)

    def test_a_birthday_does_not_vanish_at_nine_sixteen(self) -> None:
        entries = self._entries(
            [_event(TODAY, "09:00", "09:15", "Anna", description="1985")],
            kind=cl.KIND_BIRTHDAYS,
        )
        self.assertEqual(len(entries), 1)

    def test_an_all_day_entry_has_no_past_to_be_in(self) -> None:
        entries = self._entries(
            [{"start": TODAY.isoformat(), "end": (TODAY + timedelta(1)).isoformat(),
              "summary": "Betriebsausflug"}]
        )
        self.assertEqual(len(entries), 1)

    def test_tomorrow_is_never_filtered(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [_event(TODAY + timedelta(1), "08:00", "09:00")]},
            today=TODAY,
            now=self.NOW,
            text=TEXT,
        )
        self.assertEqual(len(days[-1].entries), 1)


class TestSundayAndEmptyDays(unittest.TestCase):
    """The two things a column is read by [Festlegung P45, 2026-08-31]."""

    def test_sunday_is_read_off_the_date(self) -> None:
        # 2026-08-23 is a Sunday, the 24th is not.
        self.assertTrue(cl.Day(day=date(2026, 8, 23)).sunday)
        self.assertFalse(cl.Day(day=date(2026, 8, 24)).sunday)

    def test_the_flag_reaches_the_template(self) -> None:
        days = cl.build_days([_source()], {"calendar.a": []},
                             today=date(2026, 8, 23), text=TEXT)
        self.assertIs(days[0].as_dict()["sunday"], True)

    def test_it_cannot_disagree_with_the_day(self) -> None:
        """There is no setter — a stale flag is not reachable."""
        self.assertNotIn("sunday", {f.name for f in dataclasses.fields(cl.Day)})

    def test_the_sunday_colour_is_a_panel_primary(self) -> None:
        """Off the palette, so it carries no dither raster [P22/P23]."""
        self.assertIn(cl.SUNDAY_COLOR, cl.COLORS)
        self.assertIn(cl.COLORS[cl.SUNDAY_COLOR],
                      {"#%02x%02x%02x" % rgb for rgb in imaging.SPECTRA})

    def test_an_empty_day_is_the_bare_badge(self) -> None:
        """P45 replaced "keine Termine" with a dash; P46 dropped the dash too.

        The badge is there whatever the day holds, and white beside it says
        "nothing" as plainly as a dash did — for the same 122 px the dash cost
        120. Gaplessness is untouched."""
        days = cl.build_days([_source()], {"calendar.a": []},
                             today=TODAY, text=TEXT)
        self.assertEqual(days[0].height, cl.BADGE_MIN_H + cl.DAY_GAP)
        self.assertEqual(days[0].height, 122)
        self.assertIs(days[0].as_dict()["empty"], True)
        for language in ("en", "de"):
            self.assertNotIn("calendar.empty", wall_text.WallText(language)._strings)


class TestColumns(unittest.TestCase):
    def _day(self, entries: int, day: date | None = None) -> cl.Day:
        return cl.Day(
            day=day or TODAY,
            entries=[
                cl.Entry(time_text="09:00", title_lines=["x"], location="", color="#000")
                for _ in range(entries)
            ],
        )

    def test_no_column_is_ever_taller_than_the_column(self) -> None:
        days = [self._day(4, TODAY + timedelta(n)) for n in range(20)]
        for column in cl.fill_columns(days):
            self.assertLessEqual(sum(day.height for day in column), cl.COLUMN_H)

    def test_a_block_that_does_not_fit_moves_to_the_next_column_whole(self) -> None:
        """Never split across columns [Festlegung 2026-08-20]."""
        days = [self._day(6, TODAY + timedelta(n)) for n in range(9)]
        columns = cl.fill_columns(days)
        placed = [day for column in columns for day in column]
        self.assertEqual([day.cut for day in placed], [0] * len(placed))

    def test_what_no_longer_fits_is_simply_not_shown(self) -> None:
        days = [self._day(6, TODAY + timedelta(n)) for n in range(40)]
        columns = cl.fill_columns(days)
        self.assertLess(sum(len(column) for column in columns), 40)

    def test_a_day_taller_than_a_whole_column_is_cut_and_says_so(self) -> None:
        """The one case FSD §8.1 leaves open — dropping it would take every
        later day with it and leave no trace on the wall."""
        columns = cl.fill_columns([self._day(20)])
        block = columns[0][0]
        self.assertGreater(block.cut, 0)
        self.assertLessEqual(block.height, cl.COLUMN_H)
        self.assertEqual(len(block.entries) + block.cut, 20)

    def test_the_geometry_matches_the_canvas(self) -> None:
        # 2400 does not divide into three columns and two gutters evenly —
        # (2400 - 80) / 3 is 773.33. The mockup and FSD §8.1 both round down to
        # 773 and leave the odd pixel on the right margin.
        self.assertEqual(cl.COLUMN_W * 3 + cl.GUTTER * 2, cl.CONTENT_W - 1)
        self.assertEqual(cl.COLUMN_TOP + cl.COLUMN_H, cl.COLUMN_BOTTOM)

    def test_the_columns_start_at_the_margin_because_there_is_no_header(self) -> None:
        """[P29] — the header cost 140 px off all three columns to say the date
        a second time."""
        self.assertEqual(cl.COLUMN_TOP, cl.MARGIN)
        self.assertEqual(cl.COLUMN_H, 1408)

    def test_nothing_is_reserved_at_the_bottom(self) -> None:
        """[P31] The calendar is a list that runs out, not a page with a
        baseline — the columns end at the canvas."""
        self.assertEqual(cl.MARGIN_BOTTOM, 0)
        self.assertEqual(cl.COLUMN_BOTTOM, cl.CANVAS_H)

    def test_the_margin_is_the_measured_one_not_the_mockups(self) -> None:
        """[P30] 80 px left 17 % of the panel unused and were never measured —
        `projektidee.md` §4 marks them "Vorschlag, nicht gemessen"."""
        self.assertEqual(cl.MARGIN, 32)
        self.assertEqual(cl.COLUMN_W, (cl.CONTENT_W - 2 * cl.GUTTER) // 3)

    def test_only_the_third_column_pays_for_the_foot(self) -> None:
        days = [self._day(3, TODAY + timedelta(n)) for n in range(20)]
        columns = cl.fill_columns(days, [cl.COLUMN_H, cl.COLUMN_H, cl.COLUMN_H - 96])
        self.assertLessEqual(sum(day.height for day in columns[0]), cl.COLUMN_H)
        self.assertLessEqual(sum(day.height for day in columns[1]), cl.COLUMN_H)
        self.assertLessEqual(sum(day.height for day in columns[2]), cl.COLUMN_H - 96)


class TestTheMockupLoad(unittest.TestCase):
    """The claim of FSD §8.1: three columns carry 22 appointments on 9 days.

    Reproduced from the mockup's own table (``tools/mockup-gen/pages_wand.py``),
    so the number in the specification and the number this module produces are
    the same number.
    """

    LOAD = [5, 3, 2, 3, 2, 0, 3, 2, 2]  # appointments per day, 22 in 9 days

    def _days(self) -> list[cl.Day]:
        out = []
        for offset, count in enumerate(self.LOAD):
            day = TODAY + timedelta(offset)
            entries = [
                cl.Entry(
                    time_text="10:00–11:00",
                    title_lines=["Kundentermin Meier GmbH"],
                    location="Werk 2, Halle B",
                    color=cl.COLORS["blue"],
                )
                for _ in range(count)
            ]
            out.append(cl.Day(day=day, entries=entries))
        return out

    def test_the_mockup_load_fits_in_three_columns(self) -> None:
        columns = cl.fill_columns(self._days())
        placed = [day for column in columns for day in column]
        self.assertEqual(len(placed), 9)
        self.assertEqual(sum(len(day.entries) for day in placed), 22)


class TestPage(unittest.TestCase):
    def _document(self, **section):
        return {"calendar": {
            "sources": [{"entity_id": "calendar.a", "person": "Wolfgang", "color": "blue"}],
            "events": {"calendar.a": [_event(TODAY)]},
            **section,
        }}

    def test_the_legend_names_every_source(self) -> None:
        page = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        self.assertEqual(page.legend, [[{"label": "Wolfgang", "hex": cl.COLORS["blue"]}]])

    def test_a_source_without_a_person_still_gets_a_label(self) -> None:
        document = self._document()
        document["calendar"]["sources"][0]["person"] = ""
        page = cl.build_page(document, now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        self.assertEqual(page.legend[0][0]["label"], "a")

    def test_a_failed_source_is_named_on_the_wall(self) -> None:
        page = cl.build_page(
            self._document(failed={"calendar.a": "boom"}),
            now=datetime(2026, 8, 23, 12, 0),
            text=TEXT,
        )
        self.assertEqual(page.notes, [TEXT("calendar.source_failed", person="Wolfgang")])

    def test_a_note_grows_the_foot_rather_than_the_page(self) -> None:
        plain = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        with_note = cl.build_page(
            self._document(failed={"calendar.a": "boom"}),
            now=datetime(2026, 8, 23, 12, 0),
            text=TEXT,
        )
        self.assertEqual(with_note.foot_h, plain.foot_h + cl.FOOT_LINE)

    def test_the_foot_is_the_lines_it_actually_holds(self) -> None:
        """One legend row and 24 px of air — measured, not assumed, because the
        foot is anchored to the bottom and a line too many grows *upwards* into
        the last appointment. Since P38 there is no timestamp line."""
        page = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        self.assertEqual(page.foot_h, cl.FOOT_GAP + cl.FOOT_LINE)

    def test_the_page_carries_no_timestamp(self) -> None:
        """[P38] The one thing that made every calendar image unique. A stamp
        on the minute defeats the hash lock of FSD 11: all four scheduled runs
        an hour became real pushes with a visible refresh of the wall."""
        page = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        self.assertEqual(page.stamp, "")

    def test_two_runs_a_quarter_hour_apart_build_the_very_same_page(self) -> None:
        """The property the wall actually cares about — same content, same
        picture, so the hash lock says ``unchanged`` and nothing is pushed."""
        first = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        later = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 15), text=TEXT)
        self.assertEqual(first.as_dict(), later.as_dict())

    def test_the_stamp_travels_with_the_page(self) -> None:
        """The hook is still there for a caller that wants a foot line, and it
        pays for its own height."""
        page = cl.build_page(
            self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT, stamp="X"
        )
        self.assertEqual(page.stamp, "X")
        self.assertEqual(page.foot_h, cl.FOOT_GAP + 2 * cl.FOOT_LINE)

    def test_no_source_is_said_out_loud(self) -> None:
        page = cl.build_page(
            {"calendar": {"sources": [], "events": {}}},
            now=datetime(2026, 8, 23, 12, 0),
            text=TEXT,
        )
        self.assertEqual(page.notes, [TEXT("calendar.no_sources")])

    def test_the_bar_width_is_bounded(self) -> None:
        # A cleared field (0) means "unset" and takes the default; anything
        # else is held between the measured floor and something still sane.
        for value, expected in ((0, cl.BAR_W), (1, 2), (6, 6), (500, 24)):
            page = cl.build_page(
                self._document(color_bar_px=value),
                now=datetime(2026, 8, 23, 12, 0),
                text=TEXT,
            )
            self.assertEqual(page.bar_px, expected)

    def test_an_unknown_colour_falls_back_to_a_palette_one(self) -> None:
        source = cl.read_source({"entity_id": "calendar.a", "color": "#123456"})
        self.assertIn(source.color, cl.COLORS)

    def test_the_date_is_said_exactly_once(self) -> None:
        """The defect that removed the header [P29]: the page carried "Sunday,
        August 23" at 64 px *and* "Today · Sunday, August 23" right under it.

        P46 brought a header back, and this is the test that says it is not the
        same header: it carries the **month**, the badges carry number and
        weekday, and neither repeats the other.
        """
        page = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        self.assertEqual(page.header, "August 2026")
        badges = [item for column in page.columns for item in column
                  if item["kind"] == "day"]
        self.assertEqual(badges[0]["number"], "23")
        self.assertEqual(badges[0]["weekday"], "So")
        for badge in badges:
            self.assertNotIn("August", badge["number"] + badge["weekday"])


class TestFoot(unittest.TestCase):
    """The foot is anchored to the bottom of the third column, so a line more
    than the model reserved does not vanish off the canvas — it grows *upwards*
    into the last appointment. Its height is therefore measured."""

    def _legend(self, *labels):
        return [{"label": label, "hex": "#000"} for label in labels]

    def test_three_ordinary_names_are_one_line(self) -> None:
        """Measured: Wolfgang · Ehefrau · Geburtstage = 613 px of 773."""
        rows = cl.legend_lines(self._legend("Wolfgang", "Ehefrau", "Geburtstage"))
        self.assertEqual(len(rows), 1)

    def test_names_that_do_not_fit_break_into_a_second_line(self) -> None:
        rows = cl.legend_lines(
            self._legend("Wolfgang", "Ehefrau", "Geburtstage", "Firmentermine", "Vereinssachen")
        )
        self.assertGreater(len(rows), 1)
        self.assertEqual(sum(len(row) for row in rows), 5)

    def test_no_legend_line_is_wider_than_the_column(self) -> None:
        labels = ["Wolfgang", "Ehefrau", "Geburtstage", "Ferien der Kinder", "Müllabfuhr"]
        for row in cl.legend_lines(self._legend(*labels)):
            width = sum(
                cl.LEGEND_CHIP_W + cl.LEGEND_CHIP_GAP + cl._text_w(who["label"]) for who in row
            ) + cl.LEGEND_GAP * (len(row) - 1)
            self.assertLessEqual(width, cl.COLUMN_W)

    def test_a_single_name_too_wide_for_the_column_still_gets_its_own_line(self) -> None:
        rows = cl.legend_lines(self._legend("x" * 200))
        self.assertEqual(len(rows), 1)

    def test_the_height_follows_the_lines(self) -> None:
        self.assertEqual(cl.foot_height(1, 0), cl.FOOT_GAP + 2 * cl.FOOT_LINE)
        self.assertEqual(cl.foot_height(2, 1), cl.FOOT_GAP + 4 * cl.FOOT_LINE)
        self.assertEqual(cl.foot_height(0, 0, stamp=False), 0)


class TestCatalogs(unittest.TestCase):
    """Both wall catalogs carry every key the page asks for."""

    KEYS = (
        "format.clock", "format.month_year", "format.week_span",
        "format.week_span_months", "calendar.all_day", "calendar.week",
        "calendar.years", "calendar.untitled", "calendar.cut",
        "calendar.source_failed", "calendar.no_sources",
        "calendar.no_events",
        "calendar.spans_from", "calendar.spans_through", "calendar.spans_until",
    )
    # Retired with the day title [P46]: there is no title line to format, no
    # "Heute ·" to prefix it with and no dash on an empty day.
    GONE = ("format.day_title", "calendar.today", "calendar.empty")

    def test_every_key_exists_in_both_languages(self) -> None:
        for language in ("en", "de"):
            catalog = json.loads(
                (REPO_ROOT / "addon-epaperengine" / "templates" / "i18n" / f"{language}.json")
                .read_text("utf-8")
            )
            for key in self.KEYS:
                self.assertIn(key, catalog, f"{language}: {key}")
            for key in self.GONE:
                self.assertNotIn(key, catalog, f"{language}: {key} is retired")
            for index in range(7):
                self.assertIn(f"weekday.{index}", catalog)
                self.assertIn(f"weekday_short.{index}", catalog)
            for month in range(1, 13):
                self.assertIn(f"month.{month}", catalog)
                self.assertIn(f"month_short.{month}", catalog)

    def test_the_short_forms_are_written_out_not_sliced(self) -> None:
        """"Mo" happens to be "Montag"[:2] and English is Mon/Tue/Wed — a
        two-letter slice would be right in German and wrong here, silently
        [P9]. So both forms are catalogue entries, and this is what says so."""
        source = (REPO_ROOT / "addon-epaperengine" / "calendar_layout.py").read_text("utf-8")
        self.assertNotIn('weekday.{', source.replace("weekday_short.{", ""))
        for language, expected in (("en", "Wed"), ("de", "Mi")):
            self.assertEqual(wall_text.WallText(language)("weekday_short.2"), expected)

    def test_the_date_format_is_a_catalog_key_not_code(self) -> None:
        """[Festlegung P9] — month and weekday names are language, and the
        add-on image installs no C locale to take them from."""
        source = (REPO_ROOT / "addon-epaperengine" / "calendar_layout.py").read_text("utf-8")
        self.assertNotIn("%B", source)
        self.assertNotIn("%A", source)


class TestWeekBands(unittest.TestCase):
    """The grey band that opens a week [Festlegung P46, 2026-09-01, Wolfgang]."""

    def _days(self, first: date, count: int) -> list[cl.Day]:
        return [cl.Day(day=first + timedelta(n)) for n in range(count)]

    def test_a_band_stands_before_every_monday(self) -> None:
        # 2026-08-23 is a Sunday, so the 24th and the 31st are Mondays.
        items = cl.with_week_bands(self._days(TODAY, 10), TEXT)
        bands = [(n, item) for n, item in enumerate(items) if isinstance(item, cl.WeekBand)]
        self.assertEqual([item.monday for _, item in bands],
                         [date(2026, 8, 24), date(2026, 8, 31)])
        for index, _ in bands:
            self.assertEqual(items[index + 1].day.weekday(), 0)

    def test_a_run_that_starts_on_a_monday_gets_its_band(self) -> None:
        """Before *every* Monday, the first one included: an exception for the
        first item would leave a run beginning on a Monday unlabelled while one
        beginning on a Tuesday is labelled a day later."""
        items = cl.with_week_bands(self._days(date(2026, 8, 24), 3), TEXT)
        self.assertIsInstance(items[0], cl.WeekBand)

    def test_the_range_is_the_weeks_monday_not_the_day_it_stands_before(self) -> None:
        """The bug the mockup showed: the range was computed from whichever day
        the band happened to sit above, so the same week read "5. – 11. Oktober"
        in one column and "8. – 14. Oktober" in the next. Invisible until two
        bands for one week stood side by side."""
        band = cl.week_band(date(2026, 10, 5), TEXT)
        self.assertEqual(band.label, "KW 41")
        self.assertEqual(band.span, "5. – 11. Oktober")

    def test_a_week_that_crosses_a_month_names_both(self) -> None:
        self.assertEqual(cl.week_band(date(2026, 9, 28), TEXT).span, "28. Sep – 4. Okt")

    def test_the_week_number_is_the_iso_one(self) -> None:
        for monday, week in ((date(2026, 8, 24), 35), (date(2026, 12, 28), 53)):
            self.assertEqual(cl.week_band(monday, TEXT).label,
                             TEXT("calendar.week", week=week))

    def test_english_writes_the_range_its_own_way(self) -> None:
        english = wall_text.WallText("en")
        self.assertEqual(cl.week_band(date(2026, 10, 5), english).span, "October 5 – 11")
        self.assertEqual(cl.week_band(date(2026, 9, 28), english).span, "Sep 28 – Oct 4")

    def test_a_band_is_never_the_last_thing_in_a_column(self) -> None:
        """A heading whose week starts in the next column is a heading over
        nothing. So the band goes only where the Monday behind it goes — and
        it is charged for *before* the column is chosen, or the day behind it
        runs off the bottom where ``overflow: hidden`` eats it in silence.

        Swept over five loads because the case only bites when a band lands
        near the foot of a column: at three appointments a day it never does.
        """
        heights = [cl.COLUMN_H - cl.HEAD_H, cl.COLUMN_H, cl.COLUMN_H - 96]
        for count in range(5):
            with self.subTest(appointments=count):
                days = [
                    cl.Day(
                        day=TODAY + timedelta(n),
                        entries=[
                            cl.Entry(time_text="09:00", title_lines=["x"],
                                     location="", color="#000")
                            for _ in range(count)
                        ],
                    )
                    for n in range(60)
                ]
                columns = cl.fill_columns(cl.with_week_bands(days, TEXT), heights)
                for column, limit in zip(columns, heights):
                    if not column:
                        continue
                    self.assertIsInstance(column[-1], cl.Day)
                    self.assertLessEqual(column[-1].top + column[-1].height, limit)
                    for index, item in enumerate(column):
                        if isinstance(item, cl.WeekBand):
                            self.assertIsInstance(column[index + 1], cl.Day)

    def test_the_band_costs_what_the_model_reserves(self) -> None:
        self.assertEqual(cl.week_band(date(2026, 8, 24), TEXT).height,
                         cl.WEEK_BAND_H + cl.WEEK_BAND_GAP)

    def test_the_band_is_a_palette_colour_and_not_a_grey(self) -> None:
        """[P47] It shipped once at grey 200 and measured 63 % white on the real
        image: on six primaries a grey is mostly white, which is why it looked
        pale. A primary lands as itself — 93 % on the same measurement.

        This is the same rule the Sunday badge, the recipe title and the guest
        greeting follow; the test that keeps them honest is the same one.
        """
        self.assertIn(cl.WEEK_BAND_COLOR, cl.COLORS)
        self.assertEqual(cl.WEEK_BAND_BG, cl.COLORS[cl.WEEK_BAND_COLOR])
        self.assertIn(cl.WEEK_BAND_BG,
                      {"#%02x%02x%02x" % rgb for rgb in imaging.SPECTRA})

    def test_the_band_does_not_wear_a_colour_the_badges_wear(self) -> None:
        """Black is the badge and red is the Sunday badge [P46]. A band in
        either would put the same colour on two different things, and the wall
        is read from a metre away where only the colour arrives."""
        self.assertNotIn(cl.WEEK_BAND_BG, {cl.BADGE_BG, cl.BADGE_BG_SUNDAY})

    def test_the_band_text_is_not_yellow(self) -> None:
        """The one place §7 is strict: yellow as a *surface* is fine, yellow as
        28 px of text is not. So the band is yellow and its text is black —
        the reverse of that pairing was rendered and was visibly the weakest."""
        rule = re.search(r"      \.band \{([^}]*)\}",
                         TEMPLATE.read_text("utf-8"))
        assert rule is not None
        self.assertIn(cl.COLORS["yellow"], rule.group(1))
        for part in (".band .kw", ".band .span"):
            block = re.search(re.escape(part) + r" \{([^}]*)\}",
                              TEMPLATE.read_text("utf-8"))
            assert block is not None, part
            self.assertNotIn("color:", block.group(1))


class TestStripes(unittest.TestCase):
    """The colour of a multi-day appointment, running through [P46]."""

    def _page(self, events, now=datetime(2026, 8, 23, 12, 0)):
        return cl.build_page(
            {"calendar": {
                "sources": [{"entity_id": "calendar.a", "person": "W", "color": "blue"}],
                "events": {"calendar.a": events},
            }},
            now=now,
            text=TEXT,
        )

    def _span(self, start, end, summary="Urlaub"):
        return {"start": start, "end": end, "summary": summary}

    def test_a_span_is_one_unbroken_rectangle(self) -> None:
        page = self._page([self._span("2026-08-23T10:00:00+02:00",
                                      "2026-08-27T15:00:00+02:00")])
        stripes = page.stripes[0]
        self.assertEqual(len(stripes), 1)
        stripe = stripes[0]
        days = [item for item in page.columns[0] if item["kind"] == "day"]
        self.assertEqual(stripe["top"], days[0]["top"])
        self.assertEqual(stripe["top"] + stripe["height"],
                         days[4]["top"] + days[4]["badge_h"])
        self.assertEqual(stripe["color"], cl.COLORS["blue"])

    def test_it_runs_through_the_gaps_and_over_any_band(self) -> None:
        """It says the appointment did not stop; a stripe interrupted at every
        day boundary would say the opposite."""
        page = self._page([self._span("2026-08-23T10:00:00+02:00",
                                      "2026-08-27T15:00:00+02:00")])
        stripe = page.stripes[0][0]
        days = [item for item in page.columns[0] if item["kind"] == "day"]
        gaps = sum(day["height"] - day["badge_h"] for day in days[:4])
        band = sum(item["height"] for item in page.columns[0]
                   if item["kind"] == "band" and stripe["top"] < item["top"] < stripe["top"] + stripe["height"])
        self.assertGreater(gaps + band, 0)
        self.assertEqual(
            stripe["height"],
            sum(day["badge_h"] for day in days[:5]) + gaps + band,
        )

    def test_a_single_surviving_day_is_no_stripe(self) -> None:
        """An appointment whose span has been filtered down to one day is an
        ordinary entry again — and it keeps its entry."""
        page = self._page(
            [self._span("2026-08-18T10:00:00+02:00", "2026-08-23T15:00:00+02:00")],
            now=datetime(2026, 8, 23, 12, 0),
        )
        self.assertEqual(page.stripes[0], [])
        first = [item for item in page.columns[0] if item["kind"] == "day"][0]
        self.assertEqual(len(first["entries"]), 1)

    def test_two_overlapping_spans_share_the_lane(self) -> None:
        """Half each rather than one covering the other. Never below 4 px —
        that is where a stripe stops reading as a stripe."""
        page = self._page([
            self._span("2026-08-23T10:00:00+02:00", "2026-08-27T15:00:00+02:00", "A"),
            self._span("2026-08-25T10:00:00+02:00", "2026-08-29T15:00:00+02:00", "B"),
        ])
        stripes = page.stripes[0]
        self.assertEqual(len(stripes), 2)
        self.assertEqual({s["width"] for s in stripes}, {cl.STRIPE_W // 2})
        self.assertEqual(sorted(s["left"] for s in stripes), [0, cl.STRIPE_W // 2])
        for stripe in stripes:
            self.assertGreaterEqual(stripe["width"], 4)

    def test_two_spans_that_do_not_overlap_keep_the_whole_lane(self) -> None:
        page = self._page([
            self._span("2026-08-23T10:00:00+02:00", "2026-08-25T15:00:00+02:00", "A"),
            self._span("2026-08-27T10:00:00+02:00", "2026-08-29T15:00:00+02:00", "B"),
        ])
        for stripe in page.stripes[0]:
            self.assertEqual((stripe["left"], stripe["width"]), (0, cl.STRIPE_W))

    def test_the_lane_is_outside_the_badge(self) -> None:
        """It has to be: the per-entry colour bar sits inside the body, where
        the other appointments of the same day put theirs."""
        self.assertLessEqual(cl.STRIPE_W, cl.RAIL_W - cl.BADGE_W)
        self.assertEqual(cl.RAIL_W,
                         cl.STRIPE_W + cl.STRIPE_GAP + cl.BADGE_W + cl.BADGE_GAP)


class TestHeaderAndMonths(unittest.TestCase):
    """The month, said once at the start and again when it turns [P46]."""

    def _page(self, now):
        return cl.build_page(
            {"calendar": {
                "sources": [{"entity_id": "calendar.a", "person": "W", "color": "blue"}],
                "events": {"calendar.a": [_event(now.date() + timedelta(20))]},
            }},
            now=now,
            text=TEXT,
        )

    def test_the_header_names_the_month_of_the_first_day(self) -> None:
        self.assertEqual(self._page(datetime(2026, 8, 23, 12, 0)).header, "August 2026")

    def test_only_the_first_column_pays_for_it(self) -> None:
        """A full-width header would cost all three — the measurement P29 acted
        on. This one costs the first column and nothing else."""
        page = self._page(datetime(2026, 8, 23, 12, 0))
        self.assertEqual(page.head_h, cl.HEAD_H)
        first = [item for item in page.columns[0]][0]
        self.assertEqual(first["top"], 0)

    def test_the_first_of_a_month_carries_it_in_the_badge(self) -> None:
        """The header cannot follow a run of 30 days across a month boundary,
        and the badge is at least 98 px tall anyway — so it costs nothing."""
        page = self._page(datetime(2026, 8, 23, 12, 0))
        badges = {item["number"]: item["month"] for column in page.columns
                  for item in column if item["kind"] == "day"}
        self.assertEqual(badges["01"], "Sep")
        self.assertEqual(badges["31"], "")

    def test_the_first_day_of_the_run_says_it_in_the_header_only(self) -> None:
        page = self._page(datetime(2026, 9, 1, 12, 0))
        self.assertEqual(page.header, "September 2026")
        first = [item for column in page.columns for item in column
                 if item["kind"] == "day"][0]
        self.assertEqual((first["number"], first["month"]), ("01", ""))


class TestTemplateAgreesWithTheModel(unittest.TestCase):
    """The CSS sets what Python measured. Where they differ, the column clips."""

    CSS = TEMPLATE.read_text("utf-8")

    def _px(self, selector: str, prop: str) -> int:
        block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", self.CSS, re.S)
        assert block is not None, f"no rule for {selector}"
        found = re.search(prop + r":\s*(-?\d+)px", block.group(1))
        assert found is not None, f"{selector} has no {prop}"
        return int(found.group(1))

    def test_the_badge_is_the_size_the_model_reserves(self) -> None:
        """[P46] Number, weekday and the box they sit in — three numbers in two
        files, and a stylesheet that disagrees with the model overflows the
        badge silently, because it clips."""
        self.assertEqual(self._px(".badge", "width"), cl.BADGE_W)
        self.assertEqual(self._px(".badge .num", "font-size"), cl.BADGE_NUM_PX)
        self.assertEqual(self._px(".badge .wd", "font-size"), cl.BADGE_WD_PX)
        self.assertEqual(self._px(".badge .mon", "font-size"), cl.BADGE_MONTH_PX)
        rule = re.search(r"\.badge \{([^}]*)\}", self.CSS)
        assert rule is not None
        self.assertIn(f"background: {cl.BADGE_BG}", rule.group(1))
        self.assertIn(f"color: {cl.BADGE_FG}", rule.group(1))

    def test_the_two_badge_lines_fit_the_minimum_height(self) -> None:
        """98 px is the floor of an empty day; it has to hold both lines."""
        lines = self._px(".badge .num", "line-height") + self._px(".badge .wd", "line-height")
        self.assertLessEqual(lines, cl.BADGE_MIN_H)

    def test_the_month_line_fits_the_floor_it_raises(self) -> None:
        """The badge clips, so an empty 1st would simply have lost its month —
        on the one day of the month that has to carry it. Found by arithmetic;
        the wall would have shown a badge that looked entirely normal."""
        self.assertLessEqual(self._px(".badge .mon", "line-height"), cl.BADGE_MONTH_H)
        lines = (
            self._px(".badge .num", "line-height")
            + self._px(".badge .wd", "line-height")
            + self._px(".badge .mon", "line-height")
        )
        self.assertLessEqual(lines, cl.BADGE_MIN_H + cl.BADGE_MONTH_H)
        self.assertEqual(cl.Day(day=date(2026, 10, 1), month_text="Okt").badge_height,
                         cl.BADGE_MIN_H + cl.BADGE_MONTH_H)
        self.assertEqual(cl.Day(day=date(2026, 10, 2)).badge_height, cl.BADGE_MIN_H)

    def test_the_body_starts_behind_the_rail(self) -> None:
        """The one number that decides where every title wraps [P46]."""
        self.assertEqual(self._px(".body", "left"), cl.RAIL_W)
        self.assertEqual(self._px(".badge", "left"), cl.STRIPE_W + cl.STRIPE_GAP)

    def test_the_week_band_is_the_size_the_model_reserves(self) -> None:
        """[P46] Height and type; the 12 px of air below it are the model's."""
        self.assertEqual(self._px(".band", "height"), cl.WEEK_BAND_H)
        self.assertEqual(self._px(".band .kw", "font-size"), cl.WEEK_BAND_PX)
        self.assertEqual(self._px(".band .span", "font-size"), cl.WEEK_BAND_PX)
        rule = re.search(r"      \.band \{([^}]*)\}", self.CSS)
        assert rule is not None
        self.assertIn(f"background: {cl.WEEK_BAND_BG}", rule.group(1))

    def test_the_band_uses_the_full_column_width(self) -> None:
        """[Wolfgang: „horizontal die volle breite ausnutzen"] — the week number
        left, the date range right, and nothing between them but the band."""
        rule = re.search(r"      \.band \{([^}]*)\}", self.CSS)
        assert rule is not None
        self.assertIn("left: 0", rule.group(1))
        self.assertIn("right: 0", rule.group(1))
        self.assertIn("left: 14px", re.search(r"\.band \.kw \{([^}]*)\}", self.CSS).group(1))
        self.assertIn("right: 14px", re.search(r"\.band \.span \{([^}]*)\}", self.CSS).group(1))

    def test_every_block_is_placed_out_of_the_model(self) -> None:
        """A stripe crosses day blocks, so nothing may sit in normal flow: two
        stacking orders, one in CSS and one in Python, would drift [P46]."""
        for selector in (r"      \.day \{([^}]*)\}", r"      \.band \{([^}]*)\}"):
            rule = re.search(selector, self.CSS)
            assert rule is not None, selector
            self.assertIn("position: absolute", rule.group(1))
        self.assertIn('style="top: {{ item.top }}px"', self.CSS)

    def test_the_foot_is_flushed_to_the_outer_edge(self) -> None:
        """[P31] It sits in the last column, at the edge of the page."""
        foot = re.search(r"\.foot \{(.*?)\}", self.CSS, re.S)
        row = re.search(r"\.legend \.row \{(.*?)\}", self.CSS, re.S)
        assert foot is not None and row is not None
        self.assertIn("text-align: right", foot.group(1))
        self.assertIn("justify-content: flex-end", row.group(1))

    def test_the_page_reserves_nothing_at_the_bottom(self) -> None:
        main = re.search(r"      main \{(.*?)\}", self.CSS, re.S)
        assert main is not None
        found = re.search(r"padding:\s*([^;]+);", main.group(1))
        assert found is not None
        self.assertEqual(found.group(1).split()[2], "0")

    def test_the_gap_under_a_block_is_the_models_alone(self) -> None:
        """[P46] The 24 px used to be a CSS margin. Blocks are positioned out of
        the model now, so the gap lives in ``Day.height`` and nowhere else —
        a margin left behind here would add itself to it."""
        self.assertNotIn("margin", re.search(r"      \.day \{([^}]*)\}", self.CSS).group(1))
        day = cl.Day(day=TODAY)
        self.assertEqual(day.height - day.badge_height, cl.DAY_GAP)

    def test_the_empty_day_has_nothing_beside_the_badge(self) -> None:
        """P45 replaced "keine Termine" with a dash; P46 dropped the dash [P46].

        The words said nothing the empty space did not already say, and the
        dash said it in two pixels of stroke — 10 × 2 px that Floyd-Steinberg
        scatters. The badge is there whatever the day holds.
        """
        self.assertNotIn(".empty", self.CSS)
        self.assertNotIn("calendar.empty", self.CSS)

    def test_the_red_badge_is_painted_in_the_colour_the_model_names(self) -> None:
        """The model decides which day it is; the stylesheet only paints it.

        Two strings in two files [P45] — the class name and the hex. Either
        drifting is silent: a renamed class simply paints nothing.

        The class is ``red``, not ``sunday``, since P48: a public holiday wears
        the same ground, and the template asks ``item.red`` rather than
        ``item.sunday`` so that both reasons reach it.
        """
        self.assertIn(".badge.red", self.CSS)
        rule = re.search(r"\.badge\.red\s*\{([^}]*)\}", self.CSS)
        assert rule is not None
        self.assertIn(cl.BADGE_BG_SUNDAY, rule.group(1))
        self.assertEqual(cl.BADGE_BG_SUNDAY, cl.COLORS[cl.SUNDAY_COLOR])
        self.assertIn('{% if item.red %} red{% endif %}', self.CSS)
        # The old name must not survive anywhere: a leftover `.badge.sunday`
        # rule would paint Sundays through a class nothing sets any more.
        self.assertNotIn(".badge.sunday", self.CSS)

    def test_the_holiday_line_costs_what_the_model_charges(self) -> None:
        """[P48] 46 px of box against 38 px of line, and 38 px per further one.

        The badge grows to the body, so a stylesheet that set a taller line than
        the model budgeted would push the last appointment of the day past the
        badge it stands beside — and the badge clips.
        """
        self.assertEqual(self._px(".holiday", "font-size"), cl.HOLIDAY_PX)
        self.assertEqual(self._px(".holiday", "line-height"), cl.HOLIDAY_LINE_H)
        self.assertLessEqual(self._px(".holiday", "line-height"), cl.HOLIDAY_H)
        rule = re.search(r"      \.holiday \{([^}]*)\}", self.CSS)
        assert rule is not None
        self.assertIn(f"color: {cl.BADGE_BG_SUNDAY}", rule.group(1))
        self.assertIn('style="height: {{ holiday.height }}px"', self.CSS)

    def test_the_holiday_line_carries_no_time_and_no_bar(self) -> None:
        """[Festlegung P48] The whole point of the separate line: a holiday has
        no hour anybody can be late for, and belongs to no source."""
        block = re.search(
            r'<div class="holiday".*?</div>\s*\{%- endfor %\}', self.CSS, re.S
        )
        assert block is not None, "the holiday block is gone from the template"
        self.assertNotIn('class="bar"', block.group(0))
        self.assertNotIn('class="time"', block.group(0))

    def test_the_cut_marker_costs_what_the_model_charges(self) -> None:
        self.assertEqual(self._px(".cut", "height"), cl.CUT_H)

    def test_the_title_line_advance_matches(self) -> None:
        self.assertEqual(self._px(".what .line", "line-height"), cl.ENTRY_LINE_H)

    def test_the_title_column_is_where_the_model_wrapped_it(self) -> None:
        """Since P46 the width is not written down anywhere: the title box runs
        to the right edge of the body, and the body starts behind the rail. So
        the number the model wrapped at is the one the browser will use, and
        there is no second copy of it to drift."""
        self.assertEqual(self._px(".what", "left"), cl.TITLE_DX)
        rule = re.search(r"\.what \{([^}]*)\}", self.CSS)
        assert rule is not None
        self.assertIn("right: 0", rule.group(1))
        self.assertIn("right: 0", re.search(r"\.body \{([^}]*)\}", self.CSS).group(1))
        self.assertEqual(cl.COLUMN_W - self._px(".body", "left") - cl.TITLE_DX, cl.TITLE_W)

    def test_the_time_column_is_the_measured_one(self) -> None:
        self.assertEqual(self._px(".time", "width"), cl.TIME_W)
        self.assertEqual(self._px(".time", "font-size"), cl.TIME_PX)

    def test_the_columns_are_the_ones_the_specification_fixes(self) -> None:
        self.assertEqual(self._px(".column", "width"), cl.COLUMN_W)
        self.assertIn(f"gap: {cl.GUTTER}px", self.CSS)

    def test_no_rule_on_the_page_is_a_grey_hairline(self) -> None:
        """Measured 2026-08-22: grey at 2 px dithers into a dotted trail.

        Since P31 the only rule left is the gutter between the columns; the
        loop guards any that come back.
        """
        for rule in re.findall(r"border(?:-bottom)?:\s*\d+px solid ([^;]+);", self.CSS):
            self.assertEqual(rule.strip(), "#000")
        self.assertIn("background: #000", self.CSS)

    def test_the_page_carries_no_header_at_all(self) -> None:
        """[P29] — the whole element is gone, not merely emptied."""
        self.assertNotIn("<header", self.CSS)
        self.assertNotIn("page.headline", self.CSS)

    def test_every_foot_line_is_the_height_the_model_reserves(self) -> None:
        self.assertEqual(self._px(".legend .row", "height"), cl.FOOT_LINE)
        for selector in (".legend .who", ".stamp", ".notes .line"):
            self.assertEqual(self._px(selector, "line-height"), cl.FOOT_LINE)

    def test_the_legend_swatch_gaps_are_the_ones_the_model_measured_with(self) -> None:
        row = re.search(r"\.legend \.row \{(.*?)\}", self.CSS, re.S)
        who = re.search(r"\.legend \.who \{(.*?)\}", self.CSS, re.S)
        assert row is not None and who is not None
        self.assertIn(f"gap: {cl.LEGEND_GAP}px", row.group(1))
        self.assertIn(f"gap: {cl.LEGEND_CHIP_GAP}px", who.group(1))
        self.assertEqual(self._px(".legend .chip", "width"), cl.LEGEND_CHIP_W)


if __name__ == "__main__":
    unittest.main()
