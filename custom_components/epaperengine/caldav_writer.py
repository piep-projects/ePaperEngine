"""The transport for P42: the year count, written back into the real calendar.

``anniversaries.py`` decides *what* an entry should read. This module is the
part that goes over the wire — find the CalDAV server, read the entries, write
the changed ones back. The split is deliberate: the half that can silently
corrupt somebody's real calendar is the half that is testable without a server.

**Why not through Home Assistant.** Measured at the source (HA 2026.8.3, and
confirmed live: ``supported_features: 1`` on every CalDAV calendar entity): the
CalDAV integration sets ``CalendarEntityFeature.CREATE_EVENT`` and defines
neither ``async_update_event`` nor ``async_delete_event``. Creating works,
changing never does. HA keeps no local copy either — it is a pass-through, not a
cache — so there is no sync cycle to ride in the other direction.

**No second set of credentials** [P42, Wolfgang's objection]. The CalDAV config
entry already carries ``url``/``username``/``password``, and
``entry.runtime_data`` is the finished, authenticated ``DAVClient``
(``type CalDavConfigEntry = ConfigEntry[caldav.DAVClient]``). The price is an
undocumented coupling to somebody else's integration — but it breaks *visibly*:
if ``runtime_data`` ever stops being a client, the first call raises here
instead of writing nonsense.

**The library is never imported.** ``caldav`` pulls in ``lxml``, a C extension,
and a custom integration may only ship pure Python (manifest ``requirements``
is empty on purpose). So this module never says ``import caldav``: it uses the
client the CalDAV integration already loaded, duck-typed. Without that
integration there is simply nothing to write to, which is the correct answer.

**Change, don't swap** [P42]. A ``PUT`` to the same address replaces the entry —
no duplicate, no gap, and no delete permission needed.

The one hazard worth naming, because it is silent and destroys data
[gemessen 2026-08-31]: an *expanded* search returns one object per occurrence,
each carrying **the master's URL** and a ``RECURRENCE-ID`` but **no ``RRULE``**.
Saving one of those would replace a yearly series with a single dated event, and
every future anniversary would vanish. So the two searches are kept apart — the
expanded one is read-only, only the unexpanded one is ever saved — and
``_is_writable`` refuses anything carrying a ``RECURRENCE-ID`` even so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import anniversaries
from .wall_text import WallText

_LOGGER = logging.getLogger(__name__)

CALDAV_DOMAIN = "caldav"

# Far enough that every yearly entry has its next occurrence inside the window,
# with room to spare for a leap day and a 29 February moved to the 28th. Shorter
# would silently give some entries no reference date at all.
LOOKAHEAD_DAYS = 400

# The catalogue key the wall renders the suffix from. Named once, here, and read
# out of the **shared** catalogue — see ``publish.py``: SHARED.
SUFFIX_KEY = "calendar.years"


class WriteBackError(Exception):
    """Something the person pressing the button needs to read."""


@dataclass(frozen=True)
class Planned:
    """One entry, its target title, and the occurrence the count belongs to."""

    uid: str
    old: str
    new: str
    on: date

    @property
    def changed(self) -> bool:
        return self.old != self.new

    def as_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "old": self.old,
            "new": self.new,
            "on": self.on.isoformat(),
            "changed": self.changed,
        }


def _caldav_entry(hass: HomeAssistant, entity_id: str) -> tuple[Any, str]:
    """``(config entry, calendar id)`` for a CalDAV calendar entity.

    The mapping is exact rather than by name, and it is not guesswork: the
    CalDAV integration builds ``unique_id = f"{entry.entry_id}-{calendar.id}"``
    (``caldav/calendar.py:176``), and ``calendar.id`` is the last path segment of
    the calendar's URL. Verified live for all three entities of the test
    instance. Two calendars may share a display name; they cannot share this.
    """
    registry = er.async_get(hass)
    entity = registry.async_get(entity_id)
    if entity is None:
        raise WriteBackError(f"{entity_id} is not in the entity registry")
    if entity.platform != CALDAV_DOMAIN:
        raise WriteBackError(
            f"{entity_id} is served by {entity.platform!r}, not CalDAV — "
            "only CalDAV entries can be written back to"
        )
    entry = hass.config_entries.async_get_entry(entity.config_entry_id or "")
    if entry is None:
        raise WriteBackError(f"{entity_id} has no config entry any more")
    prefix = f"{entry.entry_id}-"
    if not (entity.unique_id or "").startswith(prefix):
        raise WriteBackError(
            f"{entity_id} has an unexpected unique id — the CalDAV integration "
            "changed how it names its entities"
        )
    return entry, entity.unique_id[len(prefix) :]


def _client(entry: Any) -> Any:
    """The ``DAVClient`` the CalDAV integration authenticated.

    Deliberately loud. This is the undocumented coupling of P42, and the whole
    argument for accepting it was that it fails where somebody can see it.
    """
    client = getattr(entry, "runtime_data", None)
    if client is None or not hasattr(client, "principal"):
        raise WriteBackError(
            "The CalDAV integration is not loaded, or no longer hands out a "
            "client — nothing can be written back"
        )
    return client


def _is_writable(component: Any) -> bool:
    """Whether this object may be saved back.

    A ``RECURRENCE-ID`` marks a single expanded occurrence, and those carry the
    master's URL. Saving one replaces the whole series with that one date.
    """
    return "RECURRENCE-ID" not in component


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _collect(client: Any, calendar_id: str, today: date, suffix: str) -> list[tuple[Any, Planned]]:
    """Blocking. Every entry of one calendar, with what it should read.

    Two searches on purpose (see the module docstring): the expanded one only
    answers *when each entry happens next*, the unexpanded one is the thing that
    gets written.

    The reference date is each entry's **own next occurrence**, not today. A
    single series title can carry only one number, and this is the only choice
    that agrees with the wall: on 20 December an anniversary on 5 January reads
    the January count, which is exactly the off-by-one P42 found.
    """
    calendars = {cal.id: cal for cal in client.principal().calendars()}
    calendar = calendars.get(calendar_id)
    if calendar is None:
        raise WriteBackError(
            f"The server no longer offers a calendar {calendar_id!r} — "
            "it was renamed or removed"
        )

    start = datetime.combine(today, time.min)
    end = start + timedelta(days=LOOKAHEAD_DAYS)

    next_on: dict[str, date] = {}
    for occurrence in calendar.search(start=start, end=end, event=True, expand=True):
        component = occurrence.icalendar_component
        uid = str(component.get("UID") or "")
        when = _as_date(getattr(component.get("DTSTART"), "dt", None))
        if not uid or when is None:
            continue
        if uid not in next_on or when < next_on[uid]:
            next_on[uid] = when

    out: list[tuple[Any, Planned]] = []
    for obj in calendar.search(start=start, end=end, event=True, expand=False):
        component = obj.icalendar_component
        uid = str(component.get("UID") or "")
        title = str(component.get("SUMMARY") or "")
        if not uid or not _is_writable(component):
            continue
        on = next_on.get(uid, today)
        out.append((obj, uid, title, on))

    changes = anniversaries.plan([(uid, title, on) for _o, uid, title, on in out], suffix)
    return [
        (obj, Planned(uid=change.uid, old=change.old, new=change.new, on=on))
        for (obj, _uid, _title, on), change in zip(out, changes, strict=True)
    ]


def _write(pairs: list[tuple[Any, Planned]]) -> int:
    """Blocking. ``PUT`` each changed entry back to its own address.

    Editing the parsed component rather than the raw text is not fussiness:
    ``SUMMARY`` is folded at 75 octets (RFC 5545) and a long name with umlauts
    is folded mid-character-sequence. A regex over the raw ICS would corrupt
    exactly the entries this project cares about.
    """
    written = 0
    for obj, planned in pairs:
        component = obj.icalendar_component
        if not _is_writable(component):  # belt and braces; _collect filtered already
            continue
        component["SUMMARY"] = planned.new
        obj.save()
        written += 1
    return written


async def async_write_back(
    hass: HomeAssistant,
    entity_id: str,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Bring one anniversary calendar's titles up to date.

    ``dry_run`` is the default, and that is the point: the answer shows every
    entry and what would become of it before anything is written. ``limit`` caps
    how many are actually saved — "try it on one entry first" is a real step,
    not a wish.

    **Nothing to change means no HTTP at all**, which is what makes a daily run
    harmless.
    """
    entry, calendar_id = _caldav_entry(hass, entity_id)
    client = _client(entry)
    suffix = WallText(hass.config.language).template(SUFFIX_KEY)
    on = today or date.today()

    pairs = await hass.async_add_executor_job(_collect, client, calendar_id, on, suffix)
    changed = [pair for pair in pairs if pair[1].changed]
    to_write = changed if limit is None else changed[:limit]

    written = 0
    if to_write and not dry_run:
        written = await hass.async_add_executor_job(_write, to_write)
        _LOGGER.info("Wrote %s anniversary title(s) back to %s", written, entity_id)

    return {
        "entity_id": entity_id,
        "dry_run": dry_run,
        "language": WallText(hass.config.language).language,
        "suffix": suffix,
        "total": len(pairs),
        "changed": len(changed),
        "written": written,
        "entries": [planned.as_dict() for _obj, planned in pairs],
    }
