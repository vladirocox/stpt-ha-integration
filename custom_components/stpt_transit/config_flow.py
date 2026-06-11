from __future__ import annotations

import json
import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, SelectSelector, SelectSelectorConfig

from .const import DOMAIN, CONF_STATIONS, CONF_STOP_ID, CONF_NAME

_LOGGER = logging.getLogger(__name__)

ADD_METHODS = {
    "search": "Search by station name",
    "manual": "Enter stop ID directly",
}

_SEARCH_INDEX: dict | None = None


def _load_search_index():
    global _SEARCH_INDEX
    if _SEARCH_INDEX is not None:
        return _SEARCH_INDEX
    path = os.path.join(os.path.dirname(__file__), "stations_map.json")
    try:
        with open(path) as f:
            _SEARCH_INDEX = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as err:
        _LOGGER.warning("Could not load stations_map.json: %s", err)
        _SEARCH_INDEX = {}
    return _SEARCH_INDEX


def _search_stations(query: str) -> list[dict]:
    index = _load_search_index()
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for stop_id, info in index.items():
        name = info[0].lower()
        if q in name or q in stop_id:
            results.append({"stop_id": stop_id, "name": info[0]})
    results.sort(key=lambda s: s["name"].lower())
    return results[:30]


class StptTransitConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._search_results: list[dict] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            method = user_input.get("method", "search")
            if method == "search":
                return await self.async_step_search()
            return await self.async_step_manual()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("method", default="search"): vol.In(ADD_METHODS),
            }),
        )

    async def async_step_search(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            query = user_input.get("query", "").strip()
            if not query:
                return self.async_show_form(
                    step_id="search",
                    data_schema=vol.Schema({
                        vol.Required("query"): TextSelector(TextSelectorConfig(type="text")),
                    }),
                    errors={"query": "Enter a station name or stop ID"},
                )
            try:
                results = await self.hass.async_add_executor_job(_search_stations, query)
            except Exception as err:
                _LOGGER.error("Search failed for '%s': %s", query, err)
                results = None
            if not results:
                return self.async_show_form(
                    step_id="search",
                    data_schema=vol.Schema({
                        vol.Required("query", default=query): TextSelector(TextSelectorConfig(type="text")),
                    }),
                    errors={"query": "No stations found. Try a different name or use manual entry."},
                )
            self._search_results = results
            return await self.async_step_pick_station()

        self._search_results = None
        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema({
                vol.Required("query"): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_pick_station(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            stop_id = user_input.get(CONF_STOP_ID)
            name = user_input.get(CONF_NAME, "")
            stations = [{"stop_id": stop_id, "name": name or ""}]
            self._search_results = None
            return self.async_create_entry(title=f"STPT {stop_id}", data={CONF_STATIONS: stations})

        results = self._search_results
        if not results:
            return await self.async_step_search()

        options = {r["stop_id"]: f"{r['stop_id']} - {r['name']}" for r in results}
        return self.async_show_form(
            step_id="pick_station",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): SelectSelector(SelectSelectorConfig(options=options)),
                vol.Optional(CONF_NAME, default=""): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            stations = [{"stop_id": user_input[CONF_STOP_ID], "name": user_input.get(CONF_NAME, "") or ""}]
            return self.async_create_entry(title=f"STPT {user_input[CONF_STOP_ID]}", data={CONF_STATIONS: stations})

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): TextSelector(TextSelectorConfig(type="text")),
                vol.Optional(CONF_NAME, default=""): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StptTransitOptionsFlow(config_entry)


class StptTransitOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._add_results: list[dict] | None = None

    def _current_stations(self) -> list[dict]:
        data = list(self._config_entry.data.get(CONF_STATIONS, []))
        opts = self._config_entry.options.get(CONF_STATIONS, [])
        seen = {s.get(CONF_STOP_ID) for s in data}
        for s in opts:
            if s.get(CONF_STOP_ID) not in seen:
                data.append(s)
                seen.add(s.get(CONF_STOP_ID))
        return data

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_search":
                return await self.async_step_add_search()
            if action == "add_manual":
                return await self.async_step_add_manual()
            if action == "remove":
                return await self.async_step_remove_station()
            return self.async_create_entry(title="", data={})

        current = self._current_stations()
        actions = {
            "add_search": "Search by name to add",
            "add_manual": "Enter stop ID to add",
            "remove": "Remove a station",
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="add_search"): vol.In(actions),
            }),
            description_placeholders={"station_count": str(len(current))},
        )

    async def async_step_add_search(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            query = user_input.get("query", "").strip()
            if not query:
                return self.async_show_form(
                    step_id="add_search",
                    data_schema=vol.Schema({
                        vol.Required("query"): TextSelector(TextSelectorConfig(type="text")),
                    }),
                    errors={"query": "Enter a station name"},
                )
            try:
                results = await self.hass.async_add_executor_job(_search_stations, query)
            except Exception as err:
                _LOGGER.error("Options search failed for '%s': %s", query, err)
                results = None
            if not results:
                return self.async_show_form(
                    step_id="add_search",
                    data_schema=vol.Schema({
                        vol.Required("query", default=query): TextSelector(TextSelectorConfig(type="text")),
                    }),
                    errors={"query": "No stations found"},
                )
            self._add_results = results
            return await self.async_step_add_pick()

        self._add_results = None
        return self.async_show_form(
            step_id="add_search",
            data_schema=vol.Schema({
                vol.Required("query"): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_add_pick(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            stations = self._current_stations()
            stop_id = user_input.get(CONF_STOP_ID)
            name = user_input.get(CONF_NAME, "")
            stations.append({"stop_id": stop_id, "name": name or ""})
            self._add_results = None
            return self.async_create_entry(title="", data={CONF_STATIONS: stations})

        results = self._add_results
        if not results:
            return await self.async_step_add_search()

        options = {r["stop_id"]: f"{r['stop_id']} - {r['name']}" for r in results}
        return self.async_show_form(
            step_id="add_pick",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): SelectSelector(SelectSelectorConfig(options=options)),
                vol.Optional(CONF_NAME, default=""): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_add_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            stations = self._current_stations()
            stations.append({"stop_id": user_input[CONF_STOP_ID], "name": user_input.get(CONF_NAME, "") or ""})
            return self.async_create_entry(title="", data={CONF_STATIONS: stations})

        return self.async_show_form(
            step_id="add_manual",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): TextSelector(TextSelectorConfig(type="text")),
                vol.Optional(CONF_NAME, default=""): TextSelector(TextSelectorConfig(type="text")),
            }),
        )

    async def async_step_remove_station(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = self._current_stations()
        if user_input is not None:
            to_remove = user_input.get("stop_id", "")
            stations = [s for s in current if s.get(CONF_STOP_ID) != to_remove]
            return self.async_create_entry(title="", data={CONF_STATIONS: stations})

        options = {s.get(CONF_STOP_ID): f"{s.get(CONF_STOP_ID)} - {s.get(CONF_NAME, '')}" for s in current}
        return self.async_show_form(
            step_id="remove_station",
            data_schema=vol.Schema({
                vol.Required("stop_id"): vol.In(options),
            }),
        )
