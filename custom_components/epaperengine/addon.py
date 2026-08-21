"""The integration's side of the conversation with the add-on (FSD §3.2).

Three calls, all over plain HTTP on the configured ``display.renderer_url``:

``POST /render``
    ask for a run. Answers ``202`` at once — the run itself takes ~10 s and
    reports back through the ``report_run`` service, so nothing waits here.
    ``?force`` is the panel's "Push now": push even when the image is unchanged.
``GET /display``
    MDC reachability, the honest kind — the add-on opens TLS:1515, hands over the
    PIN and asks the panel a real question [Festlegung 2026-08-21]. A TCP connect
    from here would have called a display with a wrong PIN "reachable".
``GET /health``
    is the add-on there at all, and which version.

Why the integration calls the add-on rather than the other way round: the
add-on *pulls* its data (``get_render_data``) but has no way of knowing when
something changed. Someone has to say "now", and that someone is the side that
owns the state.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ADDON_DISPLAY_PATH,
    ADDON_HEALTH_PATH,
    ADDON_RENDER_PATH,
    DEFAULT_RENDERER_URL,
)

_LOGGER = logging.getLogger(__name__)

# A render request is a doorbell, not a job: the add-on answers 202 before it
# starts. Short on purpose — a long wait here would block the WebSocket handler
# the panel is sitting on.
RENDER_TIMEOUT_S = 15
# The probe runs a TLS handshake and an MDC round trip on the other side, and the
# add-on caps it at 20 s itself.
PROBE_TIMEOUT_S = 30


class AddonError(RuntimeError):
    """The add-on could not be reached or refused the request."""


class AddonClient:
    """Small HTTP client for the ePaperEngine add-on."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._base = DEFAULT_RENDERER_URL

    def set_base(self, renderer_url: str | None) -> None:
        """Point at the add-on. Empty configuration keeps the default address."""
        self._base = (renderer_url or DEFAULT_RENDERER_URL).rstrip("/")

    @property
    def base(self) -> str:
        return self._base

    async def _request(self, method: str, path: str, timeout: float, **params: Any) -> Any:
        session = async_get_clientsession(self._hass)
        url = f"{self._base}{path}"
        try:
            async with session.request(
                method,
                url,
                params={k: str(v) for k, v in params.items() if v},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                body = await response.text()
                if response.status >= 400:
                    raise AddonError(f"{url} answered HTTP {response.status}: {body[:200]}")
                if not body:
                    return None
                try:
                    return await response.json(content_type=None)
                except ValueError:
                    return body
        except asyncio.TimeoutError as exc:
            raise AddonError(f"{url} did not answer within {timeout:.0f}s") from exc
        except aiohttp.ClientError as exc:
            raise AddonError(f"{url} unreachable: {exc}") from exc

    async def async_render(self, reason: str, force: bool = False) -> None:
        """Ask for a render run (FSD §6.1)."""
        await self._request(
            "POST", ADDON_RENDER_PATH, RENDER_TIMEOUT_S, reason=reason, force=1 if force else ""
        )
        _LOGGER.debug("Render requested (%s%s)", reason, ", forced" if force else "")

    async def async_display(self, fresh: bool = False) -> dict[str, Any]:
        """MDC reachability plus what the panel says about itself.

        Never raises for a mute display: that is an *answer*, and the difference
        between "the display is silent" and "the add-on is silent" is exactly
        what the reachability sensor has to keep apart.
        """
        try:
            result = await self._request(
                "GET", ADDON_DISPLAY_PATH, PROBE_TIMEOUT_S, fresh=1 if fresh else ""
            )
        except AddonError as exc:
            return {"reachable": False, "error": str(exc), "addon": False}
        data = dict(result or {})
        data["addon"] = True
        return data

    async def async_health(self) -> dict[str, Any]:
        """Is the add-on there. Raises :class:`AddonError` when it is not."""
        return dict(await self._request("GET", ADDON_HEALTH_PATH, RENDER_TIMEOUT_S) or {})
