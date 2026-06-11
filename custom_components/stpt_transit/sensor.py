from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ATTRIBUTION
from .coordinator import StptTransitConfigEntry, StptTransitCoordinator
from . import get_stations

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StptTransitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for station in get_stations(entry):
        stop_id = station["stop_id"]
        station_info = coordinator.get_station_info(stop_id)
        name = station.get("name", "") or station_info.get("name", "") or f"Station {stop_id}"
        entities.append(StptArrivalsSensor(coordinator, stop_id, name, station_info))
    entities.append(StptLatestAlertSensor(coordinator))
    async_add_entities(entities, update_before_add=True)


class StptArrivalsSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StptTransitCoordinator,
        stop_id: str,
        name: str,
        station_info: dict,
    ) -> None:
        super().__init__(coordinator)
        self._stop_id = stop_id
        self._station_name = name
        self._station_info = station_info
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{stop_id}"
        self._attr_name = name
        self._attr_icon = "mdi:bus"
        self._attr_attribution = ATTRIBUTION
        self._attr_extra_state_attributes = {
            "stop_id": stop_id,
            "station_name": name,
            "latitude": station_info.get("latitude", 0),
            "longitude": station_info.get("longitude", 0),
            "source": None,
            "arrivals": [],
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._stop_id)},
            "name": self._station_name,
            "manufacturer": "STPT",
            "model": "Bus Station",
            "entry_type": None,
            "sw_version": "1.0",
            "configuration_url": f"https://live.stpt.ro/?stopid={self._stop_id}",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        stop_data = data.get(self._stop_id, {})
        arrivals = stop_data.get("arrivals", [])
        source = stop_data.get("source", "live")

        self._attr_extra_state_attributes = {
            "stop_id": self._stop_id,
            "station_name": self._station_name,
            "latitude": self._station_info.get("latitude", 0),
            "longitude": self._station_info.get("longitude", 0),
            "source": source,
            "arrivals": arrivals,
            "error": stop_data.get("error"),
        }

        if arrivals:
            next_bus = arrivals[0]
            mins = next_bus.get("minutes")
            if isinstance(mins, int):
                self._attr_native_value = mins
                self._attr_native_unit_of_measurement = "min"
            else:
                self._attr_native_value = mins if mins else 0
                self._attr_native_unit_of_measurement = "min"
            self._attr_icon = {
                "tram": "mdi:tram",
                "tv": "mdi:tram",
                "trolley": "mdi:trolley",
                "bus": "mdi:bus",
            }.get(next_bus.get("type", ""), "mdi:bus")
            self._attr_extra_state_attributes["next_line"] = next_bus.get("line", "")
            self._attr_extra_state_attributes["next_destination"] = next_bus.get("destination", "")
            self._attr_extra_state_attributes["next_arrival_time"] = next_bus.get("arrival_time", "")
            self._attr_extra_state_attributes["next_type"] = next_bus.get("type", "")
        else:
            self._attr_native_value = None
            self._attr_native_unit_of_measurement = None
            self._attr_icon = "mdi:bus-alert"
        self.async_write_ha_state()


class StptLatestAlertSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: StptTransitCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_latest_alert"
        self._attr_name = "STPT Latest Alert"
        self._attr_icon = "mdi:alert"
        self._attr_attribution = ATTRIBUTION
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        alerts = data.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = []
        latest = alerts[0] if alerts else None
        if latest:
            self._attr_native_value = latest.get("title", "")
            self._attr_extra_state_attributes = {
                "description": latest.get("description", ""),
                "cause": latest.get("cause", ""),
                "effect": latest.get("effect", ""),
            }
        else:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
        self.async_write_ha_state()
