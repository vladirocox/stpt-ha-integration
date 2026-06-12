from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    LIVE_API_URL,
    ALERTS_API_URL,
    VEHICLES_API_URL,
    CONF_STATIONS,
    CONF_REFRESH_INTERVAL,
    DEFAULT_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type StptTransitConfigEntry = ConfigEntry[StptTransitCoordinator]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://live.stpt.ro/",
}
SCHEDULE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}
SCHEDULE_TTL = 3600
ALERTS_TTL = 45


def _load_stations_map() -> dict[str, list]:
    path = os.path.join(os.path.dirname(__file__), "stations_map.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_line_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "lines_config.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _parse_arrivals(raw: Any) -> list[dict]:
    if isinstance(raw, dict):
        raw = raw.get("arrivals") or raw.get("data") or raw.get("times") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        minutes = _extract_minutes(item)
        times = _extract_times(item)
        result.append({
            "line": str(item.get("line") or item.get("route") or ""),
            "destination": str(item.get("headsign") or item.get("destination") or ""),
            "minutes": minutes[0] if minutes else 0,
            "minutes_list": minutes,
            "type": str(item.get("type") or item.get("vehicle_type") or "bus"),
            "arrival_time": times[0] if times else None,
            "arrival_times": times,
            "vehicle_id": item.get("vehicleId"),
            "live": True,
        })
    return result


def _extract_minutes(item: dict) -> list[int]:
    raw = item.get("minutes")
    if raw is not None and isinstance(raw, list):
        return [int(m) for m in raw if isinstance(m, (int, float))]
    if raw is not None and isinstance(raw, (int, float)):
        return [int(raw)]
    raw_times = item.get("times") or []
    if isinstance(raw_times, list):
        mins = []
        for t in raw_times:
            if isinstance(t, str) and "|" in t:
                parts = t.split("|")
                if len(parts) > 1 and parts[1].strip().isdigit():
                    mins.append(int(parts[1].strip()))
        return mins
    return []


def _extract_times(item: dict) -> list[str]:
    raw_times = item.get("times") or []
    if not isinstance(raw_times, list):
        return []
    times = []
    for t in raw_times:
        if isinstance(t, str):
            time_part = t.split("|")[0].strip()
            if time_part:
                times.append(time_part)
        elif isinstance(t, dict):
            time_part = str(t.get("time", "")).strip()
            if time_part:
                times.append(time_part)
    return times


def _parse_schedule_times(html: str, stop_id: str) -> list[str]:
    pattern = re.escape(stop_id) + r'"[^>]*data-times="([^"]*)"'
    m = re.search(pattern, html)
    if not m:
        return []
    raw = m.group(1)
    result = []
    for part in raw.split(","):
        part = part.strip()
        if not part or "|" not in part:
            continue
        hour_str, rest = part.split("|", 1)
        minute_str = rest.split("-")[0].strip()
        if minute_str:
            try:
                h = int(hour_str)
                m = int(minute_str)
                result.append(f"{h:02d}:{m:02d}")
            except ValueError:
                pass
    return result


def _compute_minutes_from_now(time_str: str) -> int:
    now = datetime.now()
    try:
        parts = time_str.split(":")
        target = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
    except (ValueError, IndexError):
        return 0
    delta = (target - now).total_seconds() / 60
    if delta < 0:
        delta += 1440
    return max(1, int(round(delta)))


def _extract_alert_text(value: Any) -> str:
    if isinstance(value, dict):
        translations = value.get("translation", [])
        if translations and isinstance(translations, list) and isinstance(translations[0], dict):
            return str(translations[0].get("text", "")).strip()
        return str(value).strip()
    return str(value).strip() if value is not None else ""


def _parse_alerts(raw: Any) -> list[dict]:
    if isinstance(raw, dict):
        raw = raw.get("alerts") or raw.get("entity") or []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        item_alert = item.get("alert")
        alert = item_alert if isinstance(item_alert, dict) else item
        title = (
            _extract_alert_text(alert.get("header_text"))
            or _extract_alert_text(alert.get("headerText"))
            or _extract_alert_text(alert.get("title"))
            or _extract_alert_text(alert.get("header"))
            or ""
        )
        description = (
            _extract_alert_text(alert.get("description_text"))
            or _extract_alert_text(alert.get("descriptionText"))
            or _extract_alert_text(alert.get("description"))
            or _extract_alert_text(alert.get("text"))
            or ""
        )
        result.append({
            "id": str(item.get("id") or alert.get("id") or ""),
            "title": title,
            "description": description,
            "cause": str(alert.get("cause") or ""),
            "effect": str(alert.get("effect") or ""),
            "start": alert.get("start"),
            "end": alert.get("end"),
        })
    return result


class StptTransitCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, stations_map: dict | None = None, line_config: dict | None = None) -> None:
        interval = entry.options.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
            always_update=True,
        )
        self._stations_map = stations_map if stations_map is not None else {}
        self._line_config = line_config if line_config is not None else {}
        self._session = async_get_clientsession(hass)
        self._schedule_cache: dict[str, Any] = {}
        self._alerts_cache: list[dict] | None = None
        self._alerts_ts: float = 0

    def _get_stations(self) -> list[dict]:
        opts = self.config_entry.options.get(CONF_STATIONS)
        if opts is not None:
            return list(opts)
        return list(self.config_entry.data.get(CONF_STATIONS, []))

    def get_station_info(self, stop_id: str) -> dict:
        info = self._stations_map.get(stop_id)
        if info:
            return {"name": info[0], "latitude": info[1], "longitude": info[2]}
        return {"name": stop_id, "latitude": 0.0, "longitude": 0.0}

    def get_lines_for_stop(self, stop_id: str) -> list[dict]:
        return self._get_lines_for_stop(stop_id)

    def _get_lines_for_stop(self, stop_id: str) -> list[dict]:
        results = []
        for line_id, line_data in self._line_config.items():
            for direction in ("tur", "retur"):
                dd = line_data.get(direction, {})
                ids = dd.get("ids", [])
                names = dd.get("stations", [])
                for i, sid in enumerate(ids):
                    if sid == stop_id:
                        name = names[i] if i < len(names) else ""
                        results.append({"line": line_id, "direction": direction, "stop_name": name})
        return results

    def _get_smtt_url(self, line: str, direction: str) -> str:
        line_slug = "linie-transport-public-" + line.lower().replace(" ", "")
        if direction == "retur":
            line_slug += "-r"
        return f"https://smtt.ro/{line_slug}/"

    async def _fetch_schedule(self, stop_id: str) -> list[dict]:
        now_ts = time.time()
        cached = self._schedule_cache.get(stop_id)
        if cached and (now_ts - cached["ts"]) < SCHEDULE_TTL:
            return cached["times"]

        line_info = self._get_lines_for_stop(stop_id)
        if not line_info:
            return []

        all_times = []
        seen = set()
        for info in line_info:
            url = self._get_smtt_url(info["line"], info["direction"])
            try:
                async with self._session.get(url, headers=SCHEDULE_HEADERS, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
            except (aiohttp.ClientError, TimeoutError):
                continue

            raw_times = _parse_schedule_times(html, stop_id)
            for t in raw_times:
                dedup_key = f"{t}|{info['line']}"
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    mins = _compute_minutes_from_now(t)
                    all_times.append({
                        "time": t,
                        "line": info["line"],
                        "minutes": mins,
                        "live": False,
                        "type": "bus",
                        "destination": info["stop_name"],
                    })

        all_times.sort(key=lambda x: x["minutes"])

        self._schedule_cache[stop_id] = {"times": all_times, "ts": now_ts}
        return all_times

    async def _fetch_alerts(self) -> list[dict]:
        now_ts = time.time()
        if self._alerts_cache is not None and (now_ts - self._alerts_ts) < ALERTS_TTL:
            return self._alerts_cache
        try:
            async with self._session.get(ALERTS_API_URL, headers=REQUEST_HEADERS, timeout=10) as resp:
                if resp.status != 200:
                    return self._alerts_cache or []
                raw = await resp.json()
                alerts = _parse_alerts(raw)
                self._alerts_cache = alerts
                self._alerts_ts = now_ts
                return alerts
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError):
            return self._alerts_cache or []

    async def _fetch_vehicles(self) -> dict:
        try:
            async with self._session.get(VEHICLES_API_URL, headers=REQUEST_HEADERS, timeout=10) as resp:
                if resp.status != 200:
                    return {"total": 0, "vehicles": [], "by_line": []}
                raw = await resp.json()
                if not isinstance(raw, dict) or not raw.get("success"):
                    return {"total": 0, "vehicles": [], "by_line": []}
                data = raw.get("data", {})
                return {
                    "total": data.get("total", 0),
                    "vehicles": data.get("vehicles", []),
                    "by_line": data.get("byLine", {}),
                }
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError):
            return {"total": 0, "vehicles": [], "by_line": {}}

    async def _fetch_station_arrivals(self, stop_id: str) -> dict:
        arrivals = []
        error = None
        source = "live"

        try:
            url = f"{LIVE_API_URL}?stopid={stop_id}"
            async with self._session.get(url, headers=REQUEST_HEADERS, timeout=10) as resp:
                if resp.status != 200:
                    error = f"HTTP {resp.status}"
                else:
                    raw = await resp.json()
                    living = _parse_arrivals(raw)
                    if living:
                        arrivals = living
                    else:
                        source = "schedule"
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as err:
            error = str(err)
            source = "schedule"

        if source == "schedule" and error is None:
            try:
                schedule = await self._fetch_schedule(stop_id)
                arrivals = schedule
            except Exception as err:
                error = str(err) if not error else error

        return {"stop_id": stop_id, "arrivals": arrivals, "error": error, "source": source}

    async def _async_update_data(self) -> dict[str, Any]:
        stations = self._get_stations()
        if not stations:
            return {"alerts": [], "vehicles": {"total": 0, "vehicles": [], "by_line": []}}

        station_tasks = [
            self._fetch_station_arrivals(station["stop_id"])
            for station in stations
        ]
        station_tasks.append(self._fetch_alerts())
        station_tasks.append(self._fetch_vehicles())
        tag_keys = [s["stop_id"] for s in stations] + ["alerts", "vehicles"]
        results = await asyncio.gather(*station_tasks)
        return dict(zip(tag_keys, results))
