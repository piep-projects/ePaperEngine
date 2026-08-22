"""Sensors for ePaperEngine (FSD §3.1).

Four of them: which view *should* be on the wall and why, what the last run did,
when the wall last actually changed, and when the recipe cache last spoke to
Paprika.
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
from homeassistant.util import dt as dt_util

from .const import DOMAIN, RUN_RESULTS, VIEWS
from .coordinator import EPaperEngineCoordinator
from .entity import EPaperEngineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the ePaperEngine sensors."""
    coordinator: EPaperEngineCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TargetViewSensor(coordinator),
            StatusSensor(coordinator),
            LastPushSensor(coordinator),
            RecipeCacheSensor(coordinator),
        ]
    )


class TargetViewSensor(EPaperEngineEntity, SensorEntity):
    """Which view the priority resolution picked, and why (FSD §5).

    The ``source`` attribute is not decoration: without it the resolution is a
    black box to whoever is looking at the wall wondering why the recipes are
    still up. It is the same reason the Lovelace card leads with the "because"
    line.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(VIEWS)

    def __init__(self, coordinator: EPaperEngineCoordinator) -> None:
        super().__init__(coordinator, "target_view")

    @property
    def native_value(self) -> str:
        return self.coordinator.target.view

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        target = self.coordinator.target
        next_change = self.coordinator.next_change_at()
        return {
            "source": target.source,
            **target.detail,
            "next_change": next_change.isoformat() if next_change else None,
        }


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
            # A run the add-on never started reports nothing at all, so the
            # reason it could not be reached has to travel separately — otherwise
            # an unreachable renderer looks like a system standing still for no
            # stated reason.
            "addon_error": self.coordinator.addon_error,
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


class RecipeCacheSensor(EPaperEngineEntity, SensorEntity):
    """When the recipe cache last synced with Paprika (FSD §9.2).

    A timestamp rather than the number of recipes, because the question this
    sensor exists for is *"are the new recipes here yet?"* — C11 asked for it in
    those words, and a count of 214 answers it only if you happen to remember it
    was 213 yesterday. The count rides along as an attribute.

    ``None`` until the first sync: an installation without a Paprika account is
    not an error, it is a household that does not use the recipe view.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EPaperEngineCoordinator) -> None:
        super().__init__(coordinator, "recipe_cache")

    @property
    def native_value(self) -> datetime | None:
        synced = self.coordinator.recipes.synced_at
        return dt_util.parse_datetime(str(synced)) if synced else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.recipes.status()
        return {
            "count": status["count"],
            # Recipes whose detail did not fit into the last sync's request
            # budget (FSD §9.2 — the endpoint bans by IP). They arrive with the
            # next one; a number standing still here is worth looking at.
            "pending": status["pending"],
            # Recipes in Paprika's trash. They answer the sync API like any
            # other recipe, so this is the number that explains why the count
            # is smaller than the collection looks in the app.
            "trashed": status["trashed"],
            "selected": len(self.coordinator.config["recipes"].get("selection") or []),
            "error": status["error"],
        }
