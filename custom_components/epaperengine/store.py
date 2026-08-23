"""Persistence layer for ePaperEngine (FSD §4).

Two versioned ``Store`` files under ``.storage/``:
  * ``epaperengine.config`` — user configuration, edited in the panel. Single
    source of truth; no YAML, no helper entities for these values.
  * ``epaperengine.state``  — runtime state that must survive a restart: the
    manual override with its deadline, the last render run, the last push.

Secrets (MDC PIN, Paprika login) live in the config store — never in plain YAML,
and they are handed to the add-on only on request over the HA API.

Config keys are English, like every other technical identifier in this
integration (see ``const.py``); the German labels come from the panel catalogs.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CALENDAR_BAR_PX,
    DEFAULT_CALENDAR_DAYS_BIRTHDAYS,
    DEFAULT_CALENDAR_DAYS_EVENTS,
    DEFAULT_CALENDAR_SHOW_EMPTY_DAYS,
    DEFAULT_CALENDAR_SHOW_PAST_TODAY,
    DEFAULT_GUEST_ANGLE,
    DEFAULT_GUEST_OUTLINE,
    DEFAULT_GUEST_OUTLINE_COLOR,
    DEFAULT_GUEST_OUTLINE_PX,
    DEFAULT_GUEST_COLOR,
    DEFAULT_GUEST_FONT,
    DEFAULT_GUEST_GREETING_PX,
    DEFAULT_GUEST_NAME_PX,
    DEFAULT_MANUAL_TIMEOUT_H,
    DEFAULT_PRIORITY,
    DEFAULT_RECIPE_SYNC_INTERVAL_H,
    STORAGE_VERSION,
    STORE_CONFIG,
    STORE_STATE,
    VIEW_CALENDAR,
    VIEW_GUESTS,
)


def default_config() -> dict[str, Any]:
    """The configuration document as it looks before the user touches it.

    Mirrors the tree in FSD §4. Sections are created empty rather than omitted
    so the panel can bind to them without null checks.
    """
    return {
        "display": {
            "host": None,
            "mdc_pin": None,
            "mac": None,
            "renderer_url": None,  # add-on address, FSD §3.2
        },
        # Where the image store lives (FSD §3.4). A *configured* path, not the
        # constant the specification writes, and the reason is measured: Home
        # Assistant mounts network storage as a **subdirectory** of ``/media``
        # (``/media/<mount-name>/``) [measured 2026-08-21 on ha-test1, CIFS mount
        # ``media_test_ocean3``]. The literal ``/media/epaperengine`` would
        # therefore land on the local disk of the HA machine, not on the NAS that
        # §3.4 asks for — and the mount name differs between test and production.
        # ``None`` keeps the specification's path as the fallback.
        "media": {"root": None},
        "views": {
            "priority": list(DEFAULT_PRIORITY),  # ordered, sortable in the panel
            "manual_timeout_h": DEFAULT_MANUAL_TIMEOUT_H,  # 0 = never fall back
            "manual_exceptions": [VIEW_GUESTS],
            "fallback": VIEW_CALENDAR,
        },
        # Per view: a HA ``schedule`` helper entity plus its rank. Overlapping
        # windows are not an error — the lowest rank wins (FSD §5).
        "schedule": {},
        # Quellenagnostisch (FSD §8.1): what is behind an entity — M365 publish
        # ICS, Google, CalDAV, Local Calendar — never reaches this document.
        # ``kind`` is the one distinction that does: ``birthdays`` turns the
        # description into an age and keeps the entry up all day.
        "calendar": {
            "sources": [],  # [{entity_id, person, color, kind}]
            "query_days_events": DEFAULT_CALENDAR_DAYS_EVENTS,
            "query_days_birthdays": DEFAULT_CALENDAR_DAYS_BIRTHDAYS,
            "color_bar_px": DEFAULT_CALENDAR_BAR_PX,
            "show_empty_days": DEFAULT_CALENDAR_SHOW_EMPTY_DAYS,
            "show_past_today": DEFAULT_CALENDAR_SHOW_PAST_TODAY,
        },
        # The cached collection itself lives in its own store (``STORE_RECIPES``,
        # FSD §9.1); what is configuration is the account, the sync clock and
        # which three recipes are on the wall.
        "recipes": {
            "paprika_login": None,  # {username, password} — secret, FSD §4
            "sync_interval_h": DEFAULT_RECIPE_SYNC_INTERVAL_H,
            "selection": [],  # up to 3 recipe uids, set from the panel search
            # ``{uid: number}`` — cook this one for that many people instead of
            # the number it was written for (FSD §8.2, Festlegung 2026-08-22).
            # A separate map rather than a richer ``selection`` so the priority
            # resolution and the panel keep reading a plain list of uids.
            "servings": {},
        },
        "photos": {
            "source_folder": None,  # default /media/epaperengine/photos/, FSD §3.4
            "rotation_interval_min": 60,
            "cache_state": None,
        },
        # FSD §4 writes ``font (Schreibschrift-Font, Grad)`` as one entry. It
        # is split into three flat keys here, and the reason is the merge right
        # below: ``async_load_config`` merges *sections*, one level deep. A
        # nested ``font`` object would be taken from the store whole, so adding a
        # size later would leave every existing installation without it and with
        # no default to fall back on.
        "guests": {
            "name": None,
            "greeting": None,
            # The **content hash** of a cached background, not a filename
            # (FSD §8.4 / §8.3): renaming a file on the NAS must not silently
            # change which picture greets the visitors. ``None`` = flat white.
            "background": None,
            "font": DEFAULT_GUEST_FONT,  # one of const.GUEST_FONTS
            "name_px": DEFAULT_GUEST_NAME_PX,
            "greeting_px": DEFAULT_GUEST_GREETING_PX,
            # One of const.GUEST_COLORS — a Spectra primary, so the glyph edges
            # carry no dither raster (FSD §8.4, Festlegung P23). This is what
            # replaced the lightened band: white script over a dark picture is
            # the same remedy without covering a third of it with a stripe.
            "color": DEFAULT_GUEST_COLOR,
            # Degrees, positive clockwise. The add-on bounds it at ±45°.
            "angle": DEFAULT_GUEST_ANGLE,
            # The outline — FSD §8.4's third remedy, and the only one that makes
            # the greeting independent of what it sits on. ``outline_px`` is the
            # width that can be seen; the add-on doubles it for the CSS.
            "outline": DEFAULT_GUEST_OUTLINE,
            "outline_px": DEFAULT_GUEST_OUTLINE_PX,
            "outline_color": DEFAULT_GUEST_OUTLINE_COLOR,
        },
    }


def default_state() -> dict[str, Any]:
    """Runtime state skeleton (FSD §6/§11)."""
    return {
        "manual": None,      # {"view": ..., "until": <iso>} or None
        "last_run": None,    # {"view", "at", "result", "error"}
        "last_push": None,   # {"at", "hash"}
        # Guest mode is **state, not configuration** (FSD §5): it is switched on
        # when the doorbell rings and off when the visitors leave, it survives a
        # restart, and it is exempt from the manual timeout — hence its own
        # ``since`` rather than borrowing the manual override's.
        "guests_active": False,
        "guests_since": None,
    }


class EPaperEngineStore:
    """Thin wrapper around the two HA stores."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._config: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORE_CONFIG)
        self._state: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORE_STATE)

    # --- config ---------------------------------------------------------------
    async def async_load_config(self) -> dict[str, Any]:
        """Load the config document, filling in sections added by later versions."""
        stored = await self._config.async_load() or {}
        merged = default_config()
        for section, defaults in merged.items():
            value = stored.get(section)
            if isinstance(defaults, dict) and isinstance(value, dict):
                merged[section] = {**defaults, **value}
            elif value is not None:
                merged[section] = value
        return merged

    async def async_save_config(self, data: dict[str, Any]) -> None:
        await self._config.async_save(data)

    # --- state ----------------------------------------------------------------
    async def async_load_state(self) -> dict[str, Any]:
        stored = await self._state.async_load() or {}
        return {**default_state(), **stored}

    async def async_save_state(self, data: dict[str, Any]) -> None:
        await self._state.async_save(data)
