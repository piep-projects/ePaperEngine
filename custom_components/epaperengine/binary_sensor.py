"""Reachability of the display (FSD §3.1).

One entity, and it means something narrow: **the panel answered an MDC command**.
Not "port 1515 is open" — that would report a display with a wrong PIN as
reachable, which is the one failure worth catching [Festlegung 2026-08-21]. The
measurement happens in the add-on (``probe.mjs``), because only it has the Node
protocol layer; the integration asks it over ``GET /display``.

It is deliberately **not** on the Lovelace card in the normal case [Festlegung
2026-08-20]: a dot that is always green carries no information. Only the fault
reports itself.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EPaperEngineCoordinator
from .entity import EPaperEngineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the ePaperEngine binary sensors."""
    coordinator: EPaperEngineCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DisplayReachableSensor(coordinator)])


class DisplayReachableSensor(EPaperEngineEntity, BinarySensorEntity):
    """Does the display answer over MDC."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: EPaperEngineCoordinator) -> None:
        super().__init__(coordinator, "display_reachable")

    @property
    def available(self) -> bool:
        """Unknown until the first probe, and while the add-on itself is mute.

        The distinction matters: "the display did not answer" is a fault of the
        display, "the add-on did not answer" is a fault one layer up, and a
        sensor that reported both as ``off`` would send somebody to the wrong
        device.
        """
        display = self.coordinator.display
        return bool(display) and display.get("addon") is not False

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.display.get("reachable"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """What the panel shows under "Set on the device" — small and fixed."""
        display = self.coordinator.display or {}
        battery = display.get("battery") or {}
        return {
            "host": display.get("host"),
            "device_name": display.get("device_name"),
            "software_version": display.get("software_version"),
            "serial_number": display.get("serial_number"),
            "power_state": display.get("power_state"),
            "battery_percent": battery.get("batteryPercent"),
            "plugged_in": battery.get("pluggedIn"),
            "checked_at": display.get("at"),
            "error": display.get("error"),
        }
