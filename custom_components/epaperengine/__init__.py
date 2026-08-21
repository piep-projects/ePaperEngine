"""The ePaperEngine integration.

ePaperEngine drives a Samsung EM32DX e-paper panel from Home Assistant. The
product has two halves that share the name: **this integration** holds the
configuration, resolves which view belongs on the wall and reports the state,
and the **ePaperEngine add-on** does the rendering, dithering and the MDC push
(a custom integration may not ship Chromium and Node — an add-on may).

The full specification lives in the development repo (``gesamtsystem-fsd.md``).

Scope of this version (phase 4): the two stores, the frontend catalogs, the
services the add-on talks through, the WebSocket API, the sidebar panel and the
Lovelace card, the priority resolution with its manual override, and the timed
net that keeps the wall current. The remaining views — calendar, recipes,
guests, error — follow in phase 5.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from .const import (
    CARD_FILENAME,
    CARD_WWW_URL,
    DOMAIN,
    I18N_DIRNAME,
    I18N_STATIC_URL,
    PANEL_CUSTOM_NAME,
    PANEL_FILENAME,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PLATFORMS,
)
from .coordinator import EPaperEngineCoordinator
from .services import async_register_services, async_unregister_services
from .store import EPaperEngineStore
from .websocket_api import async_register as async_register_ws

_LOGGER = logging.getLogger(__name__)

# A static path cannot be unregistered, so guard it with its own flag: it has to
# survive an entry reload and must not be registered twice.
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"
_CARD_REGISTERED = f"{DOMAIN}_card_registered"


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
    await coordinator.async_setup()

    async_register_ws(hass)
    async_register_services(hass)
    version = await hass.async_add_executor_job(_version)
    await _async_register_frontend(hass, version)
    await _async_register_card(hass, version)

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    The sidebar panel is deliberately **not** removed here: a reload runs
    unload → setup, and taking the panel away in between throws whoever is
    standing on it back to the default dashboard. It goes only on real removal;
    the re-registration in setup is a guarded no-op.
    """
    unloaded = True
    if PLATFORMS:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: EPaperEngineCoordinator | None = hass.data[DOMAIN].pop(
            entry.entry_id, None
        )
        if coordinator is not None:
            await coordinator.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the services and the panel once the last entry is gone.

    Not done in ``async_unload_entry``: a reload runs unload → setup, and
    removing the services in between would make them briefly vanish from
    automations and from the add-on's reach.
    """
    if not hass.data.get(DOMAIN):
        async_unregister_services(hass)
        frontend.async_remove_panel(hass, PANEL_URL_PATH)


def _version() -> str:
    """Integration version (manifest), for cache-busting the panel/card URLs."""
    try:
        manifest = json.loads(
            (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
        )
        return str(manifest.get("version", "0"))
    except (OSError, ValueError):
        return "0"


async def _async_register_frontend(hass: HomeAssistant, version: str) -> None:
    """Serve the panel JS and the translation catalogs, add the sidebar entry.

    A **custom** panel, not an iframe: the ``epaperengine-panel`` element gets
    ``hass`` handed to it directly and talks to the WebSocket API. Served
    straight out of the integration directory — no copy into ``www/``, so HACS
    unzipping with stale timestamps cannot leave an older second copy behind.
    """
    if not hass.data.get(_STATIC_REGISTERED):
        here = Path(__file__).parent
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    PANEL_STATIC_URL, str(here / "panel" / PANEL_FILENAME), False
                ),
                # One shared catalog per language for panel *and* card, fetched
                # as ``<url>/<lang>.json?v=<version>``; the query busts the cache.
                StaticPathConfig(I18N_STATIC_URL, str(here / I18N_DIRNAME), True),
            ]
        )
        hass.data[_STATIC_REGISTERED] = True
        _LOGGER.info("Serving frontend translation catalogs at %s", I18N_STATIC_URL)

    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        return

    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        require_admin=False,
        config={
            "_panel_custom": {
                "name": PANEL_CUSTOM_NAME,
                "embed_iframe": False,
                "trust_external": False,
                "module_url": f"{PANEL_STATIC_URL}?v={version}",
            }
        },
    )
    _LOGGER.info("Registered ePaperEngine sidebar panel at /%s", PANEL_URL_PATH)


def _deploy_file(src: Path, dst: Path) -> bool:
    """Copy ``src`` to ``dst`` when the *content* differs.

    Content, not mtime: HACS unzips with stale timestamps, so a timestamp
    comparison silently keeps an old card in ``www/`` (ha-integration-howto).
    """
    src_bytes = src.read_bytes()
    if dst.exists() and dst.read_bytes() == src_bytes:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return True


async def _async_register_card(hass: HomeAssistant, version: str) -> None:
    """Deploy the Lovelace card to ``www/`` and register it as a module resource.

    Unlike the panel the card cannot be served from the integration directory:
    Lovelace resources are URLs the *dashboard* loads, and ``/local/`` is the
    path that works on every dashboard without the user adding anything.
    """
    if hass.data.get(_CARD_REGISTERED):
        return
    src = Path(__file__).parent / CARD_FILENAME
    dst = Path(hass.config.path("www")) / CARD_FILENAME
    copied = await hass.async_add_executor_job(_deploy_file, src, dst)
    if copied:
        _LOGGER.info("Deployed %s to www/", CARD_FILENAME)
    hass.data[_CARD_REGISTERED] = True

    url = f"{CARD_WWW_URL}?v={version}"
    # Only once Home Assistant has started: during boot the resource collection
    # is not loaded yet, the stale-version cleanup cannot run, and every version
    # bump then piles up another entry (ha-integration-howto, timing note).
    if hass.state is CoreState.running:
        await _async_register_lovelace_resource(hass, url)
    else:

        async def _on_started(_event: Event) -> None:
            await _async_register_lovelace_resource(hass, url)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)


async def _async_register_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Register (or update) the card as a Lovelace ``module`` resource.

    Stale versions of the same file are dropped **before** the "already there"
    check — the other way round an up-to-date entry short-circuits the cleanup
    and the old ones linger, which is how resource lists grow one line per
    release. No-op in YAML-mode Lovelace, which has no resource store.
    """
    base = CARD_WWW_URL
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None) if lovelace else None
        if not resources or not hasattr(resources, "async_create_item"):
            _LOGGER.warning(
                "Lovelace resources unavailable (YAML mode?) — add %s by hand", url
            )
            return
        if hasattr(resources, "async_load") and not getattr(resources, "loaded", True):
            await resources.async_load()
        # ``async_items()`` and not ``async_get_info()``: the latter varies by HA
        # version and has been observed to return nothing here, which made the
        # duplicate check useless.
        items = list(resources.async_items())

        def _url(item: object) -> str:
            return item.get("url", "") if isinstance(item, dict) else getattr(item, "url", "")

        def _id(item: object) -> object:
            return item.get("id") if isinstance(item, dict) else getattr(item, "id", None)

        for item in items:
            if _url(item).split("?")[0] == base and _url(item) != url:
                try:
                    await resources.async_delete_item(_id(item))
                    _LOGGER.info("Removed stale Lovelace resource %s", _url(item))
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning(
                        "Could not remove stale resource %s: %s", _url(item), exc
                    )
        if any(_url(item) == url for item in items):
            return
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered Lovelace resource %s", url)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Lovelace resource registration failed for %s: %s", url, exc)
