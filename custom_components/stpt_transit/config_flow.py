from __future__ import annotations

import json
import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, SelectSelector, SelectSelectorConfig, SelectOptionDict

from .const import (
    DOMAIN,
    CONF_STATIONS,
    CONF_STOP_ID,
    CONF_NAME,
    CONF_LINES,
    CONF_REFRESH_INTERVAL,
    DEFAULT_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_LINE_CONFIG: dict | None = None
_STATIONS_MAP: dict | None = None


def _load_line_config() -> dict:
    global _LINE_CONFIG
    if _LINE_CONFIG is not None:
        return _LINE_CONFIG
    path = os.path.join(os.path.dirname(__file__), "lines_config.json")
    try:
        with open(path) as f:
            _LINE_CONFIG = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as err:
        _LOGGER.warning("Could not load lines_config.json: %s", err)
        _LINE_CONFIG = {}
    return _LINE_CONFIG


def _load_stations_map() -> dict:
    global _STATIONS_MAP
    if _STATIONS_MAP is not None:
        return _STATIONS_MAP
    path = os.path.join(os.path.dirname(__file__), "stations_map.json")
    try:
        with open(path) as f:
            _STATIONS_MAP = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _STATIONS_MAP = {}
    return _STATIONS_MAP


def _resolve_station_name(stop_id: str, custom_name: str = "") -> str:
    if custom_name:
        return custom_name
    stations = _load_stations_map()
    info = stations.get(stop_id)
    if info and isinstance(info, list) and len(info) > 0:
        return info[0]
    return stop_id


def _get_lines_for_stop(stop_id: str) -> list[str]:
    config = _load_line_config()
    if not config:
        return []
    seen = set()
    for line_id, line_data in config.items():
        for direction in ("tur", "retur"):
            ids = line_data.get(direction, {}).get("ids", [])
            if stop_id in ids:
                seen.add(str(line_id))
                break
    return sorted(seen, key=lambda x: (len(x), x))


class StptTransitConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._selected_station: dict | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            custom = user_input.get(CONF_NAME, "") or ""
            self._selected_station = {
                CONF_STOP_ID: user_input[CONF_STOP_ID],
                CONF_NAME: await self.hass.async_add_executor_job(_resolve_station_name, user_input[CONF_STOP_ID], custom),
            }
            return await self.async_step_pick_lines()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): TextSelector(TextSelectorConfig(type="text")),
                vol.Optional(CONF_NAME, default=""): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_pick_lines(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            selected_lines = user_input.get(CONF_LINES, [])
            if isinstance(selected_lines, str):
                selected_lines = [selected_lines]
            station = dict(self._selected_station)
            if selected_lines:
                station[CONF_LINES] = selected_lines
            self._selected_station = None
            return self.async_create_entry(
                title=f"STPT {station[CONF_STOP_ID]}",
                data={CONF_STATIONS: [station]},
            )

        stop_id = self._selected_station[CONF_STOP_ID]
        name = self._selected_station.get(CONF_NAME, "") or stop_id
        available = await self.hass.async_add_executor_job(_get_lines_for_stop, stop_id)
        if not available:
            station = dict(self._selected_station)
            self._selected_station = None
            return self.async_create_entry(
                title=f"STPT {station[CONF_STOP_ID]}",
                data={CONF_STATIONS: [station]},
            )

        options = [SelectOptionDict(value=line, label=f"Line {line}") for line in available]
        return self.async_show_form(
            step_id="pick_lines",
            data_schema=vol.Schema({
                vol.Optional(CONF_LINES, default=[]): SelectSelector(SelectSelectorConfig(options=options, multiple=True)),
            }),
            description_placeholders={"station_name": name},
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StptTransitOptionsFlow(config_entry)


class StptTransitOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._add_selected: dict | None = None

    def _options_data(self, extra_data: dict | None = None) -> dict:
        data = dict(self._config_entry.options)
        if extra_data:
            data.update(extra_data)
        return data

    def _current_stations(self) -> list[dict]:
        opts = self._config_entry.options.get(CONF_STATIONS)
        if opts is not None:
            return list(opts)
        return list(self._config_entry.data.get(CONF_STATIONS, []))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                return await self.async_step_add()
            if action == "remove":
                return await self.async_step_remove_station()
            if action == "settings":
                return await self.async_step_settings()
            return self.async_create_entry(title="", data=self._options_data())

        current = self._current_stations()
        actions = {
            "add": "Add a station",
            "remove": "Remove a station",
            "settings": "Configure global settings",
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="add"): vol.In(actions),
            }),
            description_placeholders={"station_count": str(len(current))},
        )

    async def async_step_add(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            custom = user_input.get(CONF_NAME, "") or ""
            self._add_selected = {
                CONF_STOP_ID: user_input[CONF_STOP_ID],
                CONF_NAME: await self.hass.async_add_executor_job(_resolve_station_name, user_input[CONF_STOP_ID], custom),
            }
            return await self.async_step_add_lines()

        return self.async_show_form(
            step_id="add",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): TextSelector(TextSelectorConfig(type="text")),
                vol.Optional(CONF_NAME, default=""): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_add_lines(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            selected_lines = user_input.get(CONF_LINES, [])
            if isinstance(selected_lines, str):
                selected_lines = [selected_lines]
            station = dict(self._add_selected)
            if selected_lines:
                station[CONF_LINES] = selected_lines
            stations = self._current_stations()
            stations.append(station)
            self._add_selected = None
            return self.async_create_entry(title="", data=self._options_data({CONF_STATIONS: stations}))

        stop_id = self._add_selected[CONF_STOP_ID]
        name = self._add_selected.get(CONF_NAME, "") or stop_id
        available = await self.hass.async_add_executor_job(_get_lines_for_stop, stop_id)
        if not available:
            stations = self._current_stations()
            stations.append(dict(self._add_selected))
            self._add_selected = None
            return self.async_create_entry(title="", data=self._options_data({CONF_STATIONS: stations}))

        options = [SelectOptionDict(value=line, label=f"Line {line}") for line in available]
        return self.async_show_form(
            step_id="add_lines",
            data_schema=vol.Schema({
                vol.Optional(CONF_LINES, default=[]): SelectSelector(SelectSelectorConfig(options=options, multiple=True)),
            }),
            description_placeholders={"station_name": name},
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=self._options_data(user_input))

        current = self._config_entry.options.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Required(CONF_REFRESH_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=120)
                ),
            }),
        )

    async def async_step_remove_station(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = self._current_stations()
        if user_input is not None:
            to_remove = user_input.get("stop_id", "")
            stations = [s for s in current if s.get(CONF_STOP_ID) != to_remove]
            return self.async_create_entry(title="", data=self._options_data({CONF_STATIONS: stations}))

        options = {s.get(CONF_STOP_ID): f"{s.get(CONF_STOP_ID)} - {s.get(CONF_NAME, '')}" for s in current}
        return self.async_show_form(
            step_id="remove_station",
            data_schema=vol.Schema({
                vol.Required("stop_id"): vol.In(options),
            }),
        )
