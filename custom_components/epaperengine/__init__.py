"""The ePaperEngine integration.

ePaperEngine drives a Samsung EM32DX e-paper panel from Home Assistant. The
product has two halves that share the name: **this integration** holds the
configuration, resolves which view belongs on the wall and reports the state,
and the **ePaperEngine add-on** does the rendering, dithering and the MDC push
(a custom integration may not ship Chromium and Node — an add-on may).

The full specification lives in the development repo (``gesamtsystem-fsd.md``).

Scope of this version: the integration loads, keeps its stores and serves the
frontend translation catalogs. Entities, panel, card and the WebSocket API
follow in the next build step.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, I18N_DIRNAME, I18N_STATIC_URL, PLATFORMS
from .store import EPaperEngineStore

_LOGGER = logging.getLogger(__name__)

# A static path cannot be unregistered, so guard it with its own flag: it has to
# survive an entry reload and must not be registered twice.
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ePaperEngine from a config entry."""
    store = EPaperEngineStore(hass)
    data = {
        "store": store,
        "config": await store.async_load_config(),
        "state": await store.async_load_state(),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    await _async_register_i18n(hass)

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = True
    if PLATFORMS:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_register_i18n(hass: HomeAssistant) -> None:
    """Serve the frontend translation catalogs (i18n concept §6).

    One shared catalog per language for card and panel, fetched as
    ``/epaperengine_i18n/<lang>.json?v=<manifest version>``. Served straight
    from the integration directory — no copy into ``www/``, so HACS unzipping
    with stale timestamps cannot leave a second, older copy behind.
    """
    if hass.data.get(_STATIC_REGISTERED):
        return
    catalogs = Path(__file__).parent / I18N_DIRNAME
    await hass.http.async_register_static_paths(
        [StaticPathConfig(I18N_STATIC_URL, str(catalogs), True)]
    )
    hass.data[_STATIC_REGISTERED] = True
    _LOGGER.info("Serving frontend translation catalogs at %s", I18N_STATIC_URL)
