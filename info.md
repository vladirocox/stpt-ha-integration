# STPT Transit (Timișoara)

Monitor STPT stations in real time.

## Features

- Real-time arrivals from live.stpt.ro (configurable polling)
- Schedule fallback from smtt.ro when live API is empty
- Per-line sensors showing minutes until next arrival
- Vehicle tracking with per-line breakdown
- Multiple configurable stations
- Map support via lat/lon attributes
- 900+ station coordinates bundled
- Fully configurable via HA UI

## Installation

Add via HACS as custom repo, or copy `custom_components/stpt_transit/` to your HA `custom_components/`.

## Quick Start

1. Settings → Devices & Services → Add Integration → "STPT Transit"
2. Enter stop ID (e.g. `74` for Gara de Nord)
3. Configure to add more stations via Options
4. Use sensors in your dashboard with Map cards

See `README.md` for full docs.

## Related

Prefer asking in plain language? [STPT MCP](https://github.com/vladirocox/stpt-mcp)
serves the same live arrivals as an MCP server for AI assistants and chat
clients. Also see the [Inky pHAT dashboard](https://github.com/vladirocox/inkystpt)
for a Raspberry Pi e-ink departures display.
