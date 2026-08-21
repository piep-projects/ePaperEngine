"""Shared entity base for ePaperEngine.

One device — the wall display — carries every entity, so the dashboard groups
them instead of scattering five unrelated sensors. ``has_entity_name`` lets the
name come from the translation catalogs, which is what makes the German labels
follow ``hass.language`` while the entity_id stays English (FSD §3.0a).
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, PANEL_TITLE, SIGNAL_STATE_UPDATED
from .coordinator import EPaperEngineCoordinator


def display_device_info(entry_id: str) -> DeviceInfo:
    """The single hub device all entities hang on."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=PANEL_TITLE,
        manufacturer="Samsung",
        model="EM32DX",
    )


class EPaperEngineEntity(Entity):
    """Base for every ePaperEngine entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: EPaperEngineCoordinator, key: str) -> None:
        self.coordinator = coordinator
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = display_device_info(coordinator.entry.entry_id)

    async def async_added_to_hass(self) -> None:
        """Refresh when the add-on reports a run."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_UPDATED.format(self.coordinator.entry.entry_id),
                self.async_write_ha_state,
            )
        )
