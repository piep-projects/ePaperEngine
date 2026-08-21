"""Sensors for ePaperEngine (FSD §3.1).

Phase 3 ships the two that make a render run observable from outside:
what the last run did, and when the wall last actually changed. The target
view, recipe cache and display reachability follow in phase 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, RUN_RESULTS
from .coordinator import EPaperEngineCoordinator
from .entity import EPaperEngineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the ePaperEngine sensors."""
    coordinator: EPaperEngineCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StatusSensor(coordinator), LastPushSensor(coordinator)])


class StatusSensor(EPaperEngineEntity, SensorEntity):
    """Outcome of the last render run.

    An ENUM rather than free text: these five values drive automations and the
    card's error strip, and HA translates them in more-info, history and the
    logbook. ``options`` is mandatory for ENUM sensors — a value outside the
    list would be an error, which is exactly why the list lives in ``const.py``
    as the single source and the guard test checks it against the catalogs.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(RUN_RESULTS)

    def __init__(self, coordinator: EPaperEngineCoordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str:
        return self.coordinator.last_result

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detail of the last run — small by construction.

        Entity attributes are capped at 16 KB, so nothing that grows (recipe
        text, image data) may ever land here; those go through services with
        ``SupportsResponse`` instead.
        """
        run = self.coordinator.last_run or {}
        return {
            "view": run.get("view"),
            "at": run.get("at"),
            "error": run.get("error"),
            "warning": run.get("warning"),
        }


class LastPushSensor(EPaperEngineEntity, SensorEntity):
    """When the wall last actually changed.

    Deliberately *not* "when did a run last happen": a run that finds an
    unchanged image pushes nothing (FSD §11), and the interesting question for
    the card is when the panel last redrew.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EPaperEngineCoordinator) -> None:
        super().__init__(coordinator, "last_push")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_push_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        push = self.coordinator.state.get("last_push") or {}
        return {"image_hash": push.get("hash")}
