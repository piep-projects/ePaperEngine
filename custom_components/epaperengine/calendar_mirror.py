"""P53: a Home Assistant calendar, mirrored into a real CalDAV calendar.

**Why this exists.** Public holidays and the waste collection schedule are
produced by Home Assistant integrations. They live only inside Home Assistant —
the phone in somebody's pocket never sees them. This module copies them into a
CalDAV calendar the household already subscribes to, so the bin day shows up
where everybody looks anyway.

**One direction, and it is not the wall's** [Festlegung P53, 2026-09-03,
Wolfgang: „nur fürs Handy, Wand liest weiter die HA-Entity"]. The renderer keeps
reading the Home Assistant entity. Nothing here can change what hangs on the
wall, and a mirror run that fails costs a phone its bin day, not the household
its calendar page. That is also why this is not wired into the render cycle at
all: it is a service and a button, never a step of a run.

**The target is a mirror, not a merge.** What the source no longer says is
deleted [Wolfgang: „kann alles löschen - ist ein kalender der nur von ha
gefüttert werden sollte"]. Three things keep that from being dangerous:

  * **only entries this mirror wrote are ever deleted.** Every UID it creates
    carries a fingerprint of the *source entity*, so two sources may share one
    target calendar without eating each other's entries — the likely case, since
    subscribing a phone to one extra calendar is easier than to two. Anything
    else in the calendar is counted and reported as ``foreign`` and left alone.
    ⚠ This is narrower than the permission that was given: a hand-made entry in
    the target survives. The trade is that pointing this at the wrong calendar
    is no longer destructive;
  * **the window bounds the tidying.** Only the next
    :data:`MIRROR_DAYS` days are compared, so nothing outside it is touched;
  * **dry run is the default**, here and on the service. The first press
    answers "would create 19, delete 0, 64 foreign" — and a target picked by
    mistake is obvious in that sentence before anything happens.

**The identity of an entry is its content.** The UID is derived from source,
start, end and summary, so an entry that moves is a different entry: the old one
is deleted and the new one created. There is no update path and there does not
need to be one — a collection date that shifts is not the same date.

**Building the ICS by hand is deliberate.** The half of this that can silently
destroy somebody's calendar is the half that has to be testable without a
server, exactly as ``caldav_writer`` argues. So the text is built by pure
functions here — RFC 5545 escaping, CRLF, 75-octet folding — and only
``_apply`` ever talks to the network. The ``caldav`` library is never imported
for the same reason as in P42: it pulls in ``lxml``, and a custom integration
ships pure Python. The client comes from the CalDAV integration's config entry.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .caldav_writer import CALDAV_DOMAIN, WriteBackError, _caldav_entry, _client

_LOGGER = logging.getLogger(__name__)

# A year [Festlegung P53, Wolfgang: „ein Jahr"]. The wall looks 30 days ahead;
# a phone wants the whole year, or in October there is still no November
# collection to be seen.
#
# **The window is what is asked for, not what arrives** — measured 3.9.2026 in a
# dry run against the real server. The holiday integration fills it: 12 entries
# out to 27.5.2027, across the year boundary. The waste source does not — it
# publishes its own calendar year and stops at **28.12.2026**, 30 dates over
# some four months. That is the source's horizon and not a fault here: towards
# the turn of the year the mirror simply carries fewer months, and refills once
# the collection schedule for the new year is published.
MIRROR_DAYS = 365

# Everything this module writes is stamped with this. Deleting is restricted to
# UIDs that match, which is what lets one target calendar serve several sources
# and what stops a mis-configured target from being emptied.
UID_PREFIX = "epe"
UID_DOMAIN = "epaperengine"

PRODID = "-//piep-projects//ePaperEngine//EN"

# RFC 5545 §3.1: lines are folded at 75 **octets**, and the continuation begins
# with a single space. Folding by characters would split a multi-byte umlaut
# down the middle — measured on a 68-character name in the birthday tool.
FOLD_OCTETS = 75


class MirrorError(Exception):
    """Something the person pressing the button needs to read."""


@dataclass(frozen=True)
class Wanted:
    """One entry the target calendar should hold."""

    uid: str
    summary: str
    start: str
    end: str
    all_day: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "summary": self.summary,
            "start": self.start,
            "end": self.end,
            "all_day": self.all_day,
        }


@dataclass
class Plan:
    """What a run would do, before it does any of it."""

    create: list[Wanted] = field(default_factory=list)
    delete: list[str] = field(default_factory=list)
    keep: int = 0
    foreign: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "create": [item.as_dict() for item in self.create],
            "delete": list(self.delete),
            "keep": self.keep,
            "foreign": self.foreign,
        }


# --- pure: the text ----------------------------------------------------------
def escape(value: str) -> str:
    """RFC 5545 §3.3.11 text escaping.

    The backslash goes first, or every escape this function adds is escaped
    again by the ones after it.
    """
    out = str(value or "").replace("\\", "\\\\")
    for char, replacement in ((";", "\\;"), (",", "\\,")):
        out = out.replace(char, replacement)
    return out.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def fold(line: str) -> str:
    """Fold one content line to 75 octets, continuations indented by a space."""
    raw = line.encode("utf-8")
    if len(raw) <= FOLD_OCTETS:
        return line
    out: list[str] = []
    rest = raw
    limit = FOLD_OCTETS
    while len(rest) > limit:
        cut = limit
        # Never cut inside a UTF-8 sequence: continuation bytes are 0b10xxxxxx.
        while cut > 0 and (rest[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(rest[:cut].decode("utf-8"))
        rest = rest[cut:]
        limit = FOLD_OCTETS - 1  # the leading space of a continuation counts
    out.append(rest.decode("utf-8"))
    return "\r\n ".join(out)


def _stamp(value: datetime) -> str:
    return dt_util.as_utc(value).strftime("%Y%m%dT%H%M%SZ")


def _when(value: str, all_day: bool) -> tuple[str, str]:
    """``(parameters, value)`` for a DTSTART/DTEND out of what HA handed over.

    An all-day entry is a ``VALUE=DATE``; a timed one is written in UTC, which
    is correct without shipping a VTIMEZONE nobody would read.
    """
    if all_day:
        parsed = dt_util.parse_date(value[:10])
        if parsed is None:
            raise MirrorError(f"{value!r} is not a date")
        return ";VALUE=DATE", parsed.strftime("%Y%m%d")
    parsed_dt = dt_util.parse_datetime(value)
    if parsed_dt is None:
        raise MirrorError(f"{value!r} is not a date-time")
    if parsed_dt.tzinfo is None:
        parsed_dt = dt_util.as_local(parsed_dt)
    return "", _stamp(parsed_dt)


def build_ics(item: Wanted, *, now: datetime) -> str:
    """One VEVENT, wrapped in the VCALENDAR a ``PUT`` needs. CRLF throughout."""
    start_params, start_value = _when(item.start, item.all_day)
    end_params, end_value = _when(item.end, item.all_day)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{item.uid}",
        f"DTSTAMP:{_stamp(now)}",
        f"DTSTART{start_params}:{start_value}",
        f"DTEND{end_params}:{end_value}",
        f"SUMMARY:{escape(item.summary)}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


# --- pure: what belongs there -------------------------------------------------
def uid_for(source_entity_id: str, start: str, end: str, summary: str) -> str:
    """The UID of one mirrored entry — a fingerprint of source and content.

    Two properties carry the whole design: it is **stable**, so a run that
    changes nothing writes nothing; and it names its **source**, so a second
    mirror into the same calendar neither collides with this one nor tidies it
    away.
    """
    who = hashlib.sha1(source_entity_id.encode("utf-8")).hexdigest()[:8]
    what = hashlib.sha1(
        "\u001f".join([source_entity_id, start, end, summary]).encode("utf-8")
    ).hexdigest()[:20]
    return f"{UID_PREFIX}-{who}-{what}@{UID_DOMAIN}"


def owns(uid: str, source_entity_id: str) -> bool:
    """Whether this mirror wrote that UID for this source."""
    who = hashlib.sha1(source_entity_id.encode("utf-8")).hexdigest()[:8]
    return str(uid or "").startswith(f"{UID_PREFIX}-{who}-") and str(uid).endswith(
        f"@{UID_DOMAIN}"
    )


def wanted_from_events(
    source_entity_id: str, events: list[dict[str, Any]]
) -> list[Wanted]:
    """``calendar.get_events`` output → the entries the target should hold.

    Entries without a start are dropped rather than guessed at, and duplicates
    collapse on their own: two identical events produce one UID.
    """
    out: dict[str, Wanted] = {}
    for raw in events or []:
        start = str(raw.get("start") or "").strip()
        if not start:
            continue
        end = str(raw.get("end") or "").strip() or start
        summary = str(raw.get("summary") or "").strip()
        all_day = "T" not in start
        uid = uid_for(source_entity_id, start, end, summary)
        out.setdefault(
            uid,
            Wanted(uid=uid, summary=summary, start=start, end=end, all_day=all_day),
        )
    return list(out.values())


def plan(
    wanted: list[Wanted], present: list[str], source_entity_id: str
) -> Plan:
    """What to create and what to delete. Nothing else is touched.

    ``present`` is every UID the target holds inside the window. The ones this
    mirror does not own are counted and left where they are — the single rule
    that makes a wrong target harmless.
    """
    result = Plan()
    have = {uid for uid in present if owns(uid, source_entity_id)}
    result.foreign = len(present) - len(have)
    keys = {item.uid for item in wanted}
    result.create = [item for item in wanted if item.uid not in have]
    result.delete = sorted(uid for uid in have if uid not in keys)
    result.keep = len(have & keys)
    return result


# --- what may be a target ----------------------------------------------------
@callback
def available_targets(hass: HomeAssistant) -> list[dict[str, str]]:
    """Every calendar entity that can actually be mirrored into.

    **Only CalDAV ones**, and the panel cannot work that out for itself: whose
    integration serves an entity is in the entity registry, not in
    ``hass.states``. Offering the rest and failing at the first press would be
    worse than not offering them — the failure would arrive as
    "…is served by 'local_calendar'" long after the choice was made and saved.
    """
    registry = er.async_get(hass)
    out: list[dict[str, str]] = []
    for entity in registry.entities.values():
        if entity.domain != "calendar" or entity.platform != CALDAV_DOMAIN:
            continue
        state = hass.states.get(entity.entity_id)
        name = (
            entity.name
            or (state.attributes.get("friendly_name") if state else None)
            or entity.original_name
            or entity.entity_id
        )
        out.append({"entity_id": entity.entity_id, "name": str(name)})
    return sorted(out, key=lambda item: item["entity_id"])


# --- the wire ----------------------------------------------------------------
def _target_calendar(client: Any, calendar_id: str) -> Any:
    calendars = {cal.id: cal for cal in client.principal().calendars()}
    calendar = calendars.get(calendar_id)
    if calendar is None:
        raise MirrorError(
            f"The server no longer offers a calendar {calendar_id!r} — "
            "it was renamed or removed"
        )
    return calendar


def _read(client: Any, calendar_id: str, start: datetime, end: datetime) -> list[tuple[str, Any]]:
    """Blocking. ``(uid, object)`` for everything in the target's window.

    Unexpanded: this mirror only ever writes single dated entries, and an
    expanded search would hand back one object per occurrence of anything else
    that happens to be a series — each carrying the master's URL, which is the
    hazard P42 measured.
    """
    calendar = _target_calendar(client, calendar_id)
    out: list[tuple[str, Any]] = []
    for obj in calendar.search(start=start, end=end, event=True, expand=False):
        uid = str(obj.icalendar_component.get("UID") or "")
        if uid:
            out.append((uid, obj))
    return out


def _apply(
    client: Any,
    calendar_id: str,
    create: list[str],
    delete: list[Any],
) -> tuple[int, int]:
    """Blocking. Delete first, then create.

    The order matters on a server that refuses a second entry with the same
    UID: an entry that moved is a delete of the old UID and a create of the new
    one, and doing it the other way round would leave both.
    """
    calendar = _target_calendar(client, calendar_id)
    removed = 0
    for obj in delete:
        obj.delete()
        removed += 1
    added = 0
    for ical in create:
        calendar.save_event(ical)
        added += 1
    return added, removed


async def async_mirror(
    hass: HomeAssistant,
    source_entity_id: str,
    target_entity_id: str,
    *,
    dry_run: bool = True,
    days: int = MIRROR_DAYS,
    today: date | None = None,
) -> dict[str, Any]:
    """Bring one target calendar in line with one Home Assistant calendar.

    Returns what it did — or, on a dry run, what it would have done. The counts
    are the point: "create 19, delete 0, foreign 0" is a healthy first run, and
    "foreign 64" is the wrong calendar caught before it was emptied.
    """
    if not source_entity_id or not target_entity_id:
        raise MirrorError("A mirror needs both a source and a target calendar")
    if source_entity_id == target_entity_id:
        raise MirrorError(
            "Source and target are the same calendar — that would mirror it "
            "onto itself"
        )

    entry, calendar_id = _caldav_entry(hass, target_entity_id)
    client = _client(entry)

    start_day = today or dt_util.now().date()
    start = dt_util.as_local(datetime.combine(start_day, time.min))
    end = start + timedelta(days=max(int(days), 1))

    answer = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": source_entity_id,
            "start_date_time": start.isoformat(),
            "end_date_time": end.isoformat(),
        },
        blocking=True,
        return_response=True,
    )
    events = list(((answer or {}).get(source_entity_id) or {}).get("events") or [])
    wanted = wanted_from_events(source_entity_id, events)

    present = await hass.async_add_executor_job(_read, client, calendar_id, start, end)
    todo = plan(wanted, [uid for uid, _obj in present], source_entity_id)

    created = removed = 0
    if not dry_run and (todo.create or todo.delete):
        by_uid = {uid: obj for uid, obj in present}
        now = dt_util.now()
        created, removed = await hass.async_add_executor_job(
            _apply,
            client,
            calendar_id,
            [build_ics(item, now=now) for item in todo.create],
            [by_uid[uid] for uid in todo.delete if uid in by_uid],
        )
        _LOGGER.info(
            "Mirrored %s into %s: %s created, %s deleted",
            source_entity_id,
            target_entity_id,
            created,
            removed,
        )

    return {
        "source": source_entity_id,
        "target": target_entity_id,
        "dry_run": dry_run,
        "days": int(days),
        "events": len(events),
        "created": created,
        "deleted": removed,
        **todo.as_dict(),
    }
