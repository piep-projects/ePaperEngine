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
    DEFAULT_MANUAL_TIMEOUT_H,
    DEFAULT_PRIORITY,
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
        "calendar": {
            "sources": [],  # [{entity_id, person, color}]
            "query_days_events": 30,
            "query_days_birthdays": 30,
            "color_bar_px": 6,
            "show_empty_days": True,
        },
        "recipes": {
            "paprika_login": None,  # {username, password} — secret
            "sync_interval_h": 24,
            "selection": [],  # up to 3 recipe uids, set from the panel search
        },
        "photos": {
            "source_folder": None,  # default /media/epaperengine/photos/, FSD §3.4
            "rotation_interval_min": 60,
            "cache_state": None,
        },
        "guests": {
            "name": None,
            "greeting": None,
            "background": None,  # from /media/epaperengine/backgrounds/
            "font": None,        # script font + size
        },
    }


def default_state() -> dict[str, Any]:
    """Runtime state skeleton (FSD §6/§11)."""
    return {
        "manual": None,      # {"view": ..., "until": <iso>} or None
        "last_run": None,    # {"view", "at", "result", "error"}
        "last_push": None,   # {"at", "hash"}
        "guests_active": False,
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
