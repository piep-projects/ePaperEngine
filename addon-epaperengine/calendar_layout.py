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

from anniversaries import strip_suffix, suffix_pattern, year_in_title
from recipe_layout import CHAR_RATIO, wrap

# --- the canvas, 1:1 with the mockup ------------------------------------------
CANVAS_W = 2560
CANVAS_H = 1440

# **32 px, not the mockup's 80** [Festlegung P30, 2026-08-23, Wolfgang]. The
# 80 px came in with the mockup as a Satzspiegel and were carried into FSD §7 as
# the basis of its character table — and `projektidee.md` §4 marks the whole
# block "Vorschlag, nicht gemessen". They left **17 % of the panel unused**.
#
# What each direction actually buys, measured over eight loads (0–7 appointments
# a day):
#
#   vertical    80 → 32 px: 184 → 219 appointments, **+19 %**. This is the whole
#               gain — day blocks stack, so column height is what counts
#   horizontal  80 → 32 px: the column grows 773 → 805 px, a title line 33 → 35
#               characters, and the number of wrapped titles in a real day's
#               worth stays at **1 of 24**. The column gives up 215 px to the
#               bar and the time before a title starts, and the gutter is fixed.
#               Horizontally this is composition, not capacity
#
# The panel shows 1:1 with no overscan [belegt, FSD §3.3], so nothing is lost
# off the edge. What 32 px looks like against the device frame is an eye at the
# wall, and it was one.
MARGIN = 32
# **No margin at the bottom** [Festlegung P31, 2026-08-23, Wolfgang]. The
# calendar is a list that runs out somewhere, not a composed page with a
# baseline — whatever white is left under the last block is left over, not
# designed. Costs nothing to give back: the columns simply end at the canvas.
# The recipe view keeps its 32 px all round; it is a sheet, not a list.
MARGIN_BOTTOM = 0
GUTTER = 40
CONTENT_W = CANVAS_W - 2 * MARGIN  # 2496
COLUMNS = 3
# Derived rather than written down: the mockup's 773 px was (2400 − 80) / 3, and
# a literal here would silently disagree with the margin above.
COLUMN_W = (CONTENT_W - (COLUMNS - 1) * GUTTER) // COLUMNS  # 805

# **There is no header** [Festlegung P29, 2026-08-23, Wolfgang]. The mockup put
# the date at 64 px across the top and the legend beside it, and the first real
# image showed what that costs: the page said "Sunday, August 23" in the header
# and "Today · Sunday, August 23" as the first day title — the same date twice —
# and the 140 px it took came off **all three** columns.
#
# So the date is said once, by the day title that has to be there anyway, and
# legend and timestamp move to the **foot of the third column**. Columns one and
# two run the full height; only the third pays, and only for the foot.
# Measured over eight synthetic loads (0–7 appointments a day): 184 appointments
# against 162, **+14 %**. The gain is lumpy — whole day blocks are the unit, so
# at 2, 3, 5 and 7 a day it buys nothing and at 4 and 6 it buys 8 and 12.
COLUMN_TOP = MARGIN                       # 32
COLUMN_BOTTOM = CANVAS_H - MARGIN_BOTTOM  # 1440
COLUMN_H = COLUMN_BOTTOM - COLUMN_TOP     # 1408

# The foot of the third column. Every line is 36 px (28 px type), with 24 px of
# air between the last day block and the first foot line.
#
# **The height is measured, not assumed.** The legend is as wide as the names in
# it; four sources with long names do not fit one 773 px line. A foot is
# anchored to the bottom of its column, so one line more than reserved does not
# overflow downwards where it would be clipped — it grows *upwards*, into the
# last appointment. Hence ``foot_lines`` below.
FOOT_GAP = 24
FOOT_LINE = 36
FOOT_PX = 28
LEGEND_CHIP_W = 34   # the mockup's swatch
LEGEND_CHIP_GAP = 12
LEGEND_GAP = 44      # between two legend entries

# --- the day block ------------------------------------------------------------
# From ``kal_spalte`` in the mockup generator: title, 52 px advance, then air;
# every appointment 84 px plus 38 px per extra title line; 24 px under the block.
#
# **The rule under the day title is gone** [Festlegung P31, 2026-08-23,
# Wolfgang]. The mockup drew a 2 px line under every date. With three columns of
# day blocks that is one horizontal rule every few centimetres, and the bold
# 36 px date plus the air under it separates the days perfectly well on its own.
DAY_TITLE_PX = 36
DAY_HEAD_H = 50 + 14   # 64 — title line plus the air under it, no rule
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
# **12 px** [Festlegung P31, 2026-08-23, Wolfgang] — twice the 6 px of C8, which
# were themselves three times the 2 px floor of FSD §7. At 1 m a 6 px bar reads
# as a mark; 12 px reads as the *colour of the line*, which is what it is for.
# It costs no line height and no text width: the bar is absolutely positioned
# and the time still starts at 20 px.
BAR_W = 12

CUT_H = 46             # the "cut" marker under a block that did not fit

# **Where an evening stops being a second day** [Festlegung 2026-08-31,
# Wolfgang, nach dem Fund unten]. A timed appointment is drawn on every day it
# touches — except when it ends on the following day *before this hour*: then
# 23:00–01:00 stays one appointment on the evening it belongs to, which is how
# anyone reading the wall sees it, and how this module read every multi-day
# appointment until today.
#
# The same rule quietly handles the exclusive end: an appointment ending at
# 00:00 does not reach into that day at all.
#
# **This number is a convention, not a measurement** — there is nothing to
# measure. 06:00 is the hour at which "we were out until…" turns into "the next
# morning".
OVERNIGHT_UNTIL_H = 6

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

# A source is either a diary or a list of **anniversaries** — birthdays, wedding
# days, name days, a jubilee [P41, 2026-08-31; the store value stays
# ``birthdays`` so existing configurations keep working]. The distinction is not
# cosmetic: an anniversary carries a year count, shows only its start time, and
# stays on the wall all day even when "hide today's past entries" is on — it is
# not an appointment somebody can be late for.
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


def _suffix_template(say: Any) -> str:
    """The raw ``"— {years} Jahre"``, for recognising a written-back suffix.

    ``say`` is a :class:`wall_text.WallText` in production and could be any
    callable in a test, so the raw template is asked for defensively: without
    it the count is simply appended as before, which is the old behaviour and
    not a broken page.
    """
    getter = getattr(say, "template", None)
    return getter("calendar.years") if callable(getter) else ""


def anniversary_year(
    summary: str, description: str, suffix_text: str = ""
) -> tuple[str, int | None]:
    """``("Erika Müller (1946)", 1946)`` — the title as written, plus the year.

    Two carriers, either of them enough: a ``(1946)`` in the **title**, and a
    bare year in the **description**.

    **The wall computes, always** [Festlegung P42, 2026-08-31]. When the
    write-back has already put a count into the title, ``suffix_text`` is the
    catalogue string that produced it and the suffix is stripped here before a
    fresh one is appended. Handing the stored text through instead was measured
    and rejected: a series title carries **one** number while the wall looks
    **30 days ahead**, so between 2 and 31 December an anniversary falling in
    January would read one year short. Computing also means the wall stays
    right when the write-back fails or was never set up at all.

    **The title is handed back untouched** [Festlegung P41, 2026-08-31]. Until
    then the bracket was cut off, on the reasoning that it was a workaround
    rather than a name — which held only as long as the year lived in the
    description and the phone never showed it. It is the other way round now:
    the year is written into the *title* precisely so that a phone's calendar
    app shows it, and a wall that then hid it would be showing something else
    than the household edits. So the wall reads
    ``Erika Müller (1946) — wird 80``.

    That the year cannot change is what makes this work: an **age** in the title
    would be right for twelve months and a lie afterwards, and would have to be
    rewritten into every entry every year. A year written once stays true, and
    the age is the one part the renderer computes.

    Cutting nothing also settles the case where both carriers are filled: the
    description wins the *year*, and the title still reads as it was written —
    where the old rule produced ``Erika Müller (1946) — wird 80`` from a title
    it had refused to trim, for no reason a reader could see.
    """
    title = summary.strip()
    if suffix_text:
        title = strip_suffix(title, suffix_pattern(suffix_text))

    stripped = (description or "").strip()
    if stripped.isdigit() and YEAR_MIN <= int(stripped) <= YEAR_MAX:
        return title, int(stripped)

    # Anywhere in the title, not only at the end: after a write-back the year
    # sits in front of the suffix, and the suffix may be one this build does not
    # recognise (an older catalogue wording, a hand-typed line).
    return title, year_in_title(title)


def years_since(when: date, year: int) -> int:
    """How many years lie between ``year`` and ``when``.

    Was ``age_on`` until P41 [2026-08-31]: the list is not only birthdays but
    anniversaries of every kind — weddings, name days, a company jubilee — and
    an "age" is what only one of them has.

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
        summary, year = anniversary_year(
            summary, description, _suffix_template(say)
        )
        if year is not None:
            # **Ein Satz für jede Art von Jahrestag** [Festlegung P41]: "wird 80"
            # stimmt für einen Geburtstag und ist für einen Hochzeitstag falsch.
            # Was gefeiert wird, steht im Titel, wo der Haushalt es selbst
            # schreibt; der Renderer steuert nur die Zahl bei, die sich jedes
            # Jahr ändert — und genau die kann im Titel nicht stehen.
            years = years_since(_local_date(start_value), year)
            summary = f"{summary} {say('calendar.years', years=years)}"
        # A birthday has no location worth the 32 px, and its 09:00–09:15 is a
        # slot, not a duration (kalenderkonzept §6.1) — only the start shows.
        location = ""

    # An all-day event covers every day of its span; ``end`` is exclusive, the
    # way iCalendar writes it. A **timed** one covers its days too — see
    # ``_timed_days`` for the one exception and for what this used to do.
    days: list[date] = [_local_date(start_value)]
    if all_day and isinstance(end_value, date):
        span = (_local_date(end_value) - days[0]).days
        days = [days[0] + timedelta(n) for n in range(max(span, 1))]
    elif not all_day and source.kind != KIND_BIRTHDAYS:
        # An anniversary is a day, never a span: its 09:00–09:15 is a slot
        # (kalenderkonzept §6.1), and a household that draws a wedding day
        # across a week wants that on one line, not on seven.
        days = _timed_days(start_value, end_value)

    spanned = len(days) > 1
    out: list[tuple[date, Entry]] = []
    for day in days:
        if not _visible(day, today, now, all_day, source, end_value, show_past_today):
            continue
        if all_day:
            when = say("calendar.all_day")
            order = (0, "", _fold(summary))
        elif spanned:
            # **Every day says the truth about itself** [Festlegung 2026-08-31,
            # Wolfgang]. Repeating "10:00–15:00" on each of fourteen days would
            # put the start of the first day next to the end of the last and
            # read as a five-hour appointment — which is exactly what the wall
            # showed before, on the first day only.
            #
            # A day that the appointment merely runs through has no time of its
            # own, so it sorts with the all-day entries at the top of the block;
            # only the first day has a clock to sort by. The last day sorts up
            # there too — it began at midnight, before anything else that day.
            if day == days[0]:
                when = say("calendar.spans_from", time=_clock(start_value, say))
                order = (1, _clock(start_value, say), _fold(summary))
            elif day == _local_date(end_value):
                # The *last drawn* day is not always the day it ends on:
                # ``_timed_days`` gives back the night before when the
                # appointment leaves the next one before the morning, and then
                # this day is run through, not finished. Asking the end value
                # rather than the position keeps "bis 00:00" — which reads as
                # "ends when the day begins" — off the wall.
                when = say("calendar.spans_until", time=_clock(end_value, say))
                order = (0, "", _fold(summary))
            else:
                when = say("calendar.spans_through")
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


def _timed_days(start: datetime | date, end: datetime | date | None) -> list[date]:
    """The days a **timed** appointment is drawn on.

    Until 2026-08-31 this was simply the start day, on the grounds that
    "23:00–01:00 again on the next morning would be a second appointment as far
    as anyone reading the wall is concerned". That is true of an evening and
    wrong of everything longer: a 1 Sep 10:00 – 14 Sep 15:00 appointment stood
    on **one** day, labelled "10:00–15:00" — the start of the first day beside
    the end of the last. Worse, one that had *begun* before today produced no
    entry at all and was gone from the wall while it was still running, because
    its only day was already in the past.

    So the span is drawn, and the evening keeps its exception: a day the
    appointment leaves before :data:`OVERNIGHT_UNTIL_H` is not a day it was on.
    That also covers the exclusive end — 00:00 reaches into nothing.
    """
    first = _local_date(start)
    if not isinstance(end, datetime) or not isinstance(start, datetime):
        return [first]
    last = end.date()
    if last > first and end.hour < OVERNIGHT_UNTIL_H:
        last -= timedelta(days=1)
    if last <= first:
        return [first]
    return [first + timedelta(n) for n in range((last - first).days + 1)]


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
def fill_columns(days: list[Day], heights: list[int] | int | None = None) -> list[list[Day]]:
    """Day block after day block, as long as the next one fits **completely**.

    [Festlegung 2026-08-20, FSD §8.1.] What is left over when the third column
    is full is simply not shown — the query window is the ceiling of the
    *query*, not of the display.

    ``heights`` is **per column** since P29: the third one is shorter by its
    foot. A single number still works, for the tests that only care about the
    packing rule.
    """
    if heights is None:
        heights = COLUMN_H
    if isinstance(heights, int):
        heights = [heights] * COLUMNS
    columns: list[list[Day]] = [[] for _ in heights]
    index, used = 0, 0
    for day in days:
        while index < len(heights) and used + _floor(day, heights[index]) > heights[index]:
            index += 1
            used = 0
        if index >= len(heights):
            break
        block = _fit(day, heights[index])
        if block is None:
            continue
        columns[index].append(block)
        used += block.height
    return columns


def _floor(day: Day, column_h: int) -> int:
    """What the block will cost in a column of ``column_h`` — cut height included.

    Asked *before* the column is chosen, because a day taller than any column
    must not push the cursor through all three of them looking for room that
    does not exist.
    """
    block = _fit(day, column_h)
    return block.height if block is not None else 0


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


# --- the foot of the third column ---------------------------------------------
def _text_w(text: str, font_px: int = FOOT_PX) -> float:
    """How wide a run of DejaVu Sans is, by the same model the columns use."""
    return len(text) * CHAR_RATIO * font_px


def legend_lines(legend: list[dict[str, str]], width: int = COLUMN_W) -> list[list[dict[str, str]]]:
    """Break the legend into lines that actually fit the column.

    Three names of the length this household uses come to 613 px of 773
    [gemessen] — one line. Four would not, and a legend that silently needs a
    second line grows the foot *upwards* into the last appointment, because the
    foot is anchored to the bottom. So it is measured rather than hoped for.
    """
    lines: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    used = 0.0
    for who in legend:
        cost = LEGEND_CHIP_W + LEGEND_CHIP_GAP + _text_w(who["label"])
        extra = LEGEND_GAP if current else 0
        if current and used + extra + cost > width:
            lines.append(current)
            current, used = [who], cost
        else:
            current.append(who)
            used += extra + cost
    if current:
        lines.append(current)
    return lines


def foot_height(legend_rows: int, notes: int, stamp: bool = True) -> int:
    """What the foot reserves at the bottom of the third column."""
    rows = legend_rows + notes + (1 if stamp else 0)
    return FOOT_GAP + FOOT_LINE * rows if rows else 0


# --- the whole page -----------------------------------------------------------
@dataclass
class Page:
    """What the template draws."""

    legend: list[list[dict[str, str]]]
    columns: list[list[dict[str, Any]]]
    notes: list[str]
    stamp: str
    bar_px: int
    foot_h: int
    column_h: int
    shown_days: int
    shown_entries: int
    dropped_days: int
    cut_entries: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "legend": self.legend,
            "columns": self.columns,
            "notes": self.notes,
            "stamp": self.stamp,
            "bar_px": self.bar_px,
            "foot_h": self.foot_h,
            "column_h": self.column_h,
        }


def build_page(
    document: dict[str, Any],
    *,
    now: datetime,
    text: Any = None,
    stamp: str = "",
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

    # Legend and notes live in the foot of the third column [P29]. Only that
    # column is shortened; one and two run the full height.
    #
    # **There is no timestamp any more** [P38]. It used to read "updated 10:17"
    # off ``format.clock`` — and a stamp carrying the *minute* makes every
    # calendar image unique, so the hash lock of FSD 11 never says ``unchanged``
    # and each of the four scheduled runs an hour turned into a real push with a
    # visible refresh. The page still says how fresh it is, just by its content:
    # past appointments drop out as the day goes on. Callers may still pass a
    # foot line of their own; nothing in the product does.
    rows = legend_lines([{"label": source.label, "hex": source.hex} for source in sources])
    foot_h = foot_height(len(rows), len(notes), stamp=bool(stamp))
    columns = fill_columns(days, [COLUMN_H, COLUMN_H, COLUMN_H - foot_h])
    shown = [day for column in columns for day in column]

    bar_px = int(section.get("color_bar_px") or BAR_W)
    return Page(
        legend=rows,
        columns=[[day.as_dict() for day in column] for column in columns],
        notes=notes,
        stamp=stamp,
        bar_px=max(min(bar_px, 24), 2),
        foot_h=foot_h,
        column_h=COLUMN_H,
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
