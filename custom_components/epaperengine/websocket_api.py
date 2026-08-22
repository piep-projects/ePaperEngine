"""WebSocket API — the only channel panel and card use (FSD §3.1).

Why not entity attributes: they are capped at 16 KB, and the photo list alone
would blow that at a few hundred pictures. Why not REST: the front-ends already
hold an authenticated WebSocket connection, and a service call with
``SupportsResponse.ONLY`` needs a query-parameter dance over REST that a browser
does not need to learn.

Writing configuration is **admin-only**. Reading is not: the card is meant for
the whole household, and the view chips are the household's control. Setting a
view is likewise open — it is what the card exists for — while changing where
the display lives, or its PIN, is not.

The **secrets are the exception to open reading**: ``config/get`` hands the MDC
PIN and the Paprika login to administrators and a plain "is one set" to
everybody else (``_visible_config``). Without that, every logged-in member of
the household could read a cloud account password out of a panel meant for
picking tonight's recipe.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    VIEWS,
    WS_CONFIG_GET,
    WS_CONFIG_SET,
    WS_DISPLAY_TEST,
    WS_PHOTOS_LIST,
    WS_RECIPES_GET,
    WS_RECIPES_SEARCH,
    WS_RECIPES_SYNC,
    WS_RENDER,
    WS_SET_VIEW,
    WS_STATUS,
)
from .coordinator import EPaperEngineCoordinator


def _coordinator(hass: HomeAssistant) -> EPaperEngineCoordinator | None:
    """The single instance — the config flow allows only one."""
    entries: dict[str, EPaperEngineCoordinator] = hass.data.get(DOMAIN) or {}
    return next(iter(entries.values()), None)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register every ePaperEngine WebSocket command (idempotent)."""
    for handler in (
        ws_config_get,
        ws_config_set,
        ws_status,
        ws_render,
        ws_set_view,
        ws_photos_list,
        ws_display_test,
        ws_recipes_search,
        ws_recipes_get,
        ws_recipes_sync,
    ):
        websocket_api.async_register_command(hass, handler)


@websocket_api.websocket_command({vol.Required("type"): WS_CONFIG_GET})
@callback
def ws_config_get(hass, connection, msg) -> None:
    """The whole configuration document plus the current status.

    Both in one answer: every panel page needs the configuration, and every
    panel page shows the header with the current state. Two commands would mean
    two round trips for one screen.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(
        msg["id"],
        {
            "config": _visible_config(coordinator.config, connection.user.is_admin),
            "status": coordinator.status_document(),
        },
    )


def _visible_config(config: dict[str, Any], is_admin: bool) -> dict[str, Any]:
    """The configuration document as this connection may see it.

    Reading is open to the whole household on purpose — the card is for
    everybody and it needs the priority list and the view names. The **secrets**
    are not part of that: FSD §4 keeps the MDC PIN and the Paprika login out of
    plain YAML precisely so they are not lying around, and answering them to
    every logged-in user would put them right back. Writing has been
    administrator-only since phase 4; this is the same line drawn for reading.

    Replaced by a boolean rather than removed: the panel has to tell "no account
    configured" from "an account you may not read", and an empty password field
    that silently means both is how a saved account gets wiped by accident.
    """
    if is_admin:
        return config
    display = {**(config.get("display") or {})}
    recipes = {**(config.get("recipes") or {})}
    display["mdc_pin"] = bool(display.get("mdc_pin"))
    login = recipes.get("paprika_login") or {}
    recipes["paprika_login"] = (
        {"username": login.get("username"), "password": bool(login.get("password"))}
        if login
        else None
    )
    return {**config, "display": display, "recipes": recipes}


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): WS_CONFIG_SET, vol.Required("config"): dict}
)
@websocket_api.async_response
async def ws_config_set(hass, connection, msg) -> None:
    """Merge a patch into the configuration (FSD §4).

    **The panel is the only writer of configuration** — the add-on never writes
    any. Admin-only: this is where the display's address and its PIN live.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    try:
        config = await coordinator.async_set_config(msg["config"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_config", str(err))
        return
    connection.send_result(
        msg["id"], {"config": config, "status": coordinator.status_document()}
    )


@websocket_api.websocket_command({vol.Required("type"): WS_STATUS})
@callback
def ws_status(hass, connection, msg) -> None:
    """What hangs on the wall, since when, why, and what happens next."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], coordinator.status_document())


@websocket_api.websocket_command(
    {vol.Required("type"): WS_RENDER, vol.Optional("force", default=False): bool}
)
@callback
def ws_render(hass, connection, msg) -> None:
    """Trigger a render run; ``force`` is the panel's "Push now".

    Returns as soon as the request is queued — a run takes ~10 s and reports its
    outcome through ``report_run``, which the front-ends see through the status
    sensor anyway.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    coordinator.async_request_render("panel", force=bool(msg["force"]))
    connection.send_result(msg["id"], {"queued": True, "force": bool(msg["force"])})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SET_VIEW,
        # ``None`` hands control back to the automatic resolution — that is what
        # the "Automatic" chip sends, and it needs no separate command.
        vol.Required("view"): vol.Any(None, vol.In(VIEWS)),
    }
)
@websocket_api.async_response
async def ws_set_view(hass, connection, msg) -> None:
    """Pin a view by hand, or hand control back (FSD §5)."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    await coordinator.async_set_view(msg["view"])
    connection.send_result(msg["id"], coordinator.status_document())


@websocket_api.websocket_command({vol.Required("type"): WS_PHOTOS_LIST})
@websocket_api.async_response
async def ws_photos_list(hass, connection, msg) -> None:
    """The cached photos with their thumbnail paths (FSD §8.3).

    Paths are unsigned; the panel signs them through ``auth/sign_path`` before
    it sets ``src`` (see ``mediapath.py`` for why, and for the measurement).
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], await coordinator.async_photo_list())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): WS_DISPLAY_TEST})
@websocket_api.async_response
async def ws_display_test(hass, connection, msg) -> None:
    """Probe the display over MDC, right now, bypassing every cache.

    The panel's "Test connection". Admin-only, because the answer carries the
    panel's serial number and because it is a button that opens a TLS session to
    a device on the network.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    result: dict[str, Any] = await coordinator.async_refresh_display(fresh=True)
    connection.send_result(msg["id"], result)


# --- recipes (FSD §3.1, §9) ---------------------------------------------------
# Three commands rather than entity attributes: a collection of a few hundred
# recipes blows the 16 KB attribute ceiling long before it is interesting, and
# the search has to answer per keystroke.


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_RECIPES_SEARCH,
        vol.Optional("query", default=""): cv.string,
        vol.Optional("limit"): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
    }
)
@callback
def ws_recipes_search(hass, connection, msg) -> None:
    """Full-text search in the cache (FSD §9.3).

    Local, in-process, no network: the whole point of C11 was that the cache
    lives where the search lives. Not admin-only — picking what to cook is
    household business, and ``set_view`` is open for the same reason.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    limit = msg.get("limit")
    hits = (
        coordinator.recipes.search(msg["query"], limit)
        if limit
        else coordinator.recipes.search(msg["query"])
    )
    connection.send_result(
        msg["id"],
        {
            "hits": hits,
            "total": coordinator.recipes.count,
            "cache": coordinator.recipes.status(),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_RECIPES_GET,
        vol.Optional("uid"): cv.string,
        vol.Optional("uids"): [cv.string],
    }
)
@callback
def ws_recipes_get(hass, connection, msg) -> None:
    """One recipe in full — or the three that are on the wall.

    FSD §3.1 writes this as "ein Rezept vollständig"; it takes a **list** as
    well, because the panel's selection page needs all three at once and three
    round trips for one screen is the thing the status document was designed to
    avoid. A single ``uid`` still works and answers the same shape.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    uids = list(msg.get("uids") or ([msg["uid"]] if msg.get("uid") else []))
    connection.send_result(msg["id"], {"recipes": coordinator.recipes.get(uids)})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): WS_RECIPES_SYNC})
@websocket_api.async_response
async def ws_recipes_sync(hass, connection, msg) -> None:
    """Sync against Paprika right now (FSD §9.2).

    Administrator-only, unlike the search: this one leaves the house and hits an
    endpoint that is documented to ban by IP. It answers the *status* even when
    the sync failed — "no credentials", "login refused" and "217 recipes" are
    all answers to the same question, and the panel shows each of them plainly.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], await coordinator.async_sync_recipes())
