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

The recipe cache (FSD §9) belongs here too and arrives in phase 5.
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
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from . import mediapath
from .addon import AddonClient, AddonError
from .const import (
    DISPLAY_PROBE_INTERVAL_MIN,
    RENDER_DEBOUNCE_S,
    RENDER_INTERVAL_MIN,
    RESULT_IDLE,
    SIGNAL_STATE_UPDATED,
    VIEW_GUESTS,
)
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

        self.addon = AddonClient(hass)
        self.addon.set_base((config.get("display") or {}).get("renderer_url"))

        self.target: Resolution = resolve(config, state, {}, dt_util.utcnow())
        self.display: dict[str, Any] = {}
        # Why the last request to the add-on failed, if it did. Not a run result:
        # a run that never started cannot report one, and pretending otherwise
        # would leave "render_failed" standing with no add-on to explain it.
        self.addon_error: str | None = None

        self._unsubscribe: list[CALLBACK_TYPE] = []
        self._schedule_watch: CALLBACK_TYPE | None = None
        self._manual_timer: CALLBACK_TYPE | None = None
        self._pending: tuple[str, bool] = ("startup", False)
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

        await self.store.async_save_state(self.state)
        self._async_arm_manual_timer()
        if not self._async_refresh_target():
            # Same view as before — but the reason changed, and a manual pin the
            # user just pressed should still put the current picture up.
            self._async_notify()
            self.async_request_render("set_view")

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

        await self.store.async_save_config(self.config)
        self.addon.set_base((self.config.get("display") or {}).get("renderer_url"))
        self._async_watch_schedules()
        self._async_arm_manual_timer()

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
            "recipes": {"selection": list(cfg["recipes"].get("selection") or [])},
            "calendar": {"sources": list(cfg["calendar"].get("sources") or [])},
            "layout": {
                "color_bar_px": cfg["calendar"].get("color_bar_px"),
                "show_empty_days": cfg["calendar"].get("show_empty_days"),
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
            "next_change": next_change.isoformat() if next_change else None,
            "display": self.display,
            "addon_error": self.addon_error,
            "addon_url": self.addon.base,
            # Unsigned on purpose — the frontend signs it through ``auth/sign_path``
            # right before it sets ``src`` (see ``mediapath.py``).
            "preview_path": mediapath.preview_url_path(self.hass, self.config),
            "wall_path": mediapath.wall_url_path(self.hass, self.config),
        }
