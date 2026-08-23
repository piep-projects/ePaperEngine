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


class TestBirthYear(unittest.TestCase):
    def test_the_description_carries_the_year(self) -> None:
        self.assertEqual(cl.birth_year("Erika Müller", "1946"), ("Erika Müller", 1946))

    def test_a_bracket_in_the_title_is_the_documented_fallback(self) -> None:
        """kalenderkonzept §6.1: for the day the dialog offers no description."""
        self.assertEqual(cl.birth_year("Erika Müller (1946)", ""), ("Erika Müller", 1946))

    def test_the_bracket_is_cut_off_the_displayed_name(self) -> None:
        title, _ = cl.birth_year("Erika Müller (1946)", "")
        self.assertNotIn("(", title)

    def test_a_note_in_the_description_is_not_a_year(self) -> None:
        self.assertEqual(cl.birth_year("Erika", "ruft immer an"), ("Erika", None))

    def test_an_implausible_number_is_not_a_year(self) -> None:
        self.assertEqual(cl.birth_year("Erika", "42"), ("Erika", None))

    def test_the_description_wins_over_the_title(self) -> None:
        self.assertEqual(cl.birth_year("Erika (1900)", "1946"), ("Erika (1900)", 1946))

    def test_the_age_is_a_difference_of_years(self) -> None:
        """And that is the whole 29 February answer — the source picks the day."""
        self.assertEqual(cl.age_on(date(2026, 2, 28), 1946), 80)
        self.assertEqual(cl.age_on(date(2026, 3, 1), 1946), 80)


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

    def test_a_multi_day_entry_is_repeated_on_every_day_it_covers(self) -> None:
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
        self.assertEqual([len(day.entries) for day in days], [1, 1, 1])

    def test_a_gap_between_two_appointments_is_shown_as_an_empty_day(self) -> None:
        days = cl.build_days(
            [_source()],
            {"calendar.a": [_event(TODAY), _event(TODAY + timedelta(2))]},
            today=TODAY,
            text=TEXT,
        )
        self.assertEqual([bool(day.entries) for day in days], [True, False, True])
        self.assertEqual(days[1].height, cl.DAY_HEAD_H + cl.EMPTY_DAY_H + cl.DAY_GAP)

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

    def test_today_is_marked_and_titled_as_today(self) -> None:
        days = cl.build_days([_source()], {"calendar.a": [_event(TODAY)]}, today=TODAY, text=TEXT)
        self.assertTrue(days[0].today)
        self.assertTrue(days[0].title.startswith("Heute"))

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
        column. Since P30 the column is 805 px, so the figure is 35 — the model
        is unchanged, the column it is applied to grew."""
        self.assertEqual(cl.TITLE_CHARS, cl.chars_per_line(cl.TITLE_PX, cl.COLUMN_W - cl.TITLE_DX))
        self.assertIn(cl.TITLE_CHARS, range(33, 38))


class TestBirthdayEntries(unittest.TestCase):
    def _days(self, description="1985", summary="Anna Berger"):
        return cl.build_days(
            [_source(kind=cl.KIND_BIRTHDAYS, color="red")],
            {"calendar.a": [
                _event(TODAY, "09:00", "09:15", summary, description=description)
            ]},
            today=TODAY,
            text=TEXT,
        )

    def test_the_age_is_appended(self) -> None:
        entry = self._days()[0].entries[0]
        self.assertEqual(entry.title_lines[0], "Anna Berger — wird 41")

    def test_a_missing_year_costs_the_age_not_the_entry(self) -> None:
        entry = self._days(description="")[0].entries[0]
        self.assertEqual(entry.title_lines[0], "Anna Berger")

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


class TestColumns(unittest.TestCase):
    def _day(self, entries: int, day: date | None = None) -> cl.Day:
        return cl.Day(
            day=day or TODAY,
            title="Tag",
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
        self.assertEqual(cl.COLUMN_H, 1376)

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
            out.append(cl.Day(day=day, title="Tag", entries=entries))
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
        """Legend row, timestamp, 24 px of air — measured, not assumed, because
        the foot is anchored to the bottom and a line too many grows *upwards*
        into the last appointment."""
        page = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        self.assertEqual(page.foot_h, cl.FOOT_GAP + 2 * cl.FOOT_LINE)

    def test_the_stamp_travels_with_the_page(self) -> None:
        page = cl.build_page(
            self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT, stamp="X"
        )
        self.assertEqual(page.stamp, "X")

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
        August 23" at 64 px *and* "Today · Sunday, August 23" right under it."""
        page = cl.build_page(self._document(), now=datetime(2026, 8, 23, 12, 0), text=TEXT)
        titles = [day["title"] for column in page.columns for day in column]
        self.assertEqual(sum(1 for t in titles if "23. August" in t), 1)
        self.assertTrue(titles[0].startswith("Heute"))


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
        "format.day_title", "format.clock", "calendar.today", "calendar.all_day",
        "calendar.empty", "calendar.turns", "calendar.untitled", "calendar.cut",
        "calendar.updated", "calendar.source_failed", "calendar.no_sources",
        "calendar.no_events",
    )

    def test_every_key_exists_in_both_languages(self) -> None:
        for language in ("en", "de"):
            catalog = json.loads(
                (REPO_ROOT / "addon-epaperengine" / "templates" / "i18n" / f"{language}.json")
                .read_text("utf-8")
            )
            for key in self.KEYS:
                self.assertIn(key, catalog, f"{language}: {key}")
            for index in range(7):
                self.assertIn(f"weekday.{index}", catalog)
            for month in range(1, 13):
                self.assertIn(f"month.{month}", catalog)

    def test_the_date_format_is_a_catalog_key_not_code(self) -> None:
        """[Festlegung P9] — month and weekday names are language, and the
        add-on image installs no C locale to take them from."""
        source = (REPO_ROOT / "addon-epaperengine" / "calendar_layout.py").read_text("utf-8")
        self.assertNotIn("%B", source)
        self.assertNotIn("%A", source)


class TestTemplateAgreesWithTheModel(unittest.TestCase):
    """The CSS sets what Python measured. Where they differ, the column clips."""

    CSS = TEMPLATE.read_text("utf-8")

    def _px(self, selector: str, prop: str) -> int:
        block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", self.CSS, re.S)
        assert block is not None, f"no rule for {selector}"
        found = re.search(prop + r":\s*(-?\d+)px", block.group(1))
        assert found is not None, f"{selector} has no {prop}"
        return int(found.group(1))

    def test_the_day_head_costs_what_the_model_charges(self) -> None:
        head = self._px(".day h2", "height") + 2 + 14  # line, rule, air
        self.assertEqual(head, cl.DAY_HEAD_H)

    def test_the_gap_under_a_block_matches(self) -> None:
        self.assertIn(f"margin: 0 0 {cl.DAY_GAP}px 0", self.CSS)

    def test_the_empty_day_costs_what_the_model_charges(self) -> None:
        self.assertEqual(self._px(".empty", "height"), cl.EMPTY_DAY_H)

    def test_the_cut_marker_costs_what_the_model_charges(self) -> None:
        self.assertEqual(self._px(".cut", "height"), cl.CUT_H)

    def test_the_title_line_advance_matches(self) -> None:
        self.assertEqual(self._px(".what .line", "line-height"), cl.ENTRY_LINE_H)

    def test_the_title_column_is_where_the_model_wrapped_it(self) -> None:
        self.assertEqual(self._px(".what", "left"), cl.TITLE_DX)
        self.assertEqual(self._px(".what", "width"), cl.COLUMN_W - cl.TITLE_DX)

    def test_the_time_column_is_the_measured_one(self) -> None:
        self.assertEqual(self._px(".time", "width"), cl.TIME_W)
        self.assertEqual(self._px(".time", "font-size"), cl.TIME_PX)

    def test_the_columns_are_the_ones_the_specification_fixes(self) -> None:
        self.assertEqual(self._px(".column", "width"), cl.COLUMN_W)
        self.assertIn(f"gap: {cl.GUTTER}px", self.CSS)

    def test_no_rule_on_the_page_is_a_grey_hairline(self) -> None:
        """Measured 2026-08-22: grey at 2 px dithers into a dotted trail."""
        for rule in re.findall(r"border-bottom:\s*\d+px solid ([^;]+);", self.CSS):
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
