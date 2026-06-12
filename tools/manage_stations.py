#!/usr/bin/env python3
"""
STPT Station Manager — add/remove/list stations in HA config entries.

Usage:
  # Run inside HA container:
  docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py add 836 "My Station"
  docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py remove 836
  docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py list
  docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py reload
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

STORAGE_PATH = "/config/.storage/core.config_entries"
DOMAIN = "stpt_transit"
CONF_STATIONS = "stations"


def _load():
    with open(STORAGE_PATH) as f:
        return json.load(f)


def _save(data):
    with open(STORAGE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _find_entry(data):
    for e in data["data"]["entries"]:
        if e.get("domain") == DOMAIN:
            return e
    return None


def cmd_list():
    data = _load()
    entry = _find_entry(data)
    if not entry:
        print("No STPT config entry found.")
        return
    stations = entry.get("data", {}).get(CONF_STATIONS, [])
    opts_stations = entry.get("options", {}).get(CONF_STATIONS)
    if opts_stations is not None:
        stations = opts_stations

    print(f"Entry: {entry['entry_id']} ({entry['title']})")
    print(f"Source: {entry.get('source')}, State: {entry.get('state', 'unknown')}")
    print(f"Options refresh_interval: {entry.get('options', {}).get('refresh_interval', 'default')}")
    print(f"\nStations ({len(stations)}):")
    for s in stations:
        sid = s.get("stop_id", "?")
        name = s.get("name", "") or "(unnamed)"
        lines = s.get("lines", [])
        lines_str = ", ".join(lines) if lines else "(all)"
        print(f"  {sid:6s}  {name:30s}  lines: {lines_str}")


def cmd_add(stop_id, name=""):
    data = _load()
    entry = _find_entry(data)
    if not entry:
        print(f"No STPT config entry found. Creating one...")
        now = datetime.now(timezone.utc).isoformat()
        entry_id = str(uuid.uuid4())
        entry = {
            "created_at": now,
            "data": {CONF_STATIONS: []},
            "disabled_by": None,
            "discovery_keys": {},
            "domain": DOMAIN,
            "entry_id": entry_id,
            "minor_version": 1,
            "modified_at": now,
            "options": {},
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "subentries": {},
            "title": f"STPT {stop_id}",
            "unique_id": None,
            "version": 1,
        }
        data["data"]["entries"].append(entry)

    # Prefer options over data for stations list
    stations = entry.get("options", {}).get(CONF_STATIONS)
    if stations is None:
        stations = entry.get("data", {}).get(CONF_STATIONS, [])
        entry["data"][CONF_STATIONS] = list(stations)

    stations = list(stations)
    # Check if station already exists
    for s in stations:
        if s.get("stop_id") == stop_id:
            print(f"Station {stop_id} already exists")
            return

    station = {"stop_id": stop_id}
    if name:
        station["name"] = name
    stations.append(station)
    entry["options"][CONF_STATIONS] = stations
    entry["modified_at"] = datetime.now(timezone.utc).isoformat()
    _save(data)
    print(f"Added station {stop_id} ({name or 'unnamed'})")


def cmd_remove(stop_id):
    data = _load()
    entry = _find_entry(data)
    if not entry:
        print("No STPT config entry found.")
        return

    stations = entry.get("options", {}).get(CONF_STATIONS)
    if stations is None:
        stations = entry.get("data", {}).get(CONF_STATIONS, [])
        entry["data"][CONF_STATIONS] = list(stations)

    before = len(stations)
    stations = [s for s in stations if s.get("stop_id") != stop_id]
    if len(stations) == before:
        print(f"Station {stop_id} not found")
        return

    entry["options"][CONF_STATIONS] = stations
    entry["modified_at"] = datetime.now(timezone.utc).isoformat()
    _save(data)
    print(f"Removed station {stop_id}")


def cmd_reload():
    """Reload STPT integration by calling HA API via internal service."""
    try:
        from homeassistant.core import HomeAssistant
        from homeassistant.helpers import entity_registry
        import homeassistant.util.yaml.loader
    except ImportError:
        print("Cannot reload: not running inside HA. Restart HA manually.")
        print("  docker restart homeassistant")
        return

    # Write a marker file that HA's async_setup_entry will detect
    marker = f"/config/.stpt_reload_{int(time.time())}"
    with open(marker, "w") as f:
        f.write("reload")
    print("Wrote reload marker. Restart HA to pick up changes:")
    print("  docker restart homeassistant")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "list":
        cmd_list()
    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: manage_stations.py add <stop_id> [name]")
            sys.exit(1)
        stop_id = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        cmd_add(stop_id, name)
    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: manage_stations.py remove <stop_id>")
            sys.exit(1)
        cmd_remove(sys.argv[2])
    elif command == "reload":
        cmd_reload()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
