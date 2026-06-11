from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import StptTransitCoordinator, StptTransitConfigEntry, _load_stations_map, _load_line_config

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: StptTransitConfigEntry) -> bool:
    try:
        stations_map = await hass.async_add_executor_job(_load_stations_map)
        line_config = await hass.async_add_executor_job(_load_line_config)
    except Exception as err:
        _LOGGER.error("Failed to load station data: %s", err)
        return False

    coordinator = StptTransitCoordinator(hass, entry, stations_map, line_config)
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        _LOGGER.warning("Initial coordinator refresh failed, continuing setup")

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception as err:
        _LOGGER.error("Failed to set up platforms: %s", err)
        return False
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StptTransitConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unload_ok


async def async_update_entry(hass: HomeAssistant, config_entry: StptTransitConfigEntry) -> None:
    await hass.config_entries.async_reload(config_entry.entry_id)
