# STPT Transit — Home Assistant Integration

> **English** — [Disponibil în limba română](README.ro.md)
> Also check out the [Inky pHAT Dashboard](https://github.com/vladirocox/inkystpt) — an e-ink display for STPT departures, weather, and Chromecast now-playing.

Monitor STPT (Societatea de Transport Public Timișoara) bus/tram/trolley stations in real time with full automation support.

![STPT sensors in Dashboard](assets/dashboard-sensors.jpg)

## Features

- **Real-time arrivals** — polls `live.stpt.ro` at a configurable interval (default 10s, range 5-120s)
- **Schedule fallback** — when live API returns no data, falls back to scraped schedule from `smtt.ro` (1h cache)
- **Multiple stations** — track any number; add/remove anytime via UI
- **Per-line sensors** — each line at a station gets its own sensor showing minutes until next arrival
- **Vehicle tracking** — total active vehicles with per-line breakdown
- **Station coordinates** — lat/lng from the route network available as sensor attributes for map display
- **Alert monitoring** — binary sensor for active STPT disruptions
- **Configurable polling** — refresh interval adjustable from 5 to 120 seconds

## Installation

### Via HACS (recommended)

1. Make sure [HACS](https://hacs.xyz) is installed
2. Go to **HACS → Integrations → three-dot menu → Custom repositories**
3. Add: `https://github.com/vladirocox/stpt-ha-integration` with category **Integration**
4. Click **Install** on the "STPT Transit" card
5. Restart Home Assistant

### Manual

1. Copy `custom_components/stpt_transit/` to your HA `custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"STPT Transit"**
3. Enter the **stop ID** (e.g. `326` for Catedrala Metropolitană)
4. Optionally pick which lines to track at that station

![Add Integration dialog](assets/config-dialog.png)

![Configure menu with Add/Remove options](assets/configure-menu.png)

### Finding a stop ID

1. Open Google Maps and navigate to the bus/tram stop
2. Tap the stop marker — a popup shows details
3. Look for the **stop number** (STPT stop IDs are numeric, e.g. `326`, `74`, `1122`)

Alternatively, visit `https://live.stpt.ro`, search for your station, and note the `stopid=N` parameter in the URL.

![Finding a stop ID in Google Maps](assets/find-stop-id-google-maps.png)

### Adding more stations

After initial setup, go to **Settings → Devices & Services → STPT Transit → Configure** to add or remove stations.

1. Select **"Add a station"**
2. Enter the **stop ID** and optionally a name
3. Pick which lines to track (or accept all)
4. The new station's sensors appear automatically

Alternatively, use the CLI script:

```bash
docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py add 326 "Catedrala Metropolitană"
docker restart homeassistant
```

## Sensors

Each tracked line at a station gets its own sensor. The state shows the **time until next arrival** as a formatted string (e.g. `"17min"`, `"2h 43min"`).

| Attribute | Type | Description |
|-----------|------|-------------|
| `stop_id` | str | STPT stop ID |
| `station_name` | str | Human-readable station name |
| `line` | str | Line number |
| `source` | str | `"live"` (from API) or `"schedule"` (scraped fallback) |
| `arrivals` | list | Upcoming arrivals with line, destination, minutes, type |
| `arrival_count` | int | Number of upcoming arrivals for this line |
| `destination` | str | Destination of the next vehicle |
| `next_arrival_time` | str | Scheduled arrival time (HH:MM format) |
| `minutes_raw` | int | Raw minutes for automations |
| `vehicle_type` | str | `"tram"`, `"trolley"`, `"bus"`, or `"vaporetto"` |
| `latitude` | float | Station GPS latitude |
| `longitude` | float | Station GPS longitude |
| `error` | str or null | Error message if the fetch failed |

For **automations**, use the `minutes_raw` attribute with a numeric state trigger:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.pod_calea_sagului_e1
    attribute: minutes_raw
    below: 5
```

A few global sensors are also available:
- `sensor.stpt_latest_alert` — title of the most recent STPT alert
- `sensor.stpt_vehicles` — total active vehicles with `by_line` breakdown
- `binary_sensor.stpt_disruptions` — on/off if any alerts are active

## Data Sources

- **Live API**: `https://live.stpt.ro/proxy-smtt-cache.php?stopid=N`
- **Vehicles API**: `https://live.stpt.ro/gtfs-vehicles.php`
- **Schedule**: `https://smtt.ro/linie-transport-public-{LINE}/` (1h cache, scraped HTML)

## Development

```bash
cp -r custom_components/stpt_transit /path/to/ha/custom_components/
docker restart homeassistant
```

## Contributing

Found a bug or have an idea? Contributions are welcome — open an issue or a pull request on [GitHub](https://github.com/vladirocox/stpt-ha-integration).

## License

MIT
