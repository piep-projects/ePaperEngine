"""Services for ePaperEngine (FSD §3.1).

Two of them in phase 3, and they are the whole conversation between the
integration and the add-on:

``get_render_data``
    the add-on pulls one document per run (FSD §6.2 step 1). ``SupportsResponse
    .ONLY`` — this is a question, not a command, and the payload would blow the
    16 KB entity-attribute limit once recipes are in it.

``report_run``
    the add-on reports the outcome (FSD §6.2 step 10). The specification says
    the result lands in ``sensor.epaperengine_status`` but not *how* it gets
    there; a service is the obvious carrier, because the add-on already talks to
    the HA API with its ``SUPERVISOR_TOKEN`` and needs no second channel.
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
    SERVICE_REPORT_RUN,
    VIEWS,
)
from .coordinator import EPaperEngineCoordinator

_LOGGER = logging.getLogger(__name__)

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


def async_unregister_services(hass: HomeAssistant) -> None:
    """Drop the services once the last entry is gone."""
    for service in (SERVICE_GET_RENDER_DATA, SERVICE_REPORT_RUN):
        hass.services.async_remove(DOMAIN, service)
