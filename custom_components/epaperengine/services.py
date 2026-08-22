"""Services for ePaperEngine (FSD §3.1).

Five. Two of them are the whole conversation between the integration and the
add-on, two are for automations — the front-ends use the WebSocket API instead
(``websocket_api.py``), because the browser is already connected there.

``get_render_data``
    the add-on pulls one document per run (FSD §6.2 step 1). ``SupportsResponse
    .ONLY`` — this is a question, not a command, and the payload would blow the
    16 KB entity-attribute limit once recipes are in it.

``report_run``
    the add-on reports the outcome (FSD §6.2 step 10). The specification says
    the result lands in ``sensor.epaperengine_status`` but not *how* it gets
    there; a service is the obvious carrier, because the add-on already talks to
    the HA API with its ``SUPERVISOR_TOKEN`` and needs no second channel.

``render``
    ask for a run from an automation. ``force`` pushes even an unchanged image.

``set_view``
    pin a view by hand, with the timeout of FSD §5. Calling it without a view
    hands control back to the automatic resolution.

``sync_recipes``
    pull the collection from Paprika now (FSD §9.2). ``SupportsResponse
    .OPTIONAL`` — an automation usually just wants the sync, but "how many came
    back" is worth having without a second call to a sensor.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    RUN_RESULTS,
    SERVICE_GET_RENDER_DATA,
    SERVICE_RENDER,
    SERVICE_REPORT_RUN,
    SERVICE_SET_VIEW,
    SERVICE_SYNC_RECIPES,
    VIEWS,
)
from .coordinator import EPaperEngineCoordinator

_LOGGER = logging.getLogger(__name__)

RENDER_SCHEMA = vol.Schema({vol.Optional("force", default=False): cv.boolean})

# An empty ``view`` is not a missing argument but a statement: "back to
# automatic". The card's "Automatic" chip sends exactly this, and giving it its
# own service would mean two names for one decision.
SET_VIEW_SCHEMA = vol.Schema({vol.Optional("view"): vol.In(VIEWS)})

REPORT_RUN_SCHEMA = vol.Schema(
    {
        vol.Required("result"): vol.In(RUN_RESULTS),
        vol.Required("view"): vol.In(VIEWS),
        vol.Optional("error"): cv.string,
        vol.Optional("warning"): cv.string,
        vol.Optional("image_hash"): cv.string,
        vol.Optional("pushed", default=False): cv.boolean,
    }
)


def _coordinator(hass: HomeAssistant) -> EPaperEngineCoordinator:
    """The single instance — the config flow allows only one."""
    entries = hass.data.get(DOMAIN) or {}
    if not entries:
        raise ServiceValidationError("ePaperEngine is not set up")
    return next(iter(entries.values()))


def async_register_services(hass: HomeAssistant) -> None:
    """Register the services (idempotent — setup may run again on reload)."""

    async def _get_render_data(call: ServiceCall) -> ServiceResponse:
        return _coordinator(hass).render_document()

    async def _report_run(call: ServiceCall) -> None:
        data: dict[str, Any] = dict(call.data)
        await _coordinator(hass).async_report_run(
            result=data["result"],
            view=data["view"],
            error=data.get("error"),
            warning=data.get("warning"),
            image_hash=data.get("image_hash"),
            pushed=bool(data.get("pushed")),
        )

    async def _render(call: ServiceCall) -> None:
        _coordinator(hass).async_request_render(
            "service", force=bool(call.data.get("force"))
        )

    async def _set_view(call: ServiceCall) -> None:
        await _coordinator(hass).async_set_view(call.data.get("view"))

    async def _sync_recipes(call: ServiceCall) -> ServiceResponse:
        return await _coordinator(hass).async_sync_recipes()

    if not hass.services.has_service(DOMAIN, SERVICE_GET_RENDER_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_RENDER_DATA,
            _get_render_data,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REPORT_RUN):
        hass.services.async_register(
            DOMAIN, SERVICE_REPORT_RUN, _report_run, schema=REPORT_RUN_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RENDER):
        hass.services.async_register(DOMAIN, SERVICE_RENDER, _render, schema=RENDER_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_VIEW):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_VIEW, _set_view, schema=SET_VIEW_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SYNC_RECIPES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SYNC_RECIPES,
            _sync_recipes,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.OPTIONAL,
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Drop the services once the last entry is gone."""
    for service in (
        SERVICE_GET_RENDER_DATA,
        SERVICE_REPORT_RUN,
        SERVICE_RENDER,
        SERVICE_SET_VIEW,
        SERVICE_SYNC_RECIPES,
    ):
        hass.services.async_remove(DOMAIN, service)
