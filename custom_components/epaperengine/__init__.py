"""The ePaperEngine integration.

ePaperEngine drives a Samsung EM32DX e-paper panel from Home Assistant. The
product has two halves that share the name: **this integration** holds the
configuration, resolves which view belongs on the wall and reports the state,
and the **ePaperEngine add-on** does the rendering, dithering and the MDC push
(a custom integration may not ship Chromium and Node — an add-on may).

The full specification lives in the development repo (``gesamtsystem-fsd.md``).

Scope of this version (phase 3): the integration keeps its stores, serves the
frontend catalogs, exposes the two services the add-on talks through, and makes
a render run observable with two sensors. Panel, card, WebSocket API and the
priority resolution follow in phase 4.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, I18N_DIRNAME, I18N_STATIC_URL, PLATFORMS
from .coordinator import EPaperEngineCoordinator
from .services import async_register_services, async_unregister_services
from .store import EPaperEngineStore

_LOGGER = logging.getLogger(__name__)

# A static path cannot be unregistered, so guard it with its own flag: it has to
# survive an entry reload and must not be registered twice.
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ePaperEngine from a config entry."""
    store = EPaperEngineStore(hass)
    config = await store.async_load_config()
    state = await store.async_load_state()

    # Write both documents back once, so they exist under ``.storage/`` from the
    # very first start instead of only after the panel saves something. Two
    # reasons, both borrowed from GardenESP (``coordinator.async_setup``):
    # the documents are inspectable while debugging against the test instance,
    # and this is the point where the first schema migration will have to
    # persist its result. ``async_load_*`` merges the current defaults over what
    # was stored, so this also writes back sections that a newer version added.
    await store.async_save_config(config)
    await store.async_save_state(state)

    coordinator = EPaperEngineCoordinator(hass, entry, store, config, state)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await _async_register_i18n(hass)
    async_register_services(hass)

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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the services once the last entry is gone.

    Not done in ``async_unload_entry``: a reload runs unload → setup, and
    removing the services in between would make them briefly vanish from
    automations and from the add-on's reach.
    """
    if not hass.data.get(DOMAIN):
        async_unregister_services(hass)


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
