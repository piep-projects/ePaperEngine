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
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from anniversaries import strip_suffix, suffix_pattern, year_in_title
from recipe_layout import wrap

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

# --- the day badge and the week band (P46) ------------------------------------
# **The day no longer has a title line; it has a badge in a rail** [Festlegung
# P46, 2026-09-01, Wolfgang, nach dem Mockup]. Until here every day opened with
# a full-width 36 px line — "Heute · Mittwoch, 20. August" — 64 px tall on
# *every* day, empty ones included, and typically half of it white: the longest
# German form measures 615 px of an 805 px column, the ordinary one 454.
#
# Now the date stands to the left of its appointments instead of above them:
# day number over weekday abbreviation, white on a filled box. What that trades
# is measured, over the mockup's own load:
#
#   senkrecht   the 64 px head is gone on every day that has appointments; an
#               empty day costs BADGE_MIN_H + DAY_GAP = 122 px against the old
#               64 + 32 + 24 = 120, so the filler is a wash and the gain is
#               entirely on days that carry something
#   waagerecht  the rail takes 132 px off the column, so a title line wraps at
#               27 characters instead of 34. Over 23 mockup titles that turned
#               1 wrapped title into 6, +190 px
#
#   zusammen    21 days on the wall → 30, and 28 with the week bands below
#
# The number is 52 px because the badge is what the column is read by; the
# weekday stays small because "Mo" is confirmation, not information — the
# number already says which day it is.
STRIPE_W = 12          # the lane the multi-day stripe runs in, outermost
STRIPE_GAP = 4
BADGE_W = 100          # "30" at 52 px bold is 72 px, "Wed" at 30 px is 66
BADGE_GAP = 16
RAIL_W = STRIPE_W + STRIPE_GAP + BADGE_W + BADGE_GAP   # 132
BADGE_MIN_H = 98       # number line plus weekday line plus air
BADGE_NUM_PX = 52
BADGE_WD_PX = 30
BADGE_MONTH_PX = 26    # only on the 1st, see ``Day.month_text``
BADGE_MONTH_H = 32     # the line it needs, on top of the two that are always there
DAY_GAP = 24           # air below a finished block

# **The month is said once, at the start** [P46]. P29 threw the mockup's header
# out because it repeated the date that the day title said again three lines
# lower. This one repeats nothing: the header carries the *month*, the badges
# carry only number and weekday, and neither says what the other says. It sits
# over the **first column only** — a full-width header would cost all three of
# them, which is exactly what P29 measured and rejected.
#
# A run of 30 days regularly crosses a month, and the header cannot follow it.
# So the badge of the 1st carries the new month as a third line; it costs
# nothing, because the badge is at least BADGE_MIN_H tall anyway.
HEAD_H = 80
HEAD_PX = 56

# **A week band before every Monday** [Festlegung P46, Wolfgang: „können wir
# horizontal noch die Kalenderwoche grau hinterlegt vor jedem montag einfügen?
# horizontal die volle breite ausnutzen"]. Full column width, week number on
# the left, the week's date range right-aligned so the width carries something.
#
# **Yellow, not grey** [Festlegung P47, 2026-09-01, Wolfgang: „ich denke wir
# sollten das mit blau-gelb als start versuchen — grau wirkt doch gerne sehr
# langweilig auf e-paper"]. The instinct was right, and it is measurable rather
# than a matter of taste: **on six primaries a grey is mostly white**. The band
# shipped once at grey 200 and measured, on the real wall image, 63 % white /
# 18 % blue / 12 % yellow — a raster, not a surface, and the same mechanic P22
# found under the guest greeting. A palette colour lands at **93 % pure**.
#
# **Which colour is not a matter of taste either.** Blue, green and red are
# spoken for as source colours, red doubly so since P46 made it the Sunday
# badge, and black is the badge itself. **Yellow is the only primary nobody
# has** — precisely because FSD §7 rules it out for text and thin marks, which
# is what leaves it free as a surface. A blue band would wear the same colour as
# the household's own appointments.
#
# The text on it stays **black**. Yellow *text* at 28 px is the case §7 excludes,
# and it was visibly the weakest of the five variants that were rendered.
#
# Costs 2 days of horizon over three columns.
WEEK_BAND_H = 44
WEEK_BAND_GAP = 12
WEEK_BAND_PX = 28
WEEK_BAND_COLOR = "yellow"

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

# **Sundays are red** [Festlegung P45, 2026-08-31, Wolfgang: „bei Sonntagen die
# ganzen Linie in rot"]. Red off the palette, so it carries no dither raster of
# its own — the same reason the recipe title is green [P16] and the greeting
# colour is picked from these six [P23].
#
# It is the **date** that turns, not the appointments under it: a column is read
# by its dates, and a red date is found at a glance from across the room. Since
# P46 the date is a filled badge rather than a line, so red is the badge's
# *ground* — a whole red block, which is more findable still. ⚠ It also means
# red now says two things on one page: this is a Sunday, and this source is the
# anniversary calendar. The legend distinguishes them; a glance does not.
SUNDAY_COLOR = "red"

# --- the holiday line (P48) ---------------------------------------------------
# **The name stands in a line of its own, without a time and without a bar**
# [Festlegung P48, 2026-09-01, Wolfgang]. Three things were weighed against
# drawing it as an ordinary all-day entry:
#
#   * "ganztägig" beside "1. Weihnachtsfeiertag" says nothing. A holiday has no
#     hour anybody can be late for — the same reason an anniversary shows only
#     its start (kalenderkonzept §6.1);
#   * the bar carries the colour of a *source*, and a holiday belongs to nobody.
#     Its badge is already red; a second colour mark on the same day would ask
#     the reader which of the two is the holiday;
#   * it is 46 px against 84. **On a day that carries nothing else that is free
#     either way** — the badge floor is 98 px and swallows both — so the saving
#     falls exactly where the column is tight: on days that already have
#     appointments.
#
# Red, off the palette, and the same red as the badge: the line and the ground
# say one thing together. ⚠ That makes red the third thing on this page — a
# Sunday, an anniversary source, and now a holiday. The legend separates two of
# them; a glance separates none.
HOLIDAY_PX = 32
HOLIDAY_H = 46         # one line plus the air under it
HOLIDAY_LINE_H = 38    # every further line of a name that wraps

# **The holiday line is measured against the font file, not estimated** — and
# that is a correction, not a preference [2026-09-01, am ersten Wandbild
# gefunden]. The first build wrapped it with the page's ``CHAR_RATIO = 0.531``
# and produced a **collision**: "Schulung Datenschutz mit sehr langem Titel"
# was budgeted at two lines, Chromium set three, and the third ran into the
# appointment below it. Two reasons stack up:
#
#   * the line is **bold**, and ``CHAR_RATIO`` was measured on DejaVu Sans
#     *Book*. ``fc-match "DejaVu Sans:bold"`` resolves to a different file with
#     wider metrics — measured in the add-on container over 29 real holiday
#     names at 32 px: **Book 0.544 average / 0.602 worst, Bold 0.615 / 0.676**;
#   * a holiday name is title case and full of capitals, where ``CHAR_RATIO``
#     was measured on running German recipe prose [Phase 5].
#
# So the wrap asks the file Chromium will draw, exactly as the guest greeting
# has since P21. The character model stays as the **fallback** for a machine
# without the font — the tests run there — and carries the measured *worst*
# ratio rather than the average: there is no ``SAFETY_LINES`` on this page, and
# the way this fails is a day block growing into the next one.
HOLIDAY_CHAR_RATIO = 0.676

# What ``fc-match "DejaVu Sans"`` and ``…:bold`` answer inside the add-on image
# [gemessen 2026-09-01 und 2026-09-02]. A list rather than one path so a
# base-image move degrades to the ratio model instead of throwing.
DEJAVU_BOOK_CANDIDATES = (
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
DEJAVU_BOLD_CANDIDATES = (
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)

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

# The badge is filled, so its two colours are palette colours too — a badge in
# any other tone would be a dithered raster with white letters knocked out of
# it, which is the one thing 52 px of type cannot survive.
WEEK_BAND_BG = COLORS[WEEK_BAND_COLOR]
BADGE_BG = COLORS["black"]
BADGE_BG_SUNDAY = COLORS[SUNDAY_COLOR]
BADGE_FG = "#ffffff"

# A source is either a diary or a list of **anniversaries** — birthdays, wedding
# days, name days, a jubilee [P41, 2026-08-31; the store value stays
# ``birthdays`` so existing configurations keep working]. The distinction is not
# cosmetic: an anniversary carries a year count, shows only its start time, and
# stays on the wall all day even when "hide today's past entries" is on — it is
# not an appointment somebody can be late for.
KIND_EVENTS = "events"
KIND_BIRTHDAYS = "birthdays"
# **A third kind: public holidays** [Festlegung P48, 2026-09-01, Wolfgang:
# „eine weitere Kalenderkategorie ‚Feiertage‘ … die Einträge dort sollen den Tag
# dann in rot wie einen Sonntag darstellen und den Feiertagstext einblenden"].
# It is the one kind whose entries are not *of* the day but *about* it: they say
# what the day is, the way the weekday abbreviation does, and that is why they
# stand in a line of their own rather than among the appointments.
KIND_HOLIDAYS = "holidays"
KINDS = (KIND_EVENTS, KIND_BIRTHDAYS, KIND_HOLIDAYS)

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
    # Which multi-day appointment this entry belongs to, empty for an ordinary
    # one. It is what lets ``build_days`` recognise the two ends of the same
    # span after the day-by-day filtering has run [P46].
    span_key: str = ""

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
class Holiday:
    """What the day *is*, drawn above what happens on it [P48].

    Not an :class:`Entry`: it has no time column and no colour bar, and it is
    never spanned across days. A holiday calendar hands out one all-day event
    per holiday, and the two German cases that look multi-day — school holidays,
    a bridging day — are a different list that belongs in an ordinary source.
    """

    lines: list[str]

    @property
    def height(self) -> int:
        return HOLIDAY_H + HOLIDAY_LINE_H * (max(len(self.lines), 1) - 1)

    def as_dict(self) -> dict[str, Any]:
        return {"lines": self.lines, "height": self.height}


@dataclass
class Day:
    """One day block: the badge and everything beside it."""

    day: date
    entries: list[Entry] = field(default_factory=list)
    # The names of the public holidays falling on this day [P48]. They stand
    # above the appointments and turn the badge red; a day that holds nothing
    # but one of these is still not an empty day.
    holidays: list[Holiday] = field(default_factory=list)
    today: bool = False
    cut: int = 0  # appointments that had to be dropped to make it fit
    # Both out of the catalogue, never sliced off the long form in code: "Mo"
    # happens to be "Montag"[:2] in German and is Mon/Tue/Wed in English, and a
    # third language would break the trick silently [P9].
    weekday_text: str = ""
    # Set on the 1st of a month the header does not name — the badge then
    # carries the month as a third line [P46]. Empty otherwise.
    month_text: str = ""
    # ``{span key: colour}`` for every multi-day appointment that touches this
    # day, the days it merely runs through included. The stripe is drawn from
    # these, not from the entries: a day in the middle of a span has no entry.
    spans: dict[str, str] = field(default_factory=dict)
    # Filled in by ``fill_columns``; the template needs absolute positions to
    # draw a stripe that crosses day blocks.
    top: int = 0

    @property
    def body_height(self) -> int:
        """What stands beside the badge. Zero on an empty day."""
        return (
            sum(holiday.height for holiday in self.holidays)
            + sum(entry.height for entry in self.entries)
            + (CUT_H if self.cut else 0)
        )

    @property
    def badge_floor(self) -> int:
        """The badge's own minimum — three lines on the 1st, two otherwise.

        Found by arithmetic rather than at the wall, and it would not have shown
        up there either: the badge clips, so the month of an **empty** 1st would
        simply have been missing, on the one day of the month that needs it.
        """
        return BADGE_MIN_H + (BADGE_MONTH_H if self.month_text else 0)

    @property
    def badge_height(self) -> int:
        """The badge is as tall as the day [P46, Wolfgang: „sollten mehr Zeilen
        gebraucht werden ist auch das Feld vom Badge zu erweitern"].

        Which is also what makes an empty day cost nothing extra: there is no
        dash any more, the bare badge with white beside it says the day is empty
        as plainly as the word did [P45, taken one step further].
        """
        return max(self.badge_floor, self.body_height)

    @property
    def height(self) -> int:
        return self.badge_height + DAY_GAP

    @property
    def sunday(self) -> bool:
        """Read off the date, never carried in the constructor.

        A flag that can be set is a flag that can disagree with ``day``; this
        one cannot [P45].
        """
        return self.day.weekday() == 6

    @property
    def red(self) -> bool:
        """Whether the badge is red: a Sunday, or a public holiday [P48].

        Two facts, one ground. The template asks this rather than ``sunday``,
        so that a holiday falling on a Sunday changes nothing and a holiday on a
        Tuesday reads exactly like one — which is what the household asked for
        („den Tag dann in rot wie einen Sonntag darstellen").
        """
        return self.sunday or bool(self.holidays)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "day",
            "number": f"{self.day.day:02d}",
            "weekday": self.weekday_text,
            "month": self.month_text,
            "holidays": [holiday.as_dict() for holiday in self.holidays],
            "entries": [entry.as_dict() for entry in self.entries],
            "empty": not self.entries and not self.holidays,
            "today": self.today,
            "sunday": self.sunday,
            "red": self.red,
            "cut": self.cut,
            "badge_h": self.badge_height,
            "top": self.top,
            "height": self.height,
        }


@dataclass
class WeekBand:
    """The grey band that opens a week, before every Monday [P46]."""

    monday: date
    label: str   # "KW 39"
    span: str    # "21. – 27. September"
    top: int = 0

    @property
    def height(self) -> int:
        return WEEK_BAND_H + WEEK_BAND_GAP

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "band",
            "label": self.label,
            "span": self.span,
            "top": self.top,
            "height": self.height,
        }


# --- measuring ----------------------------------------------------------------
# **There is no ``chars_per_line`` here any more** [2026-09-02]. It wrapped the
# title with the recipe page's prose ratio until that produced a collision on
# the wall, and once the title is measured nothing on this page is left that the
# prose model may answer for. Leaving it standing would be an invitation to wrap
# the next text element with it and arrive at the same fault a third time — the
# recipe page keeps its own, where the ratio was measured.


# The title column since P46: the badge rail takes 132 px off the column before
# the time column has even started. **The font never gets smaller** [Wolfgang:
# „immer gleiche Schrift"] — a title that does not fit wraps, and the badge
# grows with it.
TITLE_W = COLUMN_W - RAIL_W - TITLE_DX  # 458

# **An appointment title is measured against the font file too** [2026-09-02,
# am Wandbild belegt]. It carried ``TITLE_CHARS = chars_per_line(…)`` — the
# page's ``CHAR_RATIO = 0.531`` — from P46 until here, and that is the second
# half of the fault P48a found on the holiday line: the ratio was measured on
# running German recipe prose [P32], and a calendar title is nothing of the
# kind. It is a name, a bracketed year, a dash, a count: capitals, digits and
# punctuation, all of them wide. Measured in the add-on container over 165 real
# and mockup titles at 32 px: **average 0.576, worst 0.642** against the 0.531
# the model used.
#
# **How it failed is the part worth keeping.** The template renders every model
# line as its own ``<div class="line">`` — so Chromium does not re-wrap the
# title, it re-wraps *the model line that came out too wide*. At 27 characters
# **128 of 296 lines over that corpus were wider than 458 px**; on the wall of
# 2026-09-02, four of six entries. "Vorname1 Nachnam38 (1965) — 61 years" was
# budgeted at two lines and set as three, and the block height was already
# fixed, so the third ran into what stood below it. A too-wide line does not
# look wrong on its own — it silently becomes an extra one.
#
# So the wrap asks the file Chromium draws with, exactly as the holiday line
# and the guest greeting do. The ratio stays as the fallback for a machine
# without the font — the tests run there — and carries the measured *worst*
# ratio rather than the average, for the same reason as ``HOLIDAY_CHAR_RATIO``:
# there is no ``SAFETY_LINES`` on this page, and the way this fails is one day
# block growing into the next.
TITLE_CHAR_RATIO = 0.642
# Only reached when the font is missing; 22 characters against the 27 the prose
# ratio claimed.
TITLE_CHARS = max(round(TITLE_W / (TITLE_CHAR_RATIO * TITLE_PX)), 1)

# A holiday name gets the **whole** body, because it gives up the time column
# it would otherwise stand beside [P48]: 673 px against the title's 458, which
# is 40 characters against 27. "1. Weihnachtsfeiertag" is 21 and the longest
# German public holiday, "Tag der Deutschen Einheit", is 25 — but the wrap is
# measured rather than assumed, because the list is whatever calendar the
# household subscribes to, and a name that wraps has to raise the badge with it.
HOLIDAY_W = COLUMN_W - RAIL_W  # 673
# Only reached when the font is missing; see ``HOLIDAY_CHAR_RATIO``.
HOLIDAY_CHARS = max(round(HOLIDAY_W / (HOLIDAY_CHAR_RATIO * HOLIDAY_PX)), 1)

_faces: dict[tuple[tuple[str, ...], int], Any] = {}


def _face(candidates: tuple[str, ...], size: int) -> Any:
    """A DejaVu face at ``size``, or ``None`` where the file is not there.

    Looked up once per (family, size). Pillow is already in this image
    (``imaging``, ``guest_layout``), but this module is also imported by the
    test suite on a machine that has neither the font nor a reason to grow a
    dependency on it, so every failure here is answered with ``None`` and the
    ratio model.
    """
    key = (candidates, size)
    if key in _faces:
        return _faces[key]
    _faces[key] = None
    try:
        from PIL import ImageFont
    except Exception:  # noqa: BLE001 - no Pillow, no measurement
        return None
    for path in candidates:
        try:
            _faces[key] = ImageFont.truetype(path, size)
            break
        except Exception:  # noqa: BLE001 - try the next path
            continue
    return _faces[key]


def measured_lines(text: str, width: int, face: Any, fallback_chars: int) -> list[str]:
    """Greedy word wrap on measured advance widths, the character model where
    the font is missing.

    The one rule that matters: **no line handed to the template may be wider
    than the column it goes into.** The template renders each line as its own
    element, so a line that overflows is not clipped and does not look wrong —
    Chromium breaks it again, and the block is a line taller than the model
    said [2026-09-02, siehe ``TITLE_CHAR_RATIO``].

    A single word wider than the line is left whole: breaking a name mid-word
    would be worse than a line that runs long, and the block grows to whatever
    comes out.
    """
    if face is None:
        return wrap(text, fallback_chars) or [""]
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if face.getlength(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def title_lines(text: str, width: int = TITLE_W) -> list[str]:
    """Wrap an appointment title the way Chromium will break it."""
    return measured_lines(text, width, _face(DEJAVU_BOOK_CANDIDATES, TITLE_PX), TITLE_CHARS)


def holiday_lines(text: str, width: int = HOLIDAY_W) -> list[str]:
    """Wrap a holiday name the way Chromium will break it — bold face [P48a]."""
    return measured_lines(
        text, width, _face(DEJAVU_BOLD_CANDIDATES, HOLIDAY_PX), HOLIDAY_CHARS
    )


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
    names: dict[date, list[Holiday]] = {}

    def in_window(day: date) -> bool:
        return day >= today and (horizon is None or day <= horizon)

    for source in sources:
        for raw in events.get(source.entity_id) or []:
            if source.kind == KIND_HOLIDAYS:
                for day, holiday in _holidays_for(raw, say):
                    if in_window(day):
                        names.setdefault(day, []).append(holiday)
                continue
            for day, entry in _entries_for(raw, source, today, now, show_past_today, say):
                if in_window(day):
                    by_day.setdefault(day, []).append(entry)

    spans = _collapse_spans(by_day)

    # The run of days is gapless *between* appointments, not after the last one:
    # trailing empty days are filler, and filler is measured in appointments
    # that did not fit.
    covered = [day for covered_days, _ in spans.values() for day in covered_days]
    last = max([*by_day, *covered, *names] or [today])
    days: list[Day] = []
    cursor = today
    while cursor <= last:
        entries = sorted(by_day.get(cursor, []), key=lambda item: item.sort_key)
        holidays = names.get(cursor, [])
        touching = {key: hex_ for key, (_, hex_) in _touching(spans, cursor).items()}
        # A day a span merely runs through carries no entry any more, but the
        # stripe has to cross it — so it is never dropped as "empty". Neither is
        # a day that only a holiday name stands on [P48].
        if entries or holidays or touching or show_empty_days or cursor == today:
            days.append(
                Day(
                    day=cursor,
                    entries=entries,
                    holidays=holidays,
                    today=cursor == today,
                    weekday_text=say(f"weekday_short.{cursor.weekday()}"),
                    month_text=(
                        say(f"month_short.{cursor.month}")
                        if cursor.day == 1 and cursor != today
                        else ""
                    ),
                    spans=touching,
                )
            )
        cursor += timedelta(days=1)
    return days


def _touching(
    spans: dict[str, tuple[list[date], str]], day: date
) -> dict[str, tuple[list[date], str]]:
    return {key: value for key, value in spans.items() if day in value[0]}


def _collapse_spans(by_day: dict[date, list[Entry]]) -> dict[str, tuple[list[date], str]]:
    """Reduce every multi-day appointment to its two ends and one stripe.

    **The colour runs through instead of the word** [Festlegung P46,
    2026-09-01, Wolfgang: „bevor man durchgehend schreibt sollte man überlegen
    ob die farbmarkierung durchgehen kann"]. Until here a spanned appointment
    stood on every day it touched, the middle ones reading "durchgehend" — one
    entry of 84 px per day for a fortnight's holiday. Now it is named at both
    ends and drawn as an unbroken stripe in between.

    **What that costs is real and it is a change to P44**: the middle days no
    longer name the appointment. Somebody looking at the 24th sees a blue stripe
    and has to follow it up to the 23rd to learn it is the holiday. The stripe
    was measured against the alternative — keeping every day's entry — and buys
    two days of horizon over three columns; the readability is a judgement, not
    a measurement.

    The two ends keep the label ``_entries_for`` gave them, so an appointment
    that had already started before today opens with "durchgehend" rather than
    "ab 10:00": the first day *shown* is not always the first day it has.

    Trimming happens **after** the day filtering, which is the whole reason it
    lives here rather than in ``_entries_for`` — which days survive depends on
    today, the horizon and the past-appointment filter.
    """
    seen: dict[str, list[date]] = {}
    colour: dict[str, str] = {}
    for day, entries in by_day.items():
        for entry in entries:
            if entry.span_key:
                seen.setdefault(entry.span_key, []).append(day)
                colour[entry.span_key] = entry.color

    spans: dict[str, tuple[list[date], str]] = {}
    for key, days in seen.items():
        first, last = min(days), max(days)
        if first == last:
            continue  # one surviving day is an ordinary entry, not a span
        for day in days:
            if day not in (first, last):
                by_day[day] = [e for e in by_day[day] if e.span_key != key]
        covered = [first + timedelta(n) for n in range((last - first).days + 1)]
        spans[key] = (covered, colour[key])
    return spans


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
    # Identity across days, for the stripe. ``uid`` when the source hands one
    # out, otherwise what a calendar entry is made of — a recurrence gives every
    # occurrence the same uid, so the start has to be in the key either way.
    span_key = (
        f"{source.entity_id}|{raw.get('uid') or summary}|{days[0].isoformat()}"
        if spanned
        else ""
    )
    out: list[tuple[date, Entry]] = []
    for day in days:
        if not _visible(day, today, now, all_day, source, end_value, show_past_today):
            continue
        if all_day:
            # **An all-day span is a span too** [P46]. It used to say "ganztägig"
            # on each of its days, which is not misleading the way the repeated
            # "10:00–15:00" was — but a three-day trip drawn one way and a
            # three-day holiday drawn another would be the arbitrary half of a
            # rule. Both get the stripe; both are named at their two ends.
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
                    span_key=span_key,
                ),
            )
        )
    return out


def _holidays_for(raw: dict[str, Any], say: Any) -> list[tuple[date, Holiday]]:
    """One raw event from a holiday calendar → the day it names [P48].

    **Only its first day** [Festlegung P48, Wolfgang: „vorerst gar nicht
    spannen"]. Every German public holiday is one day long, and a list that is
    not — school holidays, a works shutdown — would turn a fortnight of badges
    red and leave red saying nothing in particular. Such a list belongs in an
    ordinary source, where the stripe of P46 already draws it properly.

    **No visibility filter either.** A holiday is exempt from "hide today's past
    appointments" for the same reason an anniversary is: it is not something
    anybody can be late for. That it is normally an all-day entry — which is
    exempt anyway — is a property of the calendar, not a guarantee, and the wall
    must not lose Christmas Day at 00:01 because a feed wrote it as 00:00–00:00.
    """
    start = _parse(raw.get("start"))
    if start is None:
        return []
    summary = str(raw.get("summary") or "").strip() or say("calendar.untitled")
    return [(_local_date(start[0]), Holiday(lines=holiday_lines(summary)))]


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


def month_header(day: date, say: Any) -> str:
    """``September 2026`` — the one line above the first column [P46].

    Every part of it out of the catalog [Festlegung P9]: month names are
    language, and ``strftime`` would take them from a C locale the add-on image
    does not install.
    """
    return say("format.month_year", month=say(f"month.{day.month}"), year=day.year)


def week_band(monday: date, say: Any) -> WeekBand:
    """The band that opens a week: ``KW 39`` and ``21. – 27. September``.

    The range is derived from the **Monday of the week**, not from the day the
    band happens to stand before. They are the same thing here, and were not in
    the first draft: a band at the head of a column that continues a week read
    "8. – 14. Oktober" beside the same week's "5. – 11. Oktober" one column to
    the left. The bug was invisible until two bands for one week stood side by
    side.

    Two catalog forms rather than one, because a week that crosses a month has
    to name both of them and one that does not must not repeat itself.
    """
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        span = say(
            "format.week_span",
            from_day=monday.day,
            to_day=sunday.day,
            month=say(f"month.{monday.month}"),
        )
    else:
        span = say(
            "format.week_span_months",
            from_day=monday.day,
            from_month=say(f"month_short.{monday.month}"),
            to_day=sunday.day,
            to_month=say(f"month_short.{sunday.month}"),
        )
    return WeekBand(
        monday=monday,
        label=say("calendar.week", week=monday.isocalendar()[1]),
        span=span,
    )


def with_week_bands(days: list[Day], say: Any) -> list[Day | WeekBand]:
    """Put a band before every Monday [P46, Wolfgang: „vor jedem montag"].

    Before *every* Monday, the first day of the run included: a rule with an
    exception for the first item would leave a run that happens to start on a
    Monday without the label a run starting on a Tuesday gets one line later.
    A run starting mid-week has no band until its first Monday — that is what
    the rule says, and the header above the first column carries the month
    meanwhile.
    """
    out: list[Day | WeekBand] = []
    for day in days:
        if day.day.weekday() == 0:
            out.append(week_band(day.day, say))
        out.append(day)
    return out


# --- filling the columns ------------------------------------------------------
Item = "Day | WeekBand"


def fill_columns(
    items: list[Any], heights: list[int] | int | None = None
) -> list[list[Any]]:
    """Block after block, as long as the next one fits **completely**.

    [Festlegung 2026-08-20, FSD §8.1.] What is left over when the third column
    is full is simply not shown — the query window is the ceiling of the
    *query*, not of the display.

    ``heights`` is **per column** since P29: the third one is shorter by its
    foot, the first by its month header. A single number still works, for the
    tests that only care about the packing rule.

    Two things the day blocks alone did not need [P46]:

    * **a week band is never the last thing in a column.** It is a heading, and
      a heading whose week starts in the next column is a heading over nothing.
      So a band is placed only if the day behind it fits with it;
    * **every block is told where it sits.** The multi-day stripe crosses day
      blocks and the gaps between them, so it cannot be drawn by any one of
      them — it is placed absolutely, out of these tops.
    """
    if heights is None:
        heights = COLUMN_H
    if isinstance(heights, int):
        heights = [heights] * COLUMNS
    columns: list[list[Any]] = [[] for _ in heights]
    index, used = 0, 0
    position = 0
    while position < len(items):
        item = items[position]
        band = item if isinstance(item, WeekBand) else None
        day = items[position + 1] if band is not None else item
        if band is not None and not isinstance(day, Day):
            position += 1  # a band with nothing behind it never reaches a column
            continue

        while index < len(heights):
            need = (band.height if band else 0) + _floor(day, heights[index])
            if used + need <= heights[index]:
                break
            index += 1
            used = 0
        if index >= len(heights):
            break

        block = _fit(day, heights[index] - (band.height if band else 0))
        if block is None:
            position += 2 if band else 1
            continue
        if band is not None:
            band.top = used
            columns[index].append(band)
            used += band.height
        block.top = used
        columns[index].append(block)
        used += block.height
        position += 2 if band else 1
    return columns


def column_stripes(column: list[Any]) -> list[dict[str, Any]]:
    """The multi-day stripes of one column, as rectangles [P46].

    From the first badge of a span to the last, **through** the gaps and through
    any week band in between: the stripe says the appointment did not stop, and
    a stripe that stopped at every day boundary would say the opposite. The
    band is drawn first and the stripe over it for the same reason.

    Two spans that overlap in one column share the 12 px lane rather than
    covering one another — half each, a third each, and never below 4 px, which
    is where a stripe stops reading as a stripe (FSD §7 puts the floor at 2 px).
    """
    days = [item for item in column if isinstance(item, Day)]
    order: list[str] = []
    extent: dict[str, tuple[int, int, str]] = {}
    for day in days:
        for key, hex_ in day.spans.items():
            top, bottom = day.top, day.top + day.badge_height
            if key in extent:
                first, last, _ = extent[key]
                extent[key] = (min(first, top), max(last, bottom), hex_)
            else:
                order.append(key)
                extent[key] = (top, bottom, hex_)

    lanes: list[int] = []          # the bottom each lane is occupied to
    placed: list[tuple[int, int, int, str]] = []
    for key in order:
        top, bottom, hex_ = extent[key]
        lane = next((n for n, end in enumerate(lanes) if end <= top), len(lanes))
        if lane == len(lanes):
            lanes.append(bottom)
        else:
            lanes[lane] = bottom
        placed.append((lane, top, bottom, hex_))

    width = max(STRIPE_W // max(len(lanes), 1), 4)
    return [
        {
            "left": lane * width,
            "width": width,
            "top": top,
            "height": bottom - top,
            "color": hex_,
        }
        for lane, top, bottom, hex_ in placed
    ]


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

    An **empty** day is never cut away: at BADGE_MIN_H it is the smallest thing
    a column can hold, and a span running through it needs its badge to hang the
    stripe on.
    """
    if day.height <= column_h:
        return day
    kept = list(day.entries)
    dropped = 0
    while kept and replace(day, entries=kept, cut=dropped + 1).height > column_h:
        kept.pop()
        dropped += 1
    # A day whose every appointment had to go is still a day when it carries a
    # holiday name: dropping the block would take the red badge and the name
    # with it, and the run of days would lose Christmas because too much was
    # happening on it [P48].
    if not kept and not day.holidays:
        return None
    return replace(day, entries=kept, cut=dropped)


# --- the foot of the third column ---------------------------------------------
def _text_w(text: str, font_px: int = FOOT_PX) -> float:
    """How wide a run of DejaVu Sans is — measured, with the ratio as fallback.

    A legend label is a person's name, which is title case and shares nothing
    with the running prose ``CHAR_RATIO`` was measured on [2026-09-02, the same
    fault as ``TITLE_CHAR_RATIO``]. Measured against the real face, three
    household labels come to 646 px of 805 where the ratio model claimed 613 —
    and the case that matters is the one just under the line: a legend the model
    calls one row and the browser sets as two grows the foot **upwards** into
    the last appointment, because the foot is anchored to the bottom.
    """
    face = _face(DEJAVU_BOOK_CANDIDATES, font_px)
    if face is None:
        return len(text) * TITLE_CHAR_RATIO * font_px
    return float(face.getlength(str(text or "")))


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
    stripes: list[list[dict[str, Any]]]
    header: str
    notes: list[str]
    stamp: str
    bar_px: int
    foot_h: int
    head_h: int
    column_h: int
    shown_days: int
    shown_entries: int
    shown_holidays: int
    dropped_days: int
    cut_entries: int
    # How many usable sources the page was built from — entity_id present, kind
    # irrelevant. **Not the number of legend rows**, which is what the run log
    # used to report under this name: several people share one row, and since
    # P48 a holiday source contributes none at all. Three sources answered as
    # ``sources: 1``, and the one number a reader would use to check "did all my
    # calendars arrive" was the one that could not say.
    sources: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "legend": self.legend,
            "columns": self.columns,
            "stripes": self.stripes,
            "header": self.header,
            "notes": self.notes,
            "stamp": self.stamp,
            "bar_px": self.bar_px,
            "foot_h": self.foot_h,
            "head_h": self.head_h,
            "column_h": self.column_h,
            "rail_w": RAIL_W,
            "badge_w": BADGE_W,
            "badge_x": STRIPE_W + STRIPE_GAP,
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
    # **A holiday source is not in the legend** [Festlegung P48]: the legend says
    # whose appointment wears which colour, and a holiday is nobody's. It has no
    # bar to explain, so a chip beside its name would point at nothing on the
    # page — and it would cost the third column a 36 px line of foot.
    rows = legend_lines(
        [
            {"label": source.label, "hex": source.hex}
            for source in sources
            if source.kind != KIND_HOLIDAYS
        ]
    )
    foot_h = foot_height(len(rows), len(notes), stamp=bool(stamp))
    # **Only the first column pays for the header, only the third for the foot**
    # [P46 and P29]. A band across the whole page would take its height off all
    # three, which is the measurement P29 acted on.
    columns = fill_columns(
        with_week_bands(days, say),
        [COLUMN_H - HEAD_H, COLUMN_H, COLUMN_H - foot_h],
    )
    shown = [item for column in columns for item in column if isinstance(item, Day)]

    bar_px = int(section.get("color_bar_px") or BAR_W)
    return Page(
        legend=rows,
        columns=[[item.as_dict() for item in column] for column in columns],
        stripes=[column_stripes(column) for column in columns],
        header=month_header(days[0].day if days else today, say),
        notes=notes,
        stamp=stamp,
        bar_px=max(min(bar_px, 24), 2),
        foot_h=foot_h,
        head_h=HEAD_H,
        column_h=COLUMN_H,
        shown_days=len(shown),
        shown_entries=sum(len(day.entries) for day in shown),
        # Counted separately from the entries, because it is not one [P48]: it
        # is also the only way to tell from a run's log whether a holiday
        # calendar reached the page at all — it is in no legend, so the source
        # count says nothing about it.
        shown_holidays=sum(len(day.holidays) for day in shown),
        dropped_days=len(days) - len(shown),
        cut_entries=sum(day.cut for day in shown),
        sources=len(sources),
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
