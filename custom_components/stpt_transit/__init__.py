from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_STATIONS
from .coordinator import StptTransitCoordinator, StptTransitConfigEntry, _load_stations_map, _load_line_config

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


def get_stations(entry) -> list[dict]:
    opts = entry.options.get(CONF_STATIONS)
    if opts is not None:
        return list(opts)
    return list(entry.data.get(CONF_STATIONS, []))


async def _async_register_panel(hass: HomeAssistant) -> None:
    from homeassistant.components import panel_custom
    from homeassistant.components.frontend import async_panel_exists
    from homeassistant.components.http import StaticPathConfig

    panel_url_path = f"{DOMAIN}_map"
    if async_panel_exists(hass, panel_url_path):
        return

    panel_dir = os.path.join(os.path.dirname(__file__), "frontend")
    await hass.http.async_register_static_paths([
        StaticPathConfig(f"/{DOMAIN}/panel", panel_dir, cache_headers=False)
    ])
    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=panel_url_path,
        webcomponent_name="stpt-map-panel",
        sidebar_title="STPT Live",
        sidebar_icon="mdi:bus",
        module_url=f"/{DOMAIN}/panel/stpt-map-panel.js",
        embed_iframe=False,
        require_admin=False,
    )


def _async_remove_panel(hass: HomeAssistant) -> None:
    from homeassistant.components.frontend import async_panel_exists, async_remove_panel

    panel_url_path = f"{DOMAIN}_map"
    if async_panel_exists(hass, panel_url_path):
        async_remove_panel(hass, panel_url_path)


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
    await _async_register_panel(hass)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StptTransitConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            _async_remove_panel(hass)
            hass.data.pop(DOMAIN, None)
    return unload_ok


async def async_update_entry(hass: HomeAssistant, config_entry: StptTransitConfigEntry) -> None:
    await hass.config_entries.async_reload(config_entry.entry_id)
