"""What an anniversary entry should read in the calendar — the rule, not the write.

The wall computes the year count on every run. The calendar itself does not:
what stands in it is what a phone's calendar app shows, and until now that was
the bare year in brackets. **P42 [2026-08-31] writes the count back**, so that
the entry reads the same in both places.

Pure functions on plain strings and dates, like ``resolve.py`` and ``outage.py``:
no ``hass``, no CalDAV, no clock of its own. The transport — reading the
credentials of the CalDAV integration, the HTTP ``PUT`` — sits elsewhere and is
handed a finished decision. That is what makes the part that can silently
corrupt somebody's real calendar testable without a server, and it is why a dry
run can show the truth before anything is written.

Three rules carry the whole module:

* **The bracket is the memory.** ``(1946)`` is the only place the birth year
  survives; the count is derived from it and never replaces it. Strip it once
  and the next year has nothing to compute from.
* **The suffix pattern is derived from the wall catalogue**, never written down
  a second time. Two copies of ``— {years} Jahre`` in two files would drift, and
  the failure would be silent: the sync would stop recognising its own previous
  suffix and append a second one.
* **Nothing to change means nothing is written.** A run that finds every entry
  current issues no ``PUT`` — that is what makes a nightly run harmless. Not
  *no HTTP*: it still reads the calendar, measured 2026-09-02 at about four
  seconds against the real server. What a quiet night costs is two searches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# The same window the renderer accepts (calendar_layout.YEAR_MIN/MAX). A number
# outside it is a note somebody put in brackets, not a year.
YEAR_MIN, YEAR_MAX = 1000, 2999

# ``(1946)`` anywhere in the title, not only at the end — after the first
# write-back a suffix follows it, and the year has to stay findable underneath.
_BRACKET = re.compile(r"\((\d{4})\)")


def year_in_title(title: str) -> int | None:
    """The year a title carries in brackets, or ``None``.

    The *last* bracket wins: "Hochzeit (Standesamt) Ulla & Christian (2006)"
    is a real shape, and the trailing one is the year.
    """
    found = [int(m) for m in _BRACKET.findall(title or "")]
    plausible = [y for y in found if YEAR_MIN <= y <= YEAR_MAX]
    return plausible[-1] if plausible else None


def suffix_pattern(catalogue_text: str) -> re.Pattern[str]:
    """Turn ``"— {years} Jahre"`` into the pattern that recognises it again.

    Derived, not written twice — see the module docstring. Everything around the
    placeholder is quoted, so a catalogue that one day says ``"({years} Jahre)"``
    keeps working without a change here. Whitespace is made forgiving because a
    calendar app may normalise it, and an unrecognised suffix is the one failure
    that compounds: it would be kept *and* a new one appended.
    """
    literal = re.escape(catalogue_text.strip())
    literal = literal.replace(re.escape("{years}"), r"\d+")
    literal = re.sub(r"(\\?\s)+", r"\\s+", literal)
    return re.compile(r"\s*" + literal + r"\s*$")


def strip_suffix(title: str, pattern: re.Pattern[str]) -> str:
    """The title without the suffix a previous run appended."""
    return pattern.sub("", title or "").strip()


@dataclass(frozen=True)
class Change:
    """One entry, and what should become of it."""

    uid: str
    old: str
    new: str

    @property
    def changed(self) -> bool:
        return self.old != self.new


def wanted_title(title: str, on: date, catalogue_text: str) -> str:
    """What the entry should read on ``on``.

    ``on`` is a date rather than "now" so the caller decides which year the
    count belongs to — and so this is testable across a new year's eve without
    waiting for one.
    """
    pattern = suffix_pattern(catalogue_text)
    base = strip_suffix(title, pattern)
    year = year_in_title(base)
    if year is None:
        # A name day has no number, and an entry whose bracket was removed by
        # hand keeps its title rather than losing it to a guess.
        return base
    count = on.year - year
    if count < 0:
        # A year in the future is a typo, not an anniversary. Leaving the title
        # alone is the only answer that cannot make it worse.
        return base
    return f"{base} {catalogue_text.format(years=count)}".strip()


def plan(entries: list[tuple[str, str, date]], catalogue_text: str) -> list[Change]:
    """Every entry, with its target title.

    Each entry brings **its own** reference date — the occurrence its count
    describes — because no single "today" is right for a whole calendar. A
    series title carries one number, and on 20 December the entry for 5 January
    has to read the January count. That is the same off-by-one the wall works
    around by recomputing; the writer avoids it by asking each entry when it
    happens next.

    Unchanged ones are kept in the list: a dry run has to show what it decided
    *not* to touch just as much.
    """
    return [
        Change(uid=uid, old=title, new=wanted_title(title, on, catalogue_text))
        for uid, title, on in entries
    ]
