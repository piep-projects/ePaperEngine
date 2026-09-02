"""Priority resolution — which view belongs on the wall (FSD §5).

**The order is configuration, not code** [Festlegung B5]. This module therefore
contains no view names in any fixed sequence: it walks the ordered list from the
store, asks each candidate whether it is active right now, and the first one that
says yes wins. Changing the order is the panel's up/down buttons, not an edit
here.

Pure functions on plain dictionaries, deliberately: no ``hass``, no entities, no
clock of its own. That is what makes the rule testable without Home Assistant —
including the two cases that are otherwise only reachable by waiting, the manual
timeout running out and two schedule windows overlapping.

The answer is a :class:`Resolution`, not a bare string, because the card has to
say **why** the view is up (FSD §3.1): without the reason the resolution is a
black box to the person looking at it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    CANDIDATE_FALLBACK,
    CANDIDATE_MANUAL,
    CANDIDATE_SCHEDULE,
    VIEW_CALENDAR,
    VIEW_GUESTS,
    VIEW_RECIPES,
    VIEWS,
)


@dataclass
class Resolution:
    """The resolved view together with the reason it won."""

    view: str
    source: str  # the candidate token that won
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"view": self.view, "source": self.source, **self.detail}


def manual_deadline(manual: dict[str, Any] | None) -> datetime | None:
    """When the manual override lapses — ``None`` means "not on a clock".

    Two different things arrive here as ``None`` and both mean the same for the
    caller: no override at all, and an override that never expires
    (``manual_timeout_h: 0``, or a view listed in ``manual_exceptions`` — guests
    stay for the weekend, not for four hours, FSD §5).

    Parsed with the standard library rather than ``dt_util``: everything written
    into the store here is ``datetime.isoformat()`` output, and staying off Home
    Assistant is what lets the resolution rule be tested without it.
    """
    if not manual or not manual.get("until"):
        return None
    try:
        return datetime.fromisoformat(str(manual["until"]))
    except ValueError:
        # A deadline nobody can read is treated as no deadline: the override
        # keeps standing and stays visible instead of expiring invisibly.
        return None


def _manual_active(manual: dict[str, Any] | None, now: datetime) -> bool:
    if not manual or not manual.get("view"):
        return False
    if not manual.get("until"):
        return True  # no deadline: exempt view, or the fallback is switched off
    deadline = manual_deadline(manual)
    return deadline is None or deadline > now


def _active_schedule(
    schedule_cfg: dict[str, Any], schedule_states: dict[str, str]
) -> tuple[str, dict[str, Any]] | None:
    """The winning schedule entry, or ``None`` if no window is open.

    **Overlapping windows are not an error** (FSD §5): among the entries that are
    currently ``on``, the lowest rank wins. An entry without a rank sorts last
    rather than first — an unconfigured rank should not outrank a deliberate one.
    """
    running: list[tuple[float, str, str, dict[str, Any]]] = []
    for view, entry in (schedule_cfg or {}).items():
        if not isinstance(entry, dict):
            continue
        entity_id = entry.get("entity_id")
        if not entity_id or schedule_states.get(str(entity_id)) != "on":
            continue
        rank = entry.get("rank")
        running.append((float(rank) if rank is not None else float("inf"), str(view), str(entity_id), entry))
    if not running:
        return None
    # Sorted by rank, then by view name: two entries sharing a rank is a
    # configuration slip, and a stable answer beats one that flips per restart.
    rank, view, entity_id, entry = sorted(running, key=lambda item: (item[0], item[1]))[0]
    return view, {
        "schedule_entity": entity_id,
        "rank": entry.get("rank"),
        "overlapping": len(running) > 1,
    }


def resolve(
    config: dict[str, Any],
    state: dict[str, Any],
    schedule_states: dict[str, str],
    now: datetime,
) -> Resolution:
    """Walk the priority list top down; the first active candidate wins.

    ``schedule_states`` maps a schedule helper's ``entity_id`` to its state, so
    the caller does the entity lookup and this function stays pure.
    """
    views_cfg = config.get("views") or {}
    priority = list(views_cfg.get("priority") or ())
    fallback = str(views_cfg.get("fallback") or VIEW_CALENDAR)
    manual = state.get("manual")

    for candidate in priority:
        if candidate == CANDIDATE_MANUAL:
            if manual and _manual_active(manual, now):
                return Resolution(
                    view=str(manual["view"]),
                    source=CANDIDATE_MANUAL,
                    detail={"until": manual.get("until"), "since": manual.get("at")},
                )
        elif candidate == VIEW_GUESTS:
            if state.get("guests_active"):
                return Resolution(view=VIEW_GUESTS, source=VIEW_GUESTS)
        elif candidate == VIEW_RECIPES:
            selection = (config.get("recipes") or {}).get("selection") or []
            if selection:
                return Resolution(
                    view=VIEW_RECIPES,
                    source=VIEW_RECIPES,
                    detail={"selected": len(selection)},
                )
        elif candidate == CANDIDATE_SCHEDULE:
            hit = _active_schedule(config.get("schedule") or {}, schedule_states)
            if hit is not None:
                view, detail = hit
                return Resolution(view=view, source=CANDIDATE_SCHEDULE, detail=detail)
        elif candidate == CANDIDATE_FALLBACK:
            break  # the list ends here even if somebody sorted entries below it
        # Any other view token (calendar, photos, error) carries no condition of
        # its own in FSD §5 — there is nothing that could make it "active", so it
        # is skipped rather than silently treated as always-on. The panel offers
        # only the five defined candidates for sorting.

    return Resolution(
        view=fallback if fallback in VIEWS else VIEW_CALENDAR,
        source=CANDIDATE_FALLBACK,
    )
