from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, ATTRIBUTION, CONF_LINES, CONF_STOP_ID
from .coordinator import StptTransitConfigEntry, StptTransitCoordinator
from . import get_stations

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


def _format_minutes(mins: int | None) -> str | None:
    if mins is None:
        return None
    if mins >= 60:
        return f"{mins // 60}h {mins % 60}min"
    return f"{mins}min"


GLOBAL_SENSOR_IDS = {"stpt_latest_alert", "stpt_vehicles"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StptTransitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities = []
    data = coordinator.data or {}

    _cleanup_old_entities(hass, entry)

    raw_stations = get_stations(entry)

    for station in raw_stations:
        stop_id = station["stop_id"]
        station_info = coordinator.get_station_info(stop_id)
        name = station.get("name", "") or station_info.get("name", "") or f"Station {stop_id}"

        lines = _discover_lines(coordinator, stop_id, data)

        station_lines = station.get(CONF_LINES)
        if station_lines:
            lines = {str(l).strip() for l in station_lines} & lines

        if lines:
            for line in sorted(lines):
                entities.append(StptLineSensor(coordinator, stop_id, line, name, station_info))
        else:
            _LOGGER.warning(
                "No lines discovered for station %s (%s), creating legacy sensor",
                stop_id, name,
            )
            entities.append(StptArrivalsSensor(coordinator, stop_id, name, station_info))

    ent_reg = er.async_get(hass)
    for uid in GLOBAL_SENSOR_IDS:
        if ent_reg.async_get_entity_id(Platform.SENSOR, DOMAIN, uid) is None:
            if uid == "stpt_latest_alert":
                entities.append(StptLatestAlertSensor(coordinator))
            elif uid == "stpt_vehicles":
                entities.append(StptVehiclesSensor(coordinator))

    async_add_entities(entities, update_before_add=True)


GLOBAL_BINARY_SENSOR_IDS = {"stpt_disruptions"}


def _cleanup_old_entities(hass: HomeAssistant, entry: StptTransitConfigEntry) -> None:
    ent_reg = er.async_get(hass)
    expected = set(GLOBAL_SENSOR_IDS) | GLOBAL_BINARY_SENSOR_IDS
    for station in get_stations(entry):
        stop_id = station[CONF_STOP_ID]
        expected.add(f"{entry.entry_id}_{stop_id}")
        for sline in station.get(CONF_LINES, []):
            expected.add(f"{entry.entry_id}_{stop_id}_{str(sline).strip()}")

    for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        if entity_entry.unique_id not in expected:
            _LOGGER.debug("Removing orphaned entity %s (unique_id: %s)", entity_entry.entity_id, entity_entry.unique_id)
            ent_reg.async_remove(entity_entry.entity_id)


def _discover_lines(
    coordinator: StptTransitCoordinator, stop_id: str, data: dict
) -> set[str]:
    lines = set()

    stop_data = data.get(stop_id, {})
    for arrival in stop_data.get("arrivals", []):
        line = arrival.get("line", "")
        if line:
            lines.add(str(line).strip())

    for line_info in coordinator.get_lines_for_stop(stop_id):
        line = line_info.get("line", "")
        if line:
            lines.add(str(line).strip())

    return lines


class StptLineSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StptTransitCoordinator,
        stop_id: str,
        line: str,
        station_name: str,
        station_info: dict,
    ) -> None:
        super().__init__(coordinator)
        self._stop_id = stop_id
        self._line = line
        self._station_name = station_name
        self._station_info = station_info
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{stop_id}_{line}"
        self._attr_name = line
        self._attr_icon = "mdi:bus"
        self._attr_attribution = ATTRIBUTION
        self._attr_extra_state_attributes = {
            "stop_id": stop_id,
            "station_name": station_name,
            "line": line,
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
        all_arrivals = stop_data.get("arrivals", [])
        source = stop_data.get("source", "live")

        line_arrivals = [a for a in all_arrivals if str(a.get("line", "")).strip() == self._line]

        self._attr_extra_state_attributes = {
            "stop_id": self._stop_id,
            "station_name": self._station_name,
            "line": self._line,
            "latitude": self._station_info.get("latitude", 0),
            "longitude": self._station_info.get("longitude", 0),
            "source": source,
            "arrivals": line_arrivals,
            "arrival_count": len(line_arrivals),
            "error": stop_data.get("error"),
        }

        if line_arrivals:
            next_arrival = line_arrivals[0]
            mins = next_arrival.get("minutes")
            self._attr_native_value = _format_minutes(mins) if isinstance(mins, int) else (str(mins) if mins else None)
            self._attr_native_unit_of_measurement = None
            self._attr_icon = {
                "tram": "mdi:tram",
                "tv": "mdi:tram",
                "trolley": "mdi:trolley",
                "bus": "mdi:bus",
                "vaporetto": "mdi:ferry",
            }.get(next_arrival.get("type", ""), "mdi:bus")
            self._attr_extra_state_attributes["destination"] = next_arrival.get("destination", "")
            self._attr_extra_state_attributes["next_arrival_time"] = next_arrival.get("arrival_time", "")
            self._attr_extra_state_attributes["vehicle_type"] = next_arrival.get("type", "")
            self._attr_extra_state_attributes["minutes_raw"] = mins if isinstance(mins, int) else None
        else:
            self._attr_native_value = None
            self._attr_native_unit_of_measurement = None
            self._attr_icon = "mdi:bus-alert"
        self.async_write_ha_state()


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
            self._attr_native_value = _format_minutes(mins) if isinstance(mins, int) else (str(mins) if mins else None)
            self._attr_native_unit_of_measurement = None
            self._attr_icon = {
                "tram": "mdi:tram",
                "tv": "mdi:tram",
                "trolley": "mdi:trolley",
                "bus": "mdi:bus",
                "vaporetto": "mdi:ferry",
            }.get(next_bus.get("type", ""), "mdi:bus")
            self._attr_extra_state_attributes["next_line"] = next_bus.get("line", "")
            self._attr_extra_state_attributes["next_destination"] = next_bus.get("destination", "")
            self._attr_extra_state_attributes["next_arrival_time"] = next_bus.get("arrival_time", "")
            self._attr_extra_state_attributes["next_type"] = next_bus.get("type", "")
            self._attr_extra_state_attributes["minutes_raw"] = mins if isinstance(mins, int) else None
        else:
            self._attr_native_value = None
            self._attr_native_unit_of_measurement = None
            self._attr_icon = "mdi:bus-alert"
        self.async_write_ha_state()


class StptLatestAlertSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: StptTransitCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "stpt_latest_alert"
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


class StptVehiclesSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: StptTransitCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "stpt_vehicles"
        self._attr_name = "STPT Vehicles"
        self._attr_icon = "mdi:bus-multiple"
        self._attr_attribution = ATTRIBUTION
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        vehicles_data = data.get("vehicles", {})
        if not isinstance(vehicles_data, dict):
            vehicles_data = {}

        total = vehicles_data.get("total", 0)
        by_line = vehicles_data.get("by_line", {})
        vehicles = vehicles_data.get("vehicles", [])

        if isinstance(by_line, dict):
            by_line_dict = {str(k): v for k, v in by_line.items()}
        elif isinstance(by_line, list):
            by_line_dict = {}
            for entry in by_line:
                if isinstance(entry, dict):
                    line = str(entry.get("line", ""))
                    count = entry.get("count", 0)
                    if line:
                        by_line_dict[line] = count
        else:
            by_line_dict = {}

        self._attr_native_value = total
        self._attr_extra_state_attributes = {
            "total_vehicles": total,
            "by_line": by_line_dict,
            "vehicle_count": len(vehicles),
        }
        self.async_write_ha_state()
