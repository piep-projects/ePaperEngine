"""Runtime state holder for ePaperEngine.

Small on purpose. The integration owns configuration and state; the *work*
(rendering, dithering, pushing) happens in the add-on, which reports back
through the ``report_run`` service. So there is nothing to poll and no
``DataUpdateCoordinator`` to build — this class holds the two documents, hands
out the render document, and tells the entities when something changed.

It will grow: priority resolution (FSD §5) and the recipe cache (§9) belong
here in phase 4 and 5.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    RESULT_IDLE,
    SIGNAL_STATE_UPDATED,
    VIEW_PHOTOS,
)
from .store import EPaperEngineStore

_LOGGER = logging.getLogger(__name__)


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
        await self.store.async_save_state(self.state)
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id))
        _LOGGER.debug("Run reported: %s (%s)", result, view)

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

        Phase 3 fixes the target view to ``photos``; resolving it from the
        priority list (FSD §5) arrives with phase 4, and the recipe and guest
        sections fill up in phase 5. They are present but empty rather than
        missing, so the add-on can bind to them today.
        """
        cfg = self.config
        return {
            "generated_at": dt_util.utcnow().isoformat(),
            # Phase 3: hard-wired. Phase 4 replaces this with the resolved view.
            "view": VIEW_PHOTOS,
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
