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

### Finding a stop ID

1. Open Google Maps and navigate to the bus/tram stop
2. Tap the stop marker — a popup shows details
3. Look for the **stop number** (STPT stop IDs are numeric, e.g. `326`, `74`, `1122`)

Alternatively, visit `https://live.stpt.ro`, search for your station, and note the `stopid=N` parameter in the URL.

### Adding more stations

![Configure menu with Add/Remove options](assets/configure-menu.png)

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

Each station creates a sensor per tracked line. The sensor state is the **minutes until the next arrival** (numeric, suitable for automations).

| Attribute | Type | Description |
|-----------|------|-------------|
| `state` | int or null | Minutes until next bus arrives (or `null` if no data) |
| `unit_of_measurement` | `min` | For graphing |
| `stop_id` | str | STPT stop ID |
| `station_name` | str | Human-readable station name |
| `line` | str | Line number |
| `latitude` | float | Station GPS latitude (from route network) |
| `longitude` | float | Station GPS longitude (from route network) |
| `source` | str | `"live"` (from API) or `"schedule"` (scraped fallback) |
| `arrivals` | list | Upcoming arrivals with line, destination, minutes, type |
| `arrival_count` | int | Number of upcoming arrivals for this line |
| `destination` | str | Destination of the next vehicle |
| `next_arrival_time` | str | Scheduled arrival time (HH:MM format) |
| `vehicle_type` | str | `"tram"`, `"trolley"`, or `"bus"` |
| `error` | str or null | Error message if the fetch failed |

A **Vehicles** sensor (`sensor.stpt_vehicles`) shows total active vehicles and per-line breakdown.

## Automations

The sensor state is numeric (minutes), so `numeric_state` triggers work directly:

### Notify before arrival

```yaml
alias: "Bus arriving in 5 minutes"
trigger:
  - platform: numeric_state
    entity_id: sensor.catedrala_metropolitana_1
    below: 5
condition:
  - condition: template
    value_template: "{{ state_attr('sensor.catedrala_metropolitana_1', 'source') == 'live' }}"
action:
  - service: notify.mobile_app
    data:
      title: "Bus arriving soon!"
      message: >
        Line {{ state_attr('sensor.catedrala_metropolitana_1', 'destination') }}
        arrives in {{ states('sensor.catedrala_metropolitana_1') }} minutes
mode: single
```

### Flash lights on arrival

```yaml
alias: "Bus has arrived"
trigger:
  - platform: numeric_state
    entity_id: sensor.catedrala_metropolitana_1
    below: 1
action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
    data:
      flash: short
mode: single
```

## Data Sources

- **Live API**: `https://live.stpt.ro/proxy-smtt-cache.php?stopid=N`
- **Vehicles API**: `https://live.stpt.ro/gtfs-vehicles.php`
- **Schedule**: `https://smtt.ro/linie-transport-public-{LINE}/` (1h cache, scraped HTML)

## Development

```bash
cp -r custom_components/stpt_transit /path/to/ha/custom_components/
docker restart homeassistant
```

## License

MIT
