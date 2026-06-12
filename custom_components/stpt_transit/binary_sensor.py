from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, ATTRIBUTION
from .coordinator import StptTransitConfigEntry, StptTransitCoordinator

_LOGGER = logging.getLogger(__name__)

DISRUPTIONS_UNIQUE_ID = "stpt_disruptions"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StptTransitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    ent_reg = er.async_get(hass)
    if ent_reg.async_get_entity_id("binary_sensor", DOMAIN, DISRUPTIONS_UNIQUE_ID) is None:
        async_add_entities([StptAlertsBinarySensor(coordinator)], update_before_add=True)


class StptAlertsBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: StptTransitCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "stpt_disruptions"
        self._attr_name = "STPT Disruptions"
        self._attr_icon = "mdi:alert-circle"
        self._attr_attribution = ATTRIBUTION
        self._attr_should_poll = False

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        alerts = data.get("alerts", [])
        return isinstance(alerts, list) and len(alerts) > 0

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        alerts = data.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = []
        latest = alerts[0] if alerts else None
        return {
            "alert_count": len(alerts),
            "latest_title": (latest.get("title") or "") if latest else None,
            "latest_description": (latest.get("description") or "") if latest else None,
        }
