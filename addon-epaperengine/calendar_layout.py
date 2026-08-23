"""How the appointments are fitted onto the wall (FSD §8.1, Mockup 08-wand-kalender).

The policy, not the drawing — like ``recipe_layout.py``, ``outage.py`` and the
integration's ``resolve.py``: a pure function over plain data, testable without
Chromium, a panel or a calendar server.

**Every measurement here is the mockup's**, read out of
``tools/mockup-gen/pages_wand.py`` rather than re-invented: three columns of
773 px, day title 36 px bold, appointment 32 px, time 26 px in 185 px, location
24 px, colour bar 6 px. Two numbers deviate and both deviations are measured,
not preferred:

* the rule under a day title is **black**, not the mockup's 2 px ``#aaaaaa``.
  A grey hairline does not survive the panel — dithered against six primaries it
  came out 67 % / 33 % black, a dotted trail (measured 2026-08-22 on the first
  real recipe image, and the same correction the recipe gutter got);
* grey **text** stays grey. It is the thin *lines* that fall apart, not the
  areas — FSD §7 allows grey down to 170 as a surface.

**What the specification fixes** [Festlegung 2026-08-20, FSD §8.1]: the view
shows as many entries as fit — no fixed horizon. Day block after day block, as
long as the next one fits **completely**; what does not fit in one column runs
into the next. Days without appointments are shown, so the run of days has no
holes. The legend sits in the header next to the date, which saves about 120 px
a column.

**The one case the specification does not cover**: a single day taller than a
whole column — eight appointments with wrapped titles are 1.200 px against
1.140 px of column. "Only complete blocks" would show *nothing* of that day and
nothing after it either. So a block that does not fit even an empty column is
placed anyway and **cut with a visible marker**, the same trade the recipes
make [P13/P14]: cutting is bad, cutting silently is the bug.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from recipe_layout import CHAR_RATIO, wrap

# --- the canvas, 1:1 with the mockup ------------------------------------------
CANVAS_W = 2560
CANVAS_H = 1440
MARGIN = 80
GUTTER = 40
CONTENT_W = CANVAS_W - 2 * MARGIN  # 2400
COLUMN_W = 773                     # (2560 - 2*80 - 2*40) / 3 [Festlegung 2026-08-20]
COLUMNS = 3

# The header: 64 px date on the left, legend and timestamp on the right, a 3 px
# black rule at y = 180. The columns start 140 px below the margin.
HEADER_RULE_Y = MARGIN + 100
COLUMN_TOP = MARGIN + 140          # 220
COLUMN_BOTTOM = CANVAS_H - MARGIN  # 1360
COLUMN_H = COLUMN_BOTTOM - COLUMN_TOP  # 1140

# A failing source costs one line under the header rule — and only then
# (FSD §8.1 has no room to spare, and a note nobody needs is 44 px of
# appointments). The columns move down by exactly that much.
NOTE_H = 44

# --- the day block ------------------------------------------------------------
# From ``kal_spalte`` in the mockup generator: title, 52 px advance, a rule,
# 14 px of air; every appointment 84 px plus 38 px per extra title line; 24 px
# under the block.
DAY_TITLE_PX = 36
DAY_HEAD_H = 52 + 14   # 66 — title advance plus the rule and the air under it
DAY_GAP = 24           # air below a finished block
EMPTY_DAY_H = 60       # "no appointments" in one 28 px line
EMPTY_DAY_PX = 28

ENTRY_H = 84           # one appointment with a one-line title
ENTRY_LINE_H = 38      # every further title line
TIME_PX = 26           # 26, not 28: 28 px no longer fits beside the title (FSD §8.1)
TIME_W = 185
TITLE_PX = 32
TITLE_DX = 215         # where the title starts inside the column
LOCATION_PX = 24
BAR_W = 6              # [Festlegung C8] — 2 px is the proven floor, 6 px reads as a bar

CUT_H = 46             # the "cut" marker under a block that did not fit

# The six Spectra primaries, minus white — a white bar on a white page is no
# bar. Same rule as the guest greeting [P23]: a colour off the palette is
# reproduced by dithering it out of these, and a 6 px bar of dithered near-blue
# is a speckle, not a mark. ``imaging.SPECTRA`` is the source; the tests hold
# the two together.
COLORS: dict[str, str] = {
    "black": "#000000",
    "red": "#dc1e1e",
    "yellow": "#f0c81e",
    "blue": "#1e3cb4",
    "green": "#1e8c46",
}
DEFAULT_COLOR = "blue"

# A source is either a diary or a birthday list. The distinction is not
# cosmetic: a birthday carries an age, shows only its start time, and stays on
# the wall all day even when "hide today's past entries" is on — it is not an
# appointment somebody can be late for.
KIND_EVENTS = "events"
KIND_BIRTHDAYS = "birthdays"
KINDS = (KIND_EVENTS, KIND_BIRTHDAYS)

# What counts as a birth year in a description. Narrow on purpose: anything else
# in that field is a note, and "turns 2019" under a name would be worse than no
# age at all.
YEAR_MIN, YEAR_MAX = 1000, 2999


# --- data ---------------------------------------------------------------------
@dataclass
class Source:
    """One configured calendar: which entity, whose it is, what colour it wears."""

    entity_id: str
    person: str = ""
    color: str = DEFAULT_COLOR
    kind: str = KIND_EVENTS

    @property
    def hex(self) -> str:
        return COLORS.get(self.color, COLORS[DEFAULT_COLOR])

    @property
    def label(self) -> str:
        """What the legend says. Falls back to the object id, never to blank."""
        return self.person or self.entity_id.split(".", 1)[-1].replace("_", " ")


@dataclass
class Entry:
    """One appointment, measured and ready for the template."""

    time_text: str
    title_lines: list[str]
    location: str
    color: str          # hex, resolved
    all_day: bool = False
    sort_key: tuple[int, str, str] = (0, "", "")

    @property
    def height(self) -> int:
        return ENTRY_H + ENTRY_LINE_H * (max(len(self.title_lines), 1) - 1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "time": self.time_text,
            "title_lines": self.title_lines,
            "location": self.location,
            "color": self.color,
            "all_day": self.all_day,
            "height": self.height,
        }


@dataclass
class Day:
    """One day block: a title and everything under it."""

    day: date
    title: str
    entries: list[Entry] = field(default_factory=list)
    today: bool = False
    cut: int = 0  # appointments that had to be dropped to make it fit

    @property
    def height(self) -> int:
        body = sum(entry.height for entry in self.entries) or EMPTY_DAY_H
        return DAY_HEAD_H + body + DAY_GAP + (CUT_H if self.cut else 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "entries": [entry.as_dict() for entry in self.entries],
            "empty": not self.entries,
            "today": self.today,
            "cut": self.cut,
            "height": self.height,
        }


# --- measuring ----------------------------------------------------------------
def chars_per_line(font_px: int, width: int) -> int:
    """DejaVu Sans characters across ``width``. The recipe model, same constant."""
    return max(round(width / (CHAR_RATIO * font_px)), 1)


TITLE_CHARS = chars_per_line(TITLE_PX, COLUMN_W - TITLE_DX)  # ~32, FSD §8.1 says ~31


def title_lines(text: str) -> list[str]:
    """Wrap an appointment title the way the column will break it."""
    return wrap(text, TITLE_CHARS) or [""]


# --- reading what Home Assistant handed over ----------------------------------
def _parse(value: Any) -> tuple[datetime | date, bool] | None:
    """``calendar.get_events`` hands out either a date or a datetime.

    A date-only value **is** the all-day marker — there is no separate flag in
    the five fields FSD §9.2/kalenderkonzept §3.1 allow, so the shape of the
    string is the signal.
    """
    if isinstance(value, datetime):
        return value, False
    if isinstance(value, date):
        return value, True
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text), True
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text), False
    except ValueError:
        return None


def _local_date(moment: datetime | date) -> date:
    return moment.date() if isinstance(moment, datetime) else moment


def birth_year(summary: str, description: str) -> tuple[str, int | None]:
    """``("Erika Müller", 1946)`` — the title as it should read, plus the year.

    Two carriers, in the order kalenderkonzept §6.1 fixes them: the
    **description**, because then nothing technical shows up in a phone's
    calendar app, and a trailing ``(1946)`` in the **title** as the fallback for
    the day Home Assistant's dialog offers no description field. The bracket is
    cut off the displayed title — it was a workaround, not a name.
    """
    stripped = (description or "").strip()
    if stripped.isdigit() and YEAR_MIN <= int(stripped) <= YEAR_MAX:
        return summary.strip(), int(stripped)

    title = summary.strip()
    if title.endswith(")") and "(" in title:
        head, _, tail = title.rpartition("(")
        candidate = tail[:-1].strip()
        if candidate.isdigit() and YEAR_MIN <= int(candidate) <= YEAR_MAX:
            return head.strip(), int(candidate)
    return title, None


def age_on(when: date, year: int) -> int:
    """The age the birthday child reaches on ``when``.

    A plain difference of years, and that is the whole answer to the
    29 February question kalenderkonzept §7.2 raises: which day a yearly
    recurrence lands on in a common year is decided by the calendar *source*
    (Local Calendar, CalDAV, Google), and whichever it picks, the year
    difference is the same. There is nothing for the renderer to special-case.
    """
    return when.year - year


# --- building the day blocks --------------------------------------------------
def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).casefold()


def build_days(
    sources: list[Source],
    events: dict[str, list[dict[str, Any]]],
    *,
    today: date,
    now: datetime | None = None,
    horizon: date | None = None,
    show_empty_days: bool = True,
    show_past_today: bool = False,
    text: Any = None,
) -> list[Day]:
    """Turn the render document's raw events into ordered, measured day blocks.

    ``text`` is the wall catalog (``wall_text.WallText``); it is optional so the
    tests can measure geometry without carrying the catalogs around.
    """
    say = text or (lambda key, **fields: key)
    by_day: dict[date, list[Entry]] = {}

    for source in sources:
        for raw in events.get(source.entity_id) or []:
            for day, entry in _entries_for(raw, source, today, now, show_past_today, say):
                if day < today or (horizon is not None and day > horizon):
                    continue
                by_day.setdefault(day, []).append(entry)

    # The run of days is gapless *between* appointments, not after the last one:
    # trailing empty days are filler, and filler is measured in appointments
    # that did not fit.
    last = max(by_day) if by_day else today
    days: list[Day] = []
    cursor = today
    while cursor <= last:
        entries = sorted(by_day.get(cursor, []), key=lambda item: item.sort_key)
        if entries or show_empty_days or cursor == today:
            days.append(
                Day(
                    day=cursor,
                    title=day_title(cursor, today, say),
                    entries=entries,
                    today=cursor == today,
                )
            )
        cursor += timedelta(days=1)
    return days


def _entries_for(
    raw: dict[str, Any],
    source: Source,
    today: date,
    now: datetime | None,
    show_past_today: bool,
    say: Any,
) -> list[tuple[date, Entry]]:
    """One raw event → the day(s) it belongs on, with the drawn entry."""
    start = _parse(raw.get("start"))
    end = _parse(raw.get("end"))
    if start is None:
        return []
    start_value, all_day = start
    end_value = end[0] if end else None

    summary = str(raw.get("summary") or "").strip()
    location = str(raw.get("location") or "").strip()
    description = str(raw.get("description") or "")
    if not summary:
        summary = say("calendar.untitled")

    if source.kind == KIND_BIRTHDAYS:
        summary, year = birth_year(summary, description)
        if year is not None:
            summary = f"{summary} {say('calendar.turns', age=age_on(_local_date(start_value), year))}"
        # A birthday has no location worth the 32 px, and its 09:00–09:15 is a
        # slot, not a duration (kalenderkonzept §6.1) — only the start shows.
        location = ""

    # An all-day event covers every day of its span; ``end`` is exclusive, the
    # way iCalendar writes it. A timed event that runs past midnight stays on
    # the day it starts — showing "23:00–01:00" again on the next morning would
    # be a second appointment as far as anyone reading the wall is concerned.
    days: list[date] = [_local_date(start_value)]
    if all_day and isinstance(end_value, date):
        span = (_local_date(end_value) - days[0]).days
        days = [days[0] + timedelta(n) for n in range(max(span, 1))]

    out: list[tuple[date, Entry]] = []
    for day in days:
        if not _visible(day, today, now, all_day, source, end_value, show_past_today):
            continue
        if all_day:
            when = say("calendar.all_day")
            order = (0, "", _fold(summary))
        elif source.kind == KIND_BIRTHDAYS or not isinstance(end_value, datetime):
            when = _clock(start_value, say)
            order = (1, when, _fold(summary))
        else:
            when = f"{_clock(start_value, say)}–{_clock(end_value, say)}"
            order = (1, _clock(start_value, say), _fold(summary))
        out.append(
            (
                day,
                Entry(
                    time_text=when,
                    title_lines=title_lines(summary),
                    location=location,
                    color=source.hex,
                    all_day=all_day,
                    sort_key=order,
                ),
            )
        )
    return out


def _visible(
    day: date,
    today: date,
    now: datetime | None,
    all_day: bool,
    source: Source,
    end_value: datetime | date | None,
    show_past_today: bool,
) -> bool:
    """Whether an entry of ``day`` is drawn at all.

    Only today is ever filtered, and only when the household asked for it. Two
    exemptions, and both are the difference between a rule and a trap: an
    **all-day** entry has no past to be in, and a **birthday** would otherwise
    vanish off the wall at 09:16 on the very morning it is meant to be read.
    """
    if show_past_today or day != today or now is None:
        return True
    if all_day or source.kind == KIND_BIRTHDAYS:
        return True
    if isinstance(end_value, datetime):
        # ``get_events`` answers with offsets; a naive ``now`` from a test is
        # compared naively rather than made to raise.
        if (end_value.tzinfo is None) != (now.tzinfo is None):
            return end_value.replace(tzinfo=None) > now.replace(tzinfo=None)
        return end_value > now
    return True


def _clock(value: datetime | date, say: Any) -> str:
    """The time of day, in the notation the language writes it.

    A catalog key like the date format [Festlegung P9] — the wall is the one
    surface where a 12-hour clock would be a translation and not a setting.
    """
    if isinstance(value, datetime):
        return value.strftime(say("format.clock"))
    return ""


def written_date(day: date, say: Any) -> str:
    """``Mittwoch, 20. August`` — every part of it out of the catalog.

    The date format is a catalog key, not code [Festlegung P9]: month and
    weekday names are language, and ``strftime`` would take them from a C locale
    the add-on image does not install.
    """
    return say(
        "format.day_title",
        weekday=say(f"weekday.{day.weekday()}"),
        day=day.day,
        month=say(f"month.{day.month}"),
        year=day.year,
    )


def day_title(day: date, today: date, say: Any) -> str:
    """``Heute · Mittwoch, 20. August`` for today, the plain date otherwise."""
    written = written_date(day, say)
    return say("calendar.today", date=written) if day == today else written


# --- filling the columns ------------------------------------------------------
def fill_columns(days: list[Day], column_h: int = COLUMN_H) -> list[list[Day]]:
    """Day block after day block, as long as the next one fits **completely**.

    [Festlegung 2026-08-20, FSD §8.1.] What is left over when the third column
    is full is simply not shown — the query window is the ceiling of the
    *query*, not of the display.
    """
    columns: list[list[Day]] = [[] for _ in range(COLUMNS)]
    index, used = 0, 0
    for day in days:
        block = _fit(day, column_h)
        if block is None:
            continue
        while index < COLUMNS and used + block.height > column_h:
            index += 1
            used = 0
        if index >= COLUMNS:
            break
        columns[index].append(block)
        used += block.height
    return columns


def _fit(day: Day, column_h: int) -> Day | None:
    """Cut a day that is taller than a whole column, and say so.

    The only case FSD §8.1 leaves open. Dropping the block would take every
    later day with it and leave no trace on the wall; dropping the tail leaves
    the day readable and the cut counted.
    """
    if day.height <= column_h:
        return day
    kept = list(day.entries)
    dropped = 0
    while kept and Day(day.day, day.title, kept, day.today, dropped + 1).height > column_h:
        kept.pop()
        dropped += 1
    if not kept:
        return None
    return Day(day.day, day.title, kept, day.today, dropped)


# --- the whole page -----------------------------------------------------------
@dataclass
class Page:
    """What the template draws."""

    headline: str
    legend: list[dict[str, str]]
    columns: list[list[dict[str, Any]]]
    notes: list[str]
    bar_px: int
    column_top: int
    shown_days: int
    shown_entries: int
    dropped_days: int
    cut_entries: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "legend": self.legend,
            "columns": self.columns,
            "notes": self.notes,
            "bar_px": self.bar_px,
            "column_top": self.column_top,
        }


def build_page(
    document: dict[str, Any],
    *,
    now: datetime,
    text: Any = None,
) -> Page:
    """The render document's ``calendar`` section → one measured page."""
    say = text or (lambda key, **fields: key)
    section = document.get("calendar") or {}
    sources = [read_source(item) for item in (section.get("sources") or [])]
    sources = [source for source in sources if source.entity_id]

    today = now.date()
    horizon_days = max(int(section.get("query_days_events") or 30), 1)
    days = build_days(
        sources,
        dict(section.get("events") or {}),
        today=today,
        now=now,
        horizon=today + timedelta(days=horizon_days),
        show_empty_days=bool(section.get("show_empty_days", True)),
        show_past_today=bool(section.get("show_past_today", False)),
        text=say,
    )

    notes = []
    failed = dict(section.get("failed") or {})
    for source in sources:
        if source.entity_id in failed:
            notes.append(say("calendar.source_failed", person=source.label))
    if not sources:
        notes.append(say("calendar.no_sources"))
    elif not days:
        notes.append(say("calendar.no_events"))

    top = COLUMN_TOP + (NOTE_H if notes else 0)
    columns = fill_columns(days, COLUMN_H - (NOTE_H if notes else 0))
    shown = [day for column in columns for day in column]

    bar_px = int(section.get("color_bar_px") or BAR_W)
    return Page(
        headline=written_date(today, say),
        legend=[{"label": source.label, "hex": source.hex} for source in sources],
        columns=[[day.as_dict() for day in column] for column in columns],
        notes=notes,
        bar_px=max(min(bar_px, 24), 2),
        column_top=top,
        shown_days=len(shown),
        shown_entries=sum(len(day.entries) for day in shown),
        dropped_days=len(days) - len(shown),
        cut_entries=sum(day.cut for day in shown),
    )


def read_source(item: dict[str, Any]) -> Source:
    """One configured source, with every field defended against an old store."""
    kind = str(item.get("kind") or KIND_EVENTS)
    color = str(item.get("color") or DEFAULT_COLOR)
    return Source(
        entity_id=str(item.get("entity_id") or "").strip(),
        person=str(item.get("person") or "").strip(),
        color=color if color in COLORS else DEFAULT_COLOR,
        kind=kind if kind in KINDS else KIND_EVENTS,
    )
