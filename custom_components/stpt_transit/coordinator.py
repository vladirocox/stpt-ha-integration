from __future__ import annotations

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

from .const import DOMAIN, LIVE_API_URL, ALERTS_API_URL, UPDATE_INTERVAL

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
    raw = item.get("minutes") or item.get("eta_minutes") or 0
    if isinstance(raw, list):
        return [int(m) for m in raw if isinstance(m, (int, float))]
    if isinstance(raw, (int, float)):
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
            alert.get("header_text")
            or alert.get("headerText")
            or alert.get("title")
            or alert.get("header")
            or ""
        )
        description = (
            alert.get("description_text")
            or alert.get("descriptionText")
            or alert.get("description")
            or alert.get("text")
            or ""
        )
        result.append({
            "id": str(item.get("id") or alert.get("id") or ""),
            "title": str(title).strip(),
            "description": str(description).strip(),
            "cause": str(alert.get("cause") or ""),
            "effect": str(alert.get("effect") or ""),
            "start": alert.get("start"),
            "end": alert.get("end"),
        })
    return result


class StptTransitCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
            always_update=True,
        )
        self._stations_map = _load_stations_map()
        self._line_config = _load_line_config()
        self._session = async_get_clientsession(hass)
        self._schedule_cache: dict[str, Any] = {}
        self._alerts_cache: list[dict] | None = None
        self._alerts_ts: float = 0

    def search_stations(self, query: str, limit: int = 20) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        results = []
        for stop_id, info in self._stations_map.items():
            name = info[0].lower()
            if q in name or q in stop_id:
                results.append({
                    "stop_id": stop_id,
                    "name": info[0],
                    "latitude": info[1],
                    "longitude": info[2],
                })
        results.sort(key=lambda s: s["name"].lower())
        return results[:limit]

    def get_station_info(self, stop_id: str) -> dict:
        info = self._stations_map.get(stop_id)
        if info:
            return {"name": info[0], "latitude": info[1], "longitude": info[2]}
        return {"name": stop_id, "latitude": 0.0, "longitude": 0.0}

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

    async def _async_update_data(self) -> dict[str, Any]:
        stations = self.config_entry.data.get("stations", [])
        result = {}
        for station in stations:
            stop_id = station["stop_id"]
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

            result[stop_id] = {"arrivals": arrivals, "error": error, "source": source}

        result["alerts"] = await self._fetch_alerts()
        return result
