"""Config flow — single instance (FSD §3.1).

No user input: display, views, schedules, calendars, recipes, photos and guests
are all configured afterwards in the panel (FSD §4). The flow exists only so the
integration can be added from the UI and gets a config entry to hang on.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, PANEL_TITLE


class EPaperEngineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ePaperEngine."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title=PANEL_TITLE, data={})
        return self.async_show_form(step_id="user")
