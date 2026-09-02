"""Runtime state holder for ePaperEngine.

The integration owns configuration and state; the *work* — rendering, dithering,
pushing — happens in the add-on. So there is nothing to poll and no
``DataUpdateCoordinator`` to build. What this class does instead:

* keeps the two store documents and writes them back,
* **resolves the target view** on every input that could change it (FSD §5) and
  keeps the reason, so the card can say *why* something is on the wall,
* holds the manual override together with its deadline, including the timer that
  makes the fallback actually happen rather than only on the next restart,
* asks the add-on for a run — debounced (FSD §6.1) — and drives the timed net,
* keeps the last MDC probe of the display.

The recipe cache (FSD §9) hangs here as well — its own object
(``recipes.RecipeCache``), driven by a second timer, because its clock is a
rate limit and has nothing to do with the render cycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from . import caldav_writer, mediapath
from .addon import AddonClient, AddonError
from .const import (
    ANNIVERSARY_SYNC_HOUR,
    ANNIVERSARY_SYNC_MINUTE,
    CALENDAR_KIND_BIRTHDAYS,
    CALENDAR_REFRESH_MIN_GAP_S,
    DEFAULT_ANNIVERSARY_WRITEBACK,
    DEFAULT_CALENDAR_DAYS_BIRTHDAYS,
    DEFAULT_CALENDAR_DAYS_EVENTS,
    DEFAULT_GUEST_ANGLE,
    DEFAULT_GUEST_OUTLINE,
    DEFAULT_GUEST_OUTLINE_COLOR,
    DEFAULT_GUEST_OUTLINE_PX,
    DEFAULT_GUEST_COLOR,
    DEFAULT_GUEST_FONT,
    DEFAULT_GUEST_GREETING_PX,
    DEFAULT_GUEST_NAME_PX,
    DEFAULT_RECIPE_SYNC_INTERVAL_H,
    DISPLAY_PROBE_INTERVAL_MIN,
    RECIPE_SYNC_MIN_GAP_S,
    RENDER_DEBOUNCE_S,
    RENDER_INTERVAL_MIN,
    RESULT_IDLE,
    SIGNAL_STATE_UPDATED,
    VIEW_CALENDAR,
    VIEW_GUESTS,
)
from . import scaling
from .recipes import MAX_SELECTION, RecipeCache
from .resolve import Resolution, manual_deadline, resolve
from .store import EPaperEngineStore

_LOGGER = logging.getLogger(__name__)

# Config sections the panel may write. Everything else in the document is
# derived or owned by the integration; an unknown section is rejected rather
# than merged, so a stale panel cannot quietly invent keys.
WRITABLE_SECTIONS = frozenset(
    {"display", "media", "views", "schedule", "calendar", "recipes", "photos", "guests"}
)

# Which sections make the picture on the wall different when they change. A
# change to one of these triggers a render; a change to, say, ``display.mdc_pin``
# does not — it changes where the image goes, not what it shows.
RENDER_RELEVANT = frozenset({"views", "schedule", "calendar", "recipes", "photos", "guests", "media"})

# The guest fields that must never reach the renderer as ``None``.
#
# Phase 4 stored ``font: null`` and had no size keys at all, so an installation
# that predates the guest view carries a section the add-on would have to guess
# at. The add-on *does* guess sanely — ``guest_layout.plan`` treats every missing
# field as its default — but the **panel** would show an unselected dropdown and
# empty size fields, and a Save from that page would write the nulls straight
# back. Filling them in once, here, is the difference between a page that opens
# ready to use and one that has to be repaired before it can be used.
GUEST_DEFAULTS: dict[str, Any] = {
    "font": DEFAULT_GUEST_FONT,
    "name_px": DEFAULT_GUEST_NAME_PX,
    "greeting_px": DEFAULT_GUEST_GREETING_PX,
    "color": DEFAULT_GUEST_COLOR,
    "angle": DEFAULT_GUEST_ANGLE,
    "outline": DEFAULT_GUEST_OUTLINE,
    "outline_px": DEFAULT_GUEST_OUTLINE_PX,
    "outline_color": DEFAULT_GUEST_OUTLINE_COLOR,
}


def _normalise_guests(config: dict[str, Any]) -> None:
    """Fill the guest fields that carry a default, in place.

    ``band`` is dropped rather than left lying: it was a real key for one
    afternoon (integration 0.9.0), the greeting has had no ground of its own
    since [Festlegung P23], and a stale key in the document would come back as a
    question every time somebody read the store.
    """
    guests = config.setdefault("guests", {})
    guests.pop("band", None)
    for key, default in GUEST_DEFAULTS.items():
        if guests.get(key) is None:
            guests[key] = default


class EPaperEngineCoordinator:
    """Holds the config and state documents and serves the render document."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: EPaperEngineStore,
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.config = config
        self.state = state
        _normalise_guests(self.config)

        self.addon = AddonClient(hass)
        self.addon.set_base((config.get("display") or {}).get("renderer_url"))

        # Reads the credentials through a callback rather than getting them
        # handed over once: the panel can change the account at any time, and a
        # cache holding the login it was built with would keep using the old one
        # until the next restart.
        self.recipes = RecipeCache(hass, lambda: self.config["recipes"].get("paprika_login"))

        self.target: Resolution = resolve(config, state, {}, dt_util.utcnow())
        self.display: dict[str, Any] = {}
        # Why the last request to the add-on failed, if it did. Not a run result:
        # a run that never started cannot report one, and pretending otherwise
        # would leave "render_failed" standing with no add-on to explain it.
        self.addon_error: str | None = None

        self._unsubscribe: list[CALLBACK_TYPE] = []
        self._schedule_watch: CALLBACK_TYPE | None = None
        self._recipe_timer: CALLBACK_TYPE | None = None
        self._anniversary_timer: CALLBACK_TYPE | None = None
        self._manual_timer: CALLBACK_TYPE | None = None
        self._pending: tuple[str, bool] = ("startup", False)
        self._calendar_refreshed_at: datetime | None = None
        self._recipe_synced_at: datetime | None = None
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=RENDER_DEBOUNCE_S,
            immediate=True,
            function=self._async_render_now,
        )

    # --- lifecycle ------------------------------------------------------------
    async def async_setup(self) -> None:
        """Start the timers and the listeners (FSD §6.1)."""
        await self.recipes.async_load()
        self._async_refresh_target(render=False)
        self._async_watch_schedules()
        self._async_arm_manual_timer()

        self._unsubscribe.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(minutes=RENDER_INTERVAL_MIN)
            )
        )
        self._unsubscribe.append(
            async_track_time_interval(
                self.hass,
                self._async_probe_tick,
                timedelta(minutes=DISPLAY_PROBE_INTERVAL_MIN),
            )
        )
        self._async_arm_recipe_timer()
        self._async_arm_anniversary_timer()

    async def async_shutdown(self) -> None:
        """Drop every timer and listener — a reload must not leave one behind."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        if self._schedule_watch is not None:
            self._schedule_watch()
            self._schedule_watch = None
        if self._manual_timer is not None:
            self._manual_timer()
            self._manual_timer = None
        if self._anniversary_timer is not None:
            self._anniversary_timer()
            self._anniversary_timer = None
        if self._recipe_timer is not None:
            self._recipe_timer()
            self._recipe_timer = None
        await self._debouncer.async_shutdown()

    # --- state ----------------------------------------------------------------
    @property
    def last_run(self) -> dict[str, Any] | None:
        return self.state.get("last_run")

    @property
    def last_result(self) -> str:
        run = self.last_run
        return str(run.get("result")) if run else RESULT_IDLE

    @property
    def last_push_at(self) -> datetime | None:
        push = self.state.get("last_push")
        if not push or not push.get("at"):
            return None
        return dt_util.parse_datetime(str(push["at"]))

    @property
    def manual(self) -> dict[str, Any] | None:
        return self.state.get("manual")

    @callback
    def _async_notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id))

    async def async_report_run(
        self,
        result: str,
        view: str,
        error: str | None = None,
        warning: str | None = None,
        image_hash: str | None = None,
        pushed: bool = False,
    ) -> None:
        """Record the outcome of a render run (FSD §6.2 step 10).

        Called by the add-on over the HA API once a run finishes — successfully
        or not. ``last_push`` is only touched when something actually went to the
        display, so "when did the wall last change" stays answerable even after a
        string of unchanged runs.
        """
        now = dt_util.utcnow().isoformat()
        self.state["last_run"] = {
            "result": result,
            "view": view,
            "at": now,
            "error": error,
            "warning": warning,
        }
        if pushed:
            self.state["last_push"] = {"at": now, "hash": image_hash}
        # The add-on answered, so whatever we last failed to reach it with is
        # history. Leaving it standing would keep an old outage on the card.
        self.addon_error = None
        await self.store.async_save_state(self.state)
        self._async_notify()
        _LOGGER.debug("Run reported: %s (%s)", result, view)

    # --- target view (FSD §5) -------------------------------------------------
    def _schedule_states(self) -> dict[str, str]:
        """Current state of every configured schedule helper.

        The entity lookup lives here so ``resolve.py`` stays free of ``hass`` —
        that is what makes the rule testable without Home Assistant.
        """
        states: dict[str, str] = {}
        for entry in (self.config.get("schedule") or {}).values():
            if not isinstance(entry, dict):
                continue
            entity_id = entry.get("entity_id")
            if not entity_id:
                continue
            state = self.hass.states.get(str(entity_id))
            states[str(entity_id)] = state.state if state else "unavailable"
        return states

    @callback
    def _async_refresh_target(self, render: bool = True) -> bool:
        """Re-resolve the target view. Returns True when it changed."""
        previous = self.target
        self.target = resolve(
            self.config, self.state, self._schedule_states(), dt_util.utcnow()
        )
        changed = (previous.view, previous.source) != (self.target.view, self.target.source)
        if changed:
            _LOGGER.info(
                "Target view %s -> %s (%s)", previous.view, self.target.view, self.target.source
            )
            self._async_notify()
            if render:
                self.async_request_render(f"target:{self.target.view}")
        return changed

    @callback
    def _async_watch_schedules(self) -> None:
        """(Re)subscribe to the configured schedule helpers.

        Torn down and rebuilt on every configuration write rather than kept as a
        catch-all listener: the set of entities is small, and a stale
        subscription to a helper the user just unhooked would keep re-rendering.
        """
        if self._schedule_watch is not None:
            self._schedule_watch()
            self._schedule_watch = None

        entities = [
            str(entry["entity_id"])
            for entry in (self.config.get("schedule") or {}).values()
            if isinstance(entry, dict) and entry.get("entity_id")
        ]
        if not entities:
            return

        @callback
        def _changed(_event: Event) -> None:
            self._async_refresh_target()

        self._schedule_watch = async_track_state_change_event(self.hass, entities, _changed)

    @callback
    def _async_arm_manual_timer(self) -> None:
        """Fire once when the manual override lapses (FSD §5).

        Without this the fallback would only happen at the next timed run, and
        "back to automatic in 2 h 48 min" on the card would be a promise the
        system does not keep to the minute.
        """
        if self._manual_timer is not None:
            self._manual_timer()
            self._manual_timer = None
        deadline = manual_deadline(self.manual)
        if deadline is None:
            return

        @callback
        def _lapsed(_now: datetime) -> None:
            self._manual_timer = None
            _LOGGER.info("Manual override lapsed, back to automatic")
            self.hass.async_create_task(self.async_set_view(None))

        self._manual_timer = async_track_point_in_utc_time(self.hass, _lapsed, deadline)

    # --- anniversaries (P42) --------------------------------------------------
    @callback
    def _async_arm_anniversary_timer(self) -> None:
        """(Re)start the nightly write-back clock.

        A *time of day*, not an interval — see ``ANNIVERSARY_SYNC_HOUR``: the
        number an entry should carry changes at a date boundary, so a clock that
        drifts across midnight would answer differently depending on when it
        last fired.

        **No catch-up, deliberately, and that is the difference to the recipe
        clock.** That one syncs on startup when a sync is overdue, because an
        empty cache is a visible hole. This one would fire while Home Assistant
        is still starting, and it needs somebody else's integration to be up:
        ``caldav_writer`` borrows the ``DAVClient`` the CalDAV integration
        authenticated (P42). Too early means a logged failure that is not one.
        A missed night costs nothing — the same number is still waiting the
        next night.
        """
        if self._anniversary_timer is not None:
            self._anniversary_timer()
            self._anniversary_timer = None

        section = self.config.get("calendar") or {}
        enabled = section.get("anniversary_writeback")
        if enabled is None:
            enabled = DEFAULT_ANNIVERSARY_WRITEBACK
        if not enabled:
            return

        self._anniversary_timer = async_track_time_change(
            self.hass,
            self._async_anniversary_tick,
            hour=ANNIVERSARY_SYNC_HOUR,
            minute=ANNIVERSARY_SYNC_MINUTE,
            second=0,
        )

    async def _async_anniversary_tick(self, _now: datetime) -> None:
        """The nightly run. Never a dry run — a dry run at 00:15 helps nobody.

        Cheap when there is nothing to do, which is 364 nights out of 365: with
        no anniversary source configured it does not talk to any server at all,
        and with one it reads the calendar and writes nothing back.
        """
        await self.async_write_back_anniversaries(dry_run=False)

    # --- recipes (FSD §9) -----------------------------------------------------
    @callback
    def _async_arm_recipe_timer(self, catch_up: bool = True) -> None:
        """(Re)start the sync clock, and catch up if a sync is overdue.

        Two things in one place on purpose. The timer alone would leave a fresh
        installation with an empty cache until the interval elapsed — a whole
        day of "no recipes" after typing in the account. ``catch_up`` closes
        that, and it stays rate-limit-safe because it syncs only when one is
        actually **due**: a restart loop cannot turn into a request loop.
        """
        if self._recipe_timer is not None:
            self._recipe_timer()
            self._recipe_timer = None

        hours = float(
            (self.config.get("recipes") or {}).get("sync_interval_h")
            or DEFAULT_RECIPE_SYNC_INTERVAL_H
        )
        hours = max(hours, 1.0)  # a sub-hour sync clock is an accident, not a wish

        async def _tick(_now: datetime) -> None:
            await self.async_sync_recipes()

        self._recipe_timer = async_track_time_interval(
            self.hass, _tick, timedelta(hours=hours)
        )
        if catch_up and self._recipe_sync_due(hours):
            self.hass.async_create_task(self.async_sync_recipes())

    def _recipe_sync_due(self, hours: float) -> bool:
        """Is the cache older than the interval? No credentials = nothing due."""
        if not (self.config.get("recipes") or {}).get("paprika_login"):
            return False
        last = self.recipes.synced_at
        if not last:
            return True
        parsed = dt_util.parse_datetime(str(last))
        if parsed is None:
            return True
        return dt_util.utcnow() - parsed >= timedelta(hours=hours)

    async def async_set_recipe_selection(
        self, selection: list[str], servings: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """What is cooked tonight — the household's decision, not the admin's.

        [Festlegung 2026-08-31, Wolfgang.] Picking a recipe was administrator
        business only because it happened to be stored as configuration, and the
        panel wrote it through ``config/set``. It is the same kind of decision
        as ``set_view``: whoever may change what hangs on the shared wall may
        choose what hangs there tonight.

        **The patch is built here, never taken from the caller.** Exactly two
        keys move. The Paprika account and the sync interval live in the same
        store section, and a command that forwarded a caller's dict would be a
        way for anybody to write them — which is the reason the narrow command
        exists instead of a relaxed ``config/set``.

        Everything else — the three-column cap, dropping a portion count for a
        recipe nobody picked, the render run — already happens in
        ``async_set_config``, and doing it a second time here is how the two
        would drift apart.
        """
        patch: dict[str, Any] = {"selection": [str(uid) for uid in selection if uid]}
        if servings is not None:
            patch["servings"] = dict(servings)
        return await self.async_set_config({"recipes": patch})

    async def async_sync_recipes(self) -> dict[str, Any]:
        """Pull the collection from Paprika and tell everybody what came of it.

        Rate-limited rather than permission-limited since 2026-08-31: the button
        is open to the household, and the endpoint is documented to ban by IP
        (FSD §9.2). A press inside the gap answers the cache status with
        ``skipped``, so the panel can say "just synced" instead of pretending to
        have fetched.
        """
        now = dt_util.utcnow()
        if (
            self._recipe_synced_at is not None
            and (now - self._recipe_synced_at).total_seconds() < RECIPE_SYNC_MIN_GAP_S
        ):
            _LOGGER.debug("Recipes were just synced, not asking Paprika again")
            return {**self.recipes.status(), "skipped": True}
        # Stamped before the call, not after: a sync that hangs must not become
        # a way to hold the door open for a second one.
        self._recipe_synced_at = now
        status = await self.recipes.async_sync()
        # The wall may be showing one of these very recipes, so a sync that
        # changed something is a reason to render — but only then.
        if status.get("fetched") or status.get("removed"):
            self.async_request_render("recipes")
        self._async_notify()
        return {**status, "skipped": False}

    def next_change_at(self) -> datetime | None:
        """When the wall is next due to change on its own.

        The earliest of the manual deadline and the next event of any configured
        schedule helper. ``None`` means "nothing scheduled" — the card then says
        nothing rather than inventing a time.
        """
        candidates: list[datetime] = []
        deadline = manual_deadline(self.manual)
        if deadline is not None:
            candidates.append(deadline)
        for entry in (self.config.get("schedule") or {}).values():
            if not isinstance(entry, dict) or not entry.get("entity_id"):
                continue
            state = self.hass.states.get(str(entry["entity_id"]))
            if state is None:
                continue
            # ``schedule`` helpers carry the next window boundary as an
            # attribute; nothing else in HA knows it, and recomputing it here
            # would mean reimplementing the helper.
            raw = state.attributes.get("next_event")
            parsed = dt_util.parse_datetime(str(raw)) if raw else None
            if parsed is not None:
                candidates.append(parsed)
        return min(candidates) if candidates else None

    # --- manual override ------------------------------------------------------
    async def async_set_view(self, view: str | None) -> None:
        """Pin a view by hand, or hand control back to the automatic resolution.

        ``None`` clears the override. The deadline follows ``manual_timeout_h``,
        except for the views listed in ``manual_exceptions`` — guests stay for
        the weekend, not for four hours (FSD §5).
        """
        views_cfg = self.config.get("views") or {}
        if view is None:
            self.state["manual"] = None
        else:
            # A float, not an int: FSD §4 calls it "a number", 4.5 h is a
            # sensible thing to want, and truncating it would silently turn a
            # deliberate half hour into "no deadline at all".
            timeout_h = float(views_cfg.get("manual_timeout_h") or 0)
            exceptions = set(views_cfg.get("manual_exceptions") or ())
            now = dt_util.utcnow()
            until = (
                None
                if timeout_h <= 0 or view in exceptions
                else (now + timedelta(hours=timeout_h)).isoformat()
            )
            self.state["manual"] = {"view": view, "at": now.isoformat(), "until": until}
            # Switching to the guest view *is* switching guest mode on: the panel
            # would otherwise need two controls for one intention.
            if view == VIEW_GUESTS:
                self.state["guests_active"] = True
                self.state.setdefault("guests_since", None)
                if not self.state["guests_since"]:
                    self.state["guests_since"] = now.isoformat()

        await self.store.async_save_state(self.state)
        self._async_arm_manual_timer()
        if not self._async_refresh_target():
            # Same view as before — but the reason changed, and a manual pin the
            # user just pressed should still put the current picture up.
            self._async_notify()
            self.async_request_render("set_view")

    # --- guest mode (FSD §8.4) ------------------------------------------------
    async def async_set_guests(self, active: bool) -> None:
        """Switch guest mode on or off.

        **On** is all it takes to put the greeting up: ``guests`` is a candidate
        of the priority list (FSD §5) and stands above the schedule, so no manual
        pin is needed and none is set — that is what keeps the visit exempt from
        the four-hour fallback without a special case in the timer.

        **Off** also drops a manual pin that happens to be on the guest view.
        Without that the wall would keep the greeting up with guest mode
        switched off, and the panel would show a switch that changed nothing:
        pinning the view *is* switching the mode on (``async_set_view``), so the
        two have to come apart again together.
        """
        active = bool(active)
        if active == bool(self.state.get("guests_active")):
            return
        now = dt_util.utcnow()
        self.state["guests_active"] = active
        self.state["guests_since"] = now.isoformat() if active else None
        manual = self.manual
        if not active and manual and manual.get("view") == VIEW_GUESTS:
            self.state["manual"] = None

        await self.store.async_save_state(self.state)
        self._async_arm_manual_timer()
        _LOGGER.info("Guest mode %s", "on" if active else "off")
        if not self._async_refresh_target():
            # The wall was not showing guests anyway (something above it in the
            # priority list wins) — the switch still has to be visible, and the
            # greeting itself may have changed while it was off.
            self._async_notify()
            self.async_request_render("guests")

    async def async_background_list(self) -> dict[str, Any]:
        """The guest backgrounds with their thumbnail paths (FSD §8.4).

        The add-on refreshes and lists; the paths are built here, because only
        the integration knows ``media.root`` and how Home Assistant serves its
        media directories. Unsigned — the panel signs them right before it sets
        ``src`` (``mediapath.py``).
        """
        answer = await self.addon.async_backgrounds()
        root = mediapath.media_root(self.config)
        backgrounds = [
            {
                "digest": entry.get("digest"),
                "name": entry.get("name"),
                "thumb": mediapath.media_url_path(
                    self.hass, f"{root}/{mediapath.SUBDIR_PREVIEW_BACKGROUNDS}/{entry.get('digest')}.jpg"
                ),
            }
            for entry in (answer.get("backgrounds") or [])
            if entry.get("digest")
        ]
        return {
            "total": answer.get("total", len(backgrounds)),
            "backgrounds": backgrounds,
            "root": root,
            "folder": f"{root}/{mediapath.SUBDIR_BACKGROUNDS}",
            "error": answer.get("error"),
        }

    # --- configuration --------------------------------------------------------
    async def async_set_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge a patch from the panel into the config document (FSD §4).

        Section-wise merge, not a wholesale replace: two panel pages open at once
        would otherwise let the second save undo the first one's section.
        """
        unknown = set(patch) - WRITABLE_SECTIONS
        if unknown:
            raise ValueError(f"unknown configuration section(s): {', '.join(sorted(unknown))}")

        for section, values in patch.items():
            if isinstance(values, dict) and isinstance(self.config.get(section), dict):
                self.config[section] = {**self.config[section], **values}
            else:
                self.config[section] = values

        # Three columns is a layout constant, not a preference (FSD §8.2). The
        # panel enforces it too; this is where it has to hold, because the store
        # is what the renderer reads.
        recipes_cfg = self.config.get("recipes") or {}
        selection = [str(uid) for uid in (recipes_cfg.get("selection") or []) if uid]
        recipes_cfg["selection"] = selection[:MAX_SELECTION]
        # A target portion count for a recipe nobody picked any more is dead
        # weight that would come back to life the next time it is chosen.
        recipes_cfg["servings"] = {
            uid: value
            for uid, value in (recipes_cfg.get("servings") or {}).items()
            if uid in recipes_cfg["selection"]
        }

        _normalise_guests(self.config)

        await self.store.async_save_config(self.config)
        self.addon.set_base((self.config.get("display") or {}).get("renderer_url"))
        self._async_watch_schedules()
        self._async_arm_manual_timer()
        if "calendar" in patch:
            # The switch and the source list live in the same section: a
            # calendar that just became an anniversary source is exactly as
            # good a reason to re-arm as the switch itself.
            self._async_arm_anniversary_timer()
        if "recipes" in patch:
            # Covers both halves of that page: a changed interval moves the
            # clock, and a freshly typed account makes the first sync due.
            self._async_arm_recipe_timer()

        changed_target = self._async_refresh_target()
        if not changed_target and RENDER_RELEVANT & set(patch):
            self.async_request_render("config")
        self._async_notify()
        return self.config

    # --- render requests (FSD §6.1) -------------------------------------------
    @callback
    def async_request_render(self, reason: str, force: bool = False) -> None:
        """Ask the add-on for a run, debounced.

        ``force`` — the panel's "Push now" — skips the debounce: it is a
        deliberate press, and making somebody wait 20 s for the thing they just
        asked for would only look broken.
        """
        self._pending = (reason, force)
        if force:
            self.hass.async_create_task(self._async_render_now())
            return
        self.hass.async_create_task(self._debouncer.async_call())

    async def _async_render_now(self) -> None:
        reason, force = self._pending
        self._pending = (reason, False)  # a forced request is spent once used
        try:
            await self.addon.async_render(reason, force=force)
            self.addon_error = None
        except AddonError as exc:
            self.addon_error = str(exc)
            _LOGGER.warning("Could not reach the add-on: %s", exc)
            self._async_notify()

    async def _async_tick(self, _now: datetime) -> None:
        """The timed net (FSD §6.1).

        It renders unconditionally rather than only on a changed target view:
        the whole point is to catch what has no trigger — an appointment moved on
        a phone, a new file in the photo folder. It stays cheap because a run
        only pushes when the image actually changed (FSD §11).
        """
        self._async_refresh_target(render=False)
        self.async_request_render("timer")

    async def _async_probe_tick(self, _now: datetime) -> None:
        await self.async_refresh_display()

    async def async_refresh_display(self, fresh: bool = False) -> dict[str, Any]:
        """Ask the add-on to probe the display over MDC."""
        self.display = await self.addon.async_display(fresh=fresh)
        self._async_notify()
        return self.display

    # --- photos (FSD §8.3) ----------------------------------------------------
    def _read_photo_index(self) -> dict[str, str]:
        """The add-on's ``digest -> filename`` map. Blocking; call in the executor."""
        index_path = Path(mediapath.media_root(self.config)) / "processed" / "photos" / "index.json"
        try:
            return dict(json.loads(index_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}

    async def async_photo_list(self) -> dict[str, Any]:
        """The cached photos, for the picker in the panel.

        Read from the add-on's index rather than from the source folder: the
        index is what the renderer actually picks from, and it already carries
        the content hash the thumbnails are named after. File I/O in the executor
        — the tree lives on a NAS.
        """
        index = await self.hass.async_add_executor_job(self._read_photo_index)
        root = mediapath.media_root(self.config)
        photos = [
            {
                "digest": digest,
                "name": name,
                "thumb": mediapath.media_url_path(
                    self.hass, f"{root}/{mediapath.SUBDIR_PREVIEW_PHOTOS}/{digest}.jpg"
                ),
            }
            for digest, name in sorted(index.items(), key=lambda item: item[1].lower())
        ]
        return {"total": len(photos), "photos": photos, "root": root}

    def _scaled_selection(self) -> list[dict[str, Any]]:
        """The picked recipes, each cooked for its target number of people."""
        cfg = self.config["recipes"]
        targets = cfg.get("servings") or {}
        picked = self.recipes.selected([str(uid) for uid in (cfg.get("selection") or [])])
        return [
            scaling.scaled(recipe, scaling.parse_number(str(targets.get(recipe.get("uid")) or "")))
            for recipe in picked
        ]

    # --- render document ------------------------------------------------------
    def photo_slot(self, now: datetime | None = None) -> int:
        """Deterministic photo counter (FSD §5).

        Derived from the wall clock, **not** drawn at random: otherwise every
        accidental render run would change the picture and burn a panel refresh.
        The integration only supplies the counter — mapping it onto actual files
        is the add-on's job, since only it knows the photo cache.
        """
        interval = int(self.config["photos"].get("rotation_interval_min") or 60)
        interval = max(interval, 1)
        stamp = (now or dt_util.utcnow()).timestamp()
        return int(stamp // (interval * 60))

    # --- calendar (FSD §8.1, kalenderkonzept.md §7/§8) ------------------------
    async def async_calendar_events(
        self, *, refresh: bool = True
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
        """``({entity_id: [event, …]}, {entity_id: "why it failed"})``.

        **One call per source, and every failure caught on its own**
        (kalenderkonzept §7.1). Measured on HA 2026.8.2 why that matters: a
        non-existent entity inside a multi-target call is dropped *silently* —
        200, no error, the key simply absent — and a call whose targets are all
        gone answers 500. A collective call would therefore turn a dead
        calendar into a quiet hole in the wall. One call each turns it into a
        named line under the header.

        ``refresh`` runs ``homeassistant.update_entity`` first. Not optional in
        practice: a Remote Calendar over a published ICS polls every 24 h
        (kalenderkonzept §8), and without this the wall reliably shows
        yesterday. It is best effort — a source that cannot be refreshed is
        still worth asking.
        """
        section = self.config.get("calendar") or {}
        sources = [
            source
            for source in (section.get("sources") or [])
            if isinstance(source, dict) and source.get("entity_id")
        ]
        if not sources:
            return {}, {}

        if refresh:
            await self._async_refresh_calendars([str(s["entity_id"]) for s in sources])

        now = dt_util.now()
        # From **midnight**, not from now: "today" on the wall is the whole day.
        # ``duration`` would start the window at this instant, and this morning's
        # birthday — a 09:00–09:15 entry — would be gone from the wall by 09:16
        # whatever the "show past entries" switch says.
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        events: dict[str, list[dict[str, Any]]] = {}
        failed: dict[str, str] = {}
        for source in sources:
            entity_id = str(source["entity_id"])
            # Holidays use the appointment window rather than one of their own
            # [P48]: the page's horizon is ``query_days_events`` whatever the
            # source, so a separate setting for them would be a field that
            # changes nothing — the anniversary window is the exception because
            # one wants notice enough to buy a present, and it is already capped
            # by the same horizon.
            days = (
                section.get("query_days_birthdays") or DEFAULT_CALENDAR_DAYS_BIRTHDAYS
                if source.get("kind") == CALENDAR_KIND_BIRTHDAYS
                else section.get("query_days_events") or DEFAULT_CALENDAR_DAYS_EVENTS
            )
            try:
                answer = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": entity_id,
                        "start_date_time": start.isoformat(),
                        "end_date_time": (start + timedelta(days=int(days))).isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
            except Exception as err:  # noqa: BLE001 - one dead source must not stop the wall
                _LOGGER.warning("Calendar %s did not answer: %s", entity_id, err)
                failed[entity_id] = f"{type(err).__name__}: {err}"
                continue
            entry = (answer or {}).get(entity_id) or {}
            events[entity_id] = list(entry.get("events") or [])
        return events, failed

    async def _async_refresh_calendars(self, entity_ids: list[str]) -> None:
        """``homeassistant.update_entity`` on the sources, best effort.

        Skipped when the sources were pulled less than
        ``CALENDAR_REFRESH_MIN_GAP_S`` ago: "Sync now" pulls them itself and then
        asks for a render run, and that run arrives within a second or two —
        without the gap a single press would fetch every published ICS twice.
        Nothing else comes this close; the timed net is 15 minutes apart.
        """
        now = dt_util.utcnow()
        if (
            self._calendar_refreshed_at is not None
            and (now - self._calendar_refreshed_at).total_seconds()
            < CALENDAR_REFRESH_MIN_GAP_S
        ):
            _LOGGER.debug("Calendar sources were just refreshed, not pulling again")
            return
        # Stamped before the call, not after: a source that times out must not
        # turn into a retry loop.
        self._calendar_refreshed_at = now
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "update_entity",
                {"entity_id": entity_ids},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - a stale calendar beats no calendar
            _LOGGER.debug("Could not refresh the calendar sources: %s", err)

    async def async_calendar_probe(self) -> dict[str, Any]:
        """What the panel's source table shows: entries per source, or the error.

        Without the refresh — this runs while somebody is looking at a settings
        page, and pulling three ICS files on every repaint would be rude to the
        servers on the other end.
        """
        events, failed = await self.async_calendar_events(refresh=False)
        return {
            "counts": {entity_id: len(items) for entity_id, items in events.items()},
            "failed": failed,
            "at": dt_util.now().isoformat(),
        }

    async def async_calendar_sync(self) -> dict[str, Any]:
        """What "Sync now" does: pull the sources, count them, redraw the wall.

        The other button on that page ("recount") deliberately does *not* pull:
        it fires while somebody is looking at a settings page. This one is a
        deliberate press, so it does the whole chain — ``update_entity`` on every
        source, a fresh ``get_events`` for the numbers on screen, and a render
        run, because otherwise a calendar that was just corrected still waits up
        to 15 minutes for the timed net.

        The render is *requested*, not awaited: the add-on answers 202 and works
        asynchronously (FSD §3.2), and the panel would be holding a spinner for
        a picture it is not showing.

        ``on_wall`` says whether that run will actually redraw the calendar. A
        wall currently showing photos takes the fresh data and shows none of it —
        ``async_render_document`` queries the calendar for no other view — and
        without this flag "Sync now" would look broken to whoever pressed it.
        """
        events, failed = await self.async_calendar_events(refresh=True)
        self.async_request_render("calendar_sync")
        return {
            "counts": {entity_id: len(items) for entity_id, items in events.items()},
            "failed": failed,
            "at": dt_util.now().isoformat(),
            "on_wall": self.target.view == VIEW_CALENDAR,
        }

    async def async_write_back_anniversaries(
        self, *, dry_run: bool = True, limit: int | None = None
    ) -> dict[str, Any]:
        """Write the year count into the anniversary calendars themselves [P42].

        Only sources of kind ``birthdays`` — an appointment has no year in
        brackets and nothing to compute, and running over a diary would be a way
        to damage one for no gain.

        Every source is tried on its own and its failure named, the same rule as
        ``async_calendar_events``: one calendar served by Local Calendar (which
        cannot be written back to at all) must not hide the result of the one
        that can.

        The default is a **dry run**. This is the only place in the project that
        changes data on somebody else's server, and the answer shows what it
        would do before it does it. ``limit`` caps how many entries are actually
        saved, so the first live run can be one entry.
        """
        section = self.config.get("calendar") or {}
        sources = [
            source
            for source in (section.get("sources") or [])
            if isinstance(source, dict)
            and source.get("entity_id")
            and source.get("kind") == CALENDAR_KIND_BIRTHDAYS
        ]

        results: list[dict[str, Any]] = []
        failed: dict[str, str] = {}
        budget = limit
        for source in sources:
            entity_id = str(source["entity_id"])
            try:
                answer = await caldav_writer.async_write_back(
                    self.hass, entity_id, dry_run=dry_run, limit=budget
                )
            except caldav_writer.WriteBackError as err:
                failed[entity_id] = str(err)
                continue
            except Exception as err:  # noqa: BLE001 - one bad source must not hide the rest
                _LOGGER.warning("Writing back to %s failed: %s", entity_id, err)
                failed[entity_id] = f"{type(err).__name__}: {err}"
                continue
            results.append(answer)
            if budget is not None:
                # The cap is over the whole run, not per calendar: "try one
                # entry" must mean one, even with two anniversary calendars.
                budget = max(0, budget - answer["written"])

        answer = {
            "dry_run": dry_run,
            "sources": results,
            "failed": failed,
            "changed": sum(r["changed"] for r in results),
            "written": sum(r["written"] for r in results),
            "at": dt_util.now().isoformat(),
        }

        # Only a real run leaves a trace. A dry run changed nothing, and letting
        # it overwrite "last written" would turn the one line the panel shows
        # into a line that cannot be trusted: it has to answer "when did this
        # installation last touch the calendar", not "when was the button last
        # pressed". The entry list is deliberately left out — 64 titles do not
        # belong in the state file, and the panel already has the answer it just
        # received.
        if not dry_run:
            self.state["anniversaries"] = {
                "at": answer["at"],
                "total": sum(r["total"] for r in results),
                "changed": answer["changed"],
                "written": answer["written"],
                "failed": failed or None,
            }
            await self.store.async_save_state(self.state)
            self._async_notify()
        return answer

    async def async_render_document(self) -> dict[str, Any]:
        """The render document, with the calendar filled in when it is needed.

        The query is skipped for every other view — FSD §6.2 step 2 says "only
        when the view is ``calendar``", and thirty days of three calendars on
        every photo run would be work nobody reads.
        """
        document = self.render_document()
        if document.get("view") != VIEW_CALENDAR:
            return document
        events, failed = await self.async_calendar_events()
        document["calendar"] = {**document["calendar"], "events": events, "failed": failed}
        return document

    def render_document(self) -> dict[str, Any]:
        """The single document the add-on pulls each run (FSD §6.2 step 1).

        The renderer *pulls*, Home Assistant does not push — that way no request
        schema has to be maintained on both sides.

        Since phase 4 the view is **resolved** (FSD §5) rather than fixed, and it
        travels with the reason it won: the add-on logs it, and a run that ends
        up rendering the wrong thing can be traced without guessing.
        """
        cfg = self.config
        return {
            "generated_at": dt_util.utcnow().isoformat(),
            "view": self.target.view,
            "target": self.target.as_dict(),
            # The language the *wall* speaks [Festlegung P9, 2026-08-21]: the
            # rendered views follow ``hass.language`` like every other surface
            # (FSD §3.0a), so the household reads its own language on the panel
            # and a public installation still falls back to English. Sent as the
            # raw HA token including the region (``de``, ``en-GB``); the add-on
            # normalises it against the catalogs it actually carries. Not a
            # configuration key on purpose — a second language switch next to
            # Home Assistant's own is a setting nobody remembers changing.
            "language": self.hass.config.language,
            # The MDC PIN travels **here and nowhere else**. FSD §4 hands secrets
            # to the add-on *on request over the HA API* rather than copying them
            # into the add-on options, where they would sit in plain text in a
            # file the user can open from the Supervisor UI. The price is that
            # the PIN shows up in the response of a service anyone with HA access
            # can call — acceptable, because that same access already reaches the
            # display through this integration.
            "display": {
                "host": cfg["display"].get("host"),
                "mdc_pin": cfg["display"].get("mdc_pin"),
                "mac": cfg["display"].get("mac"),
                # The one-display rule of FSD §14, as a value the add-on can
                # act on. Missing means on: an installation from before this
                # key must not go quiet on its own.
                "push_enabled": cfg["display"].get("push_enabled", True),
            },
            # Root of the image store (FSD §3.4). ``None`` means the add-on falls
            # back to ``/media/epaperengine`` — see the note in ``store.py`` for
            # why this is configuration rather than a constant.
            "media": {"root": cfg["media"].get("root")},
            "photos": {
                "source_folder": cfg["photos"].get("source_folder"),
                "rotation_interval_min": cfg["photos"].get("rotation_interval_min"),
                "slot": self.photo_slot(),
            },
            "guests": dict(cfg["guests"]),
            # **The full text of the selected recipes travels here** (FSD §9.1):
            # the add-on never talks to Paprika, so whatever is not in this
            # document does not exist as far as the wall is concerned. Three
            # recipes are a few kilobytes — fine for a service response, and the
            # exact reason ``get_render_data`` is not an entity attribute.
            # **The full text of the selected recipes travels here** (FSD §9.1),
            # already cooked for the number of people it is meant for: scaling
            # is arithmetic on the data, not a layout decision, so it happens
            # once here rather than in the renderer (``scaling.py``).
            "recipes": {
                "selection": list(cfg["recipes"].get("selection") or []),
                "items": self._scaled_selection(),
            },
            # Sources, layout **and** the events themselves — the last of them
            # filled in by ``async_render_document`` and only when the calendar
            # is what is going on the wall. ``now`` travels with it because the
            # add-on container has no idea what time zone this household is in,
            # and "today" is the value the whole page hangs on.
            "calendar": {
                **{
                    key: cfg["calendar"].get(key)
                    for key in (
                        "query_days_events",
                        "query_days_birthdays",
                        "color_bar_px",
                        "show_empty_days",
                        "show_past_today",
                    )
                },
                "sources": list(cfg["calendar"].get("sources") or []),
                "now": dt_util.now().isoformat(),
                "events": {},
                "failed": {},
            },
        }

    # --- what the front-ends read --------------------------------------------
    def status_document(self) -> dict[str, Any]:
        """Everything card and panel show, in one answer (FSD §3.1).

        One round trip rather than five: the card renders as a whole or not at
        all, and a half-filled card that fills in over three more replies looks
        broken. Small by construction — the growing things (photo list, later the
        recipe cache) have their own commands.
        """
        next_change = self.next_change_at()
        return {
            "target": self.target.as_dict(),
            "result": self.last_result,
            "last_run": self.last_run,
            "last_push": self.state.get("last_push"),
            "manual": self.manual,
            "guests_active": bool(self.state.get("guests_active")),
            "guests_since": self.state.get("guests_since"),
            "next_change": next_change.isoformat() if next_change else None,
            "display": self.display,
            # Small and fixed in size — the collection itself goes over
            # ``recipes/search``, never through here.
            "recipes": self.recipes.status(),
            # What the nightly write-back last did — four numbers and a
            # timestamp, so the panel can say it without asking again.
            "anniversaries": self.state.get("anniversaries"),
            # The hour the nightly run fires at, told rather than repeated:
            # the panel says "every night at 00:15" and must not be the
            # second place that number is written down.
            "anniversary_time": (
                f"{ANNIVERSARY_SYNC_HOUR:02d}:{ANNIVERSARY_SYNC_MINUTE:02d}"
            ),
            "addon_error": self.addon_error,
            "addon_url": self.addon.base,
            # Unsigned on purpose — the frontend signs it through ``auth/sign_path``
            # right before it sets ``src`` (see ``mediapath.py``).
            "preview_path": mediapath.preview_url_path(self.hass, self.config),
            "wall_path": mediapath.wall_url_path(self.hass, self.config),
        }
