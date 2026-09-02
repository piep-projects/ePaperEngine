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
    WS_CALENDAR_ANNIVERSARIES,
    WS_CALENDAR_PROBE,
    WS_CALENDAR_SYNC,
    WS_CONFIG_GET,
    WS_CONFIG_SET,
    WS_DISPLAY_TEST,
    WS_GUESTS_BACKGROUNDS,
    WS_GUESTS_SET,
    WS_PHOTOS_LIST,
    WS_RECIPES_GET,
    WS_RECIPES_SEARCH,
    WS_RECIPES_SELECT,
    WS_RECIPES_SYNC,
    WS_RENDER,
    WS_SET_VIEW,
    WS_STATUS,
)
from .coordinator import EPaperEngineCoordinator
from .recipes import SEARCH_LIMIT


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
        ws_recipes_select,
        ws_guests_set,
        ws_guests_backgrounds,
        ws_calendar_probe,
        ws_calendar_sync,
        ws_calendar_anniversaries,
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
    hits = coordinator.recipes.search(msg["query"], msg.get("limit") or SEARCH_LIMIT)
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


@websocket_api.websocket_command({vol.Required("type"): WS_RECIPES_SYNC})
@websocket_api.async_response
async def ws_recipes_sync(hass, connection, msg) -> None:
    """Sync against Paprika right now (FSD §9.2).

    **Open to the household** [Festlegung 2026-08-31, Wolfgang]. It was
    administrator-only, and the reason given was that it leaves the house and
    hits an endpoint documented to ban by IP — but "are the new recipes here
    yet?" is a question somebody asks while cooking (C11), and the answer to a
    rate limit is a rate limit. ``RECIPE_SYNC_MIN_GAP_S`` is what replaced the
    lock; a press inside the gap comes back ``skipped``.

    It changes no configuration: the account is typed under Settings and stays
    administrator business. It answers the *status* even when the sync failed —
    "no credentials", "login refused" and "217 recipes" are all answers to the
    same question, and the panel shows each of them plainly.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], await coordinator.async_sync_recipes())


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_RECIPES_SELECT,
        vol.Required("selection"): [cv.string],
        vol.Optional("servings"): {cv.string: vol.Any(None, vol.Coerce(float))},
    }
)
@websocket_api.async_response
async def ws_recipes_select(hass, connection, msg) -> None:
    """Put tonight's recipes on the wall — household business, not admin's.

    The narrow command the earlier note asked for and did not invent. Picking
    is stored *as configuration*, and that alone made it administrator-only;
    the decision itself is the same kind as ``set_view`` and ``guests/set``.

    Narrow is the whole safety argument: the schema admits a list of uids and a
    map of portion counts, and ``async_set_recipe_selection`` builds the patch
    from those two fields. The Paprika account lives in the same store section
    and cannot be reached through here — which a relaxed ``config/set`` would
    not have been able to promise.

    The answer has the shape of ``config/set`` because the panel treats it the
    same way, and the configuration is redacted for whoever is asking: this
    command is open, reading the account is not.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    try:
        config = await coordinator.async_set_recipe_selection(
            list(msg["selection"]), msg.get("servings")
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_config", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "config": _visible_config(config, connection.user.is_admin),
            "status": coordinator.status_document(),
        },
    )


# --- guests (FSD §8.4) --------------------------------------------------------


@websocket_api.websocket_command(
    {vol.Required("type"): WS_GUESTS_SET, vol.Required("active"): cv.boolean}
)
@websocket_api.async_response
async def ws_guests_set(hass, connection, msg) -> None:
    """Switch guest mode on or off (FSD §5, §8.4).

    **Not administrator-only**, and deliberately so: it is the same kind of act
    as ``set_view`` — somebody in the house decides what the wall shows right
    now — and pinning the guest view already switches the mode on for anybody
    who can press a chip. Making the *off* switch the only administrator half of
    that pair would leave the household able to start a visit and unable to end
    it. What stays administrator-only is the greeting itself: the name, the text
    and the picture are configuration and go through ``config/set``.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    await coordinator.async_set_guests(msg["active"])
    connection.send_result(msg["id"], coordinator.status_document())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): WS_GUESTS_BACKGROUNDS})
@websocket_api.async_response
async def ws_guests_backgrounds(hass, connection, msg) -> None:
    """The guest backgrounds, refreshed and listed (FSD §8.4).

    Administrator-only, unlike the photo list: this one *does work* on the other
    side — it walks the folder on the NAS, hashes what is new and writes crops
    and thumbnails. That is a button worth keeping behind the same line as "Test
    connection", and picking the background is configuration anyway.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], await coordinator.async_background_list())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): WS_CALENDAR_PROBE})
@websocket_api.async_response
async def ws_calendar_probe(hass, connection, msg) -> None:
    """How many entries each configured calendar answers with — and which do not.

    Admin-only, like every other read that touches configuration rather than
    the wall: the sources are set on this page, and the answer names entities
    somebody who only picks tonight's recipe has no business enumerating.

    No ``update_entity`` here (see ``async_calendar_probe``): this fires while a
    settings page is open, and re-pulling three published ICS files on every
    repaint would be rude to the servers answering them.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], await coordinator.async_calendar_probe())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): WS_CALENDAR_SYNC})
@websocket_api.async_response
async def ws_calendar_sync(hass, connection, msg) -> None:
    """Pull the sources now, count them, and let the wall catch up.

    The counterpart to ``calendar/probe``: same answer shape, plus ``on_wall``,
    but this one *does* run ``homeassistant.update_entity`` first and asks for a
    render run afterwards. Admin-only for the same reason as
    ``guests/backgrounds`` — it does work on the other side, here on somebody
    else's calendar server.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(msg["id"], await coordinator.async_calendar_sync())


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_CALENDAR_ANNIVERSARIES,
        vol.Optional("dry_run", default=True): bool,
        vol.Optional("limit"): vol.Any(None, vol.All(int, vol.Range(min=0))),
    }
)
@websocket_api.async_response
async def ws_calendar_anniversaries(hass, connection, msg) -> None:
    """Write the year count back into the anniversary calendars [P42].

    **Open to the household** [Festlegung 2026-09-02, Wolfgang], and it is the
    one write in this project that leaves the house — so the reason matters.
    The command has no free-text argument and no choice of target: it writes,
    into the calendars an administrator configured, the number the wall is
    already showing. There is nothing a household member can express through it
    that an administrator has not already agreed to, and since 2026-09-02 the
    nightly run does the same thing unattended anyway. Locking it would have
    left a button that only one person could press to fix a wall everybody
    looks at — the shape P43 already rejected twice.

    ``dry_run`` still defaults to ``True`` on the wire as well as in the
    transport, so a caller that forgets the flag gets the harmless answer. The
    panel passes ``false`` on purpose: pressing "write back now" is the
    intention, and a preview step in front of an idempotent operation that only
    ever writes the wall's own number is a question nobody can answer better
    afterwards. ``limit`` caps how many entries are saved.
    """
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "ePaperEngine is not set up")
        return
    connection.send_result(
        msg["id"],
        await coordinator.async_write_back_anniversaries(
            dry_run=bool(msg["dry_run"]), limit=msg.get("limit")
        ),
    )
