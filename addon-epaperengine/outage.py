"""When a failure gets to the wall (FSD §12, Festlegung P10 2026-08-21).

Pure stdlib and no I/O, deliberately — the same reasoning as ``resolve.py`` on
the integration side: a rule about *time and counting* is only trustworthy if it
can be tested without waiting for it. Everything here is a function of the
stored state, the exception and the current moment.

The rule [Festlegung P10]:

* every failed run adds to the streak and is reported to Home Assistant;
* the **first** failure leaves the picture on the wall — a NAS briefly away or a
  single wedged Chromium is not worth taking the family photo down for;
* from the **second in a row** the wall shows the failure itself, which is what
  FSD §12 asks for on a total failure;
* the timestamp on that page is the **start of the streak**, never the current
  run. That is what makes the page identical from run to run, so the hash gate
  of FSD §11 suppresses the repeats and a permanent outage costs exactly one
  refresh — §12's "günstige Nebenwirkung" only works if nothing on the page
  moves.

The state keys live in the add-on's own ``/data/state.json``; the add-on never
writes configuration back to Home Assistant (FSD §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Consecutive failed runs before the error page replaces the picture.
ERROR_PAGE_AFTER = 2

KEY_FAILURES = "failures"
KEY_SINCE = "failure_since"
KEY_LAST = "last_error"


@dataclass(frozen=True)
class Outage:
    """One failure, seen in the context of the ones before it."""

    failures: int
    since: datetime
    technical: str
    show_on_wall: bool


def describe(view: str, exc: BaseException) -> str:
    """The one technical line of FSD §8.5 [Festlegung P11].

    View first, then exception type and message: the view is what the reader
    needs to know before anything else, and it is also what tells a repeated
    failure of the same view from a system that is failing at everything.
    """
    return f"{view} · {type(exc).__name__}: {exc}"


def note_failure(
    state: dict[str, Any], view: str, exc: BaseException, now: datetime
) -> Outage:
    """Record a failed run in ``state`` and say what should happen to the wall.

    Mutates ``state`` — the caller owns writing it back, because a run that dies
    between here and the disk should not leave a half-counted streak behind.
    """
    failures = int(state.get(KEY_FAILURES) or 0) + 1
    since = float(state.get(KEY_SINCE) or now.timestamp())
    technical = describe(view, exc)

    state[KEY_FAILURES] = failures
    state[KEY_SINCE] = since
    state[KEY_LAST] = {"view": view, "text": technical}

    return Outage(
        failures=failures,
        since=datetime.fromtimestamp(since),
        technical=technical,
        show_on_wall=failures >= ERROR_PAGE_AFTER,
    )


def standing(state: dict[str, Any]) -> Outage | None:
    """The outage on record, for a run that renders the error view on purpose.

    ``error`` is one of the five view tokens (FSD §5), so it can be pinned by
    hand or won by a schedule. Then there is nothing to count — the page just
    shows what is known, and ``None`` means "nothing is".
    """
    last = state.get(KEY_LAST) or {}
    text = str(last.get("text") or "").strip()
    if not text:
        return None
    since = float(state.get(KEY_SINCE) or 0) or None
    return Outage(
        failures=int(state.get(KEY_FAILURES) or 0),
        since=datetime.fromtimestamp(since) if since else datetime.fromtimestamp(0),
        technical=text,
        show_on_wall=True,
    )


def clear(state: dict[str, Any]) -> bool:
    """End the streak after a run that worked. True if there was one."""
    had = any(key in state for key in (KEY_FAILURES, KEY_SINCE, KEY_LAST))
    for key in (KEY_FAILURES, KEY_SINCE, KEY_LAST):
        state.pop(key, None)
    return had
