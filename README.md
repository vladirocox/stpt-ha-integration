# STPT Transit — Home Assistant Integration

> **English** — [Disponibil în limba română](README.ro.md)
> Also check out the [Inky pHAT Dashboard](https://github.com/vladirocox/inkystpt) — an e-ink display for STPT departures, weather, and Chromecast now-playing.

Monitor STPT (Societatea de Transport Public Timișoara) bus/tram/trolley stations in real time with full automation support.

## Features

- **Real-time arrivals** — polls `live.stpt.ro` at a configurable interval (default 10s, range 5-120s)
- **Schedule fallback** — when live API returns no data (late night, holidays), falls back to scraped schedule from `smtt.ro` (1h cache)
- **Multiple stations** — track any number of stations; add/remove anytime via UI
- **Per-line sensors** — each line at a station gets its own sensor showing minutes until next arrival
- **Vehicle tracking** — total active vehicles with per-line breakdown
- **Map support** — each sensor exposes `latitude` / `longitude` attributes for the built-in HA Map card
- **900+ stations** — full route network coordinates bundled
- **Alert monitoring** — binary sensor for active STPT alerts
- **Configurable polling** — refresh interval adjustable from 5 to 120 seconds
- **Dual language** — English and Romanian UI translations

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
3. Enter the **stop ID** (e.g. `74` for Gara de Nord)
4. Optionally pick which lines to track at that station

### Finding a stop ID

1. Open Google Maps and navigate to the bus/tram stop
2. Tap the stop marker — a popup shows details
3. Look for the **stop number** (STPT stop IDs are numeric, e.g. `74`, `836`, `1122`)

Alternatively, visit `https://live.stpt.ro`, search for your station, and note the `stopid=N` parameter in the URL.

### Adding more stations

After initial setup, go to **Settings → Devices & Services → STPT Transit → Configure** to add or remove stations.

1. Select **"Add a station"**
2. Enter the **stop ID** and optionally a name
3. Pick which lines to track (or accept all)
4. The new station's sensors appear automatically

Alternatively, use the CLI script:

```bash
docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py add 836 "Serena"
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
| `latitude` | float | For Map card |
| `longitude` | float | For Map card |
| `source` | str | `"live"` (from API) or `"schedule"` (scraped fallback) |
| `arrivals` | list | Full list of upcoming arrivals with line, destination, minutes, type |
| `arrival_count` | int | Number of upcoming arrivals for this line |
| `destination` | str | Destination of the next vehicle |
| `next_arrival_time` | str | Scheduled arrival time (HH:MM format) |
| `vehicle_type` | str | `"tram"`, `"trolley"`, or `"bus"` |
| `error` | str or null | Error message if the fetch failed |

A **Vehicles** sensor (`sensor.stpt_vehicles`) shows the total active vehicles and per-line breakdown.

## Automations

Because the sensor state is a **numeric minute value**, you can use standard HA `numeric_state` triggers:

### Notify 5 minutes before bus arrives

```yaml
alias: "Bus arriving in 5 minutes"
trigger:
  - platform: numeric_state
    entity_id: sensor.gara_de_nord
    below: 5
condition:
  - condition: template
    value_template: "{{ state_attr('sensor.gara_de_nord', 'source') == 'live' }}"
action:
  - service: notify.mobile_app
    data:
      title: "Bus arriving soon!"
      message: >
        Line {{ state_attr('sensor.gara_de_nord', 'next_line') }}
        to {{ state_attr('sensor.gara_de_nord', 'next_destination') }}
        arrives in {{ states('sensor.gara_de_nord') }} minutes
mode: single
```

### Flash lights when bus arrives

```yaml
alias: "Bus has arrived"
trigger:
  - platform: state
    entity_id: sensor.gara_de_nord
action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
    data:
      flash: short
mode: single
```

### TTS announcement when specific line is approaching

```yaml
alias: "M35 is coming"
trigger:
  - platform: numeric_state
    entity_id: sensor.gara_de_nord
    below: 3
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.gara_de_nord', 'next_line') == 'M35' }}
action:
  - service: tts.cloud_say
    data:
      entity_id: media_player.living_room_speaker
      message: "Bus M35 to {{ state_attr('sensor.gara_de_nord', 'next_destination') }} is arriving now"
mode: single
```

### Track when a bus leaves (arrivals list changes)

```yaml
alias: "Bus left station - update dashboard"
trigger:
  - platform: state
    entity_id: sensor.gara_de_nord
    attribute: arrivals
action:
  - service: script.refresh_dashboard
mode: queued
```

## Map Card

```yaml
type: map
entities:
  - entity: sensor.gara_de_nord
  - entity: sensor.catedrala_mitropolitana
  - entity: sensor.shopping_city
```

## Lovelace Card (Markdown)

```yaml
type: markdown
content: >
  {% set s = states.sensor.gara_de_nord %}

  **🚏 {{ s.attributes.station_name }}** ({{ s.attributes.stop_id }})

  {% if s.state != 'unknown' and s.state != 'none' %}
  Next: **Line {{ s.attributes.line }}** → {{ s.attributes.destination }}
  Arriving in **{{ s.state }} min** at {{ s.attributes.next_arrival_time }}
  {% else %}
  _No live data_
  {% endif %}

  {% for a in s.attributes.arrivals %}
  - {{ a.line }} → {{ a.destination }}: {{ a.minutes }} min{% if not a.live %} (schedule){% endif %}
  {% endfor %}
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
