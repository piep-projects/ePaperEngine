"""Manual render trigger (FSD §3.1).

The **card** carries no refresh button [Festlegung 2026-08-20] — the timed net
runs every 15 minutes, and a control that only starts what is about to happen
anyway is noise. This entity exists for the other case: an automation that has
just changed something the integration cannot see, and wants the wall to catch
up without waiting for the net.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EPaperEngineCoordinator
from .entity import EPaperEngineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the ePaperEngine buttons."""
    coordinator: EPaperEngineCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RefreshButton(coordinator)])


class RefreshButton(EPaperEngineEntity, ButtonEntity):
    """Render now; push only if the image changed (FSD §11)."""

    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: EPaperEngineCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        """Queue a run. Debounced (~20 s) like every other trigger."""
        self.coordinator.async_request_render("button")
