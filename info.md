# STPT Transit (Timișoara)

Monitor STPT stations in real time.

## Features

- Real-time arrivals from live.stpt.ro (15s polling)
- Schedule fallback from smtt.ro when live API is empty
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
