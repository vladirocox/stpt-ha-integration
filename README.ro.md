# STPT Transit — Integrare Home Assistant

> **Română** — [Available in English](README.md)
> Vizualizează și [Dashboard-ul pe cerneală electronică Inky pHAT](https://github.com/vladirocox/inkystpt) — un afișaj e-ink pentru plecări STPT, vreme și redări Chromecast.

Monitorizează stațiile de autobuz/tramvai/troleibuz/vaporetto STPT (Societatea de Transport Public Timișoara) în timp real, cu suport complet pentru automatizări.

![Senzori STPT în Dashboard](assets/dashboard-sensors.jpg)

## Funcționalități

- **Sosiri în timp real** — interoghează `live.stpt.ro` la un interval configurabil (implicit 60s, interval 5-120s)
- **Program de rezervă** — când API-ul live nu returnează date, folosește programul preluat de pe `smtt.ro` (cache 1h)
- **Stații multiple** — monitorizează oricâte; adaugă/elimină oricând din UI
- **Senzori pe linie** — fiecare linie are propriul senzor cu minutele până la următoarea sosire
- **Urmărire vehicule** — numărul total de vehicule active defalcat pe linii
- **Coordonate stații** — lat/lng din rețeaua de rute disponibile ca atribute pentru hartă
- **Monitorizare alerte** — senzor binar pentru întreruperi STPT
- **Interogare configurabilă** — interval de reîmprospătare între 5 și 120 de secunde

## Instalare

### Prin HACS (recomandat)

1. Asigură-te că [HACS](https://hacs.xyz) este instalat
2. Mergi la **HACS → Integrations → meniul cu trei puncte → Custom repositories**
3. Adaugă: `https://github.com/vladirocox/stpt-ha-integration` cu categoria **Integration**
4. Apasă **Install** pe cardul "STPT Transit"
5. Repornește Home Assistant

### Manual

1. Copiază `custom_components/stpt_transit/` în directorul `custom_components/` al HA-ului tău
2. Repornește Home Assistant

## Configurare

1. Mergi la **Settings → Devices & Services → Add Integration**
2. Caută **"STPT Transit"**
3. Introdu **ID-ul stației** (ex: `326` pentru Catedrala Metropolitană)
4. Opțional, selectează liniile de monitorizat la acea stație

![Dialog Adăugare Integrare](assets/config-dialog.png)

![Meniu Configurare cu opțiuni Adăugare/Eliminare](assets/configure-menu.png)

### Cum găsești ID-ul unei stații

1. Deschide Google Maps și navighează la stația de autobuz/tramvai
2. Apasă pe markerul stației — apare un popup cu detalii
3. Caută **numărul stației** (ID-urile STPT sunt numerice, ex: `326`, `74`, `1122`)

Alternativ, vizitează `https://live.stpt.ro`, caută stația și notează parametrul `stopid=N` din URL.

![Cum găsești ID-ul stației în Google Maps](assets/find-stop-id-google-maps.png)

### Adăugarea stațiilor

După configurare, mergi la **Settings → Devices & Services → STPT Transit → Configure** pentru a adăuga sau elimina stații.

1. Selectează **"Add a station"**
2. Introdu **ID-ul stației** și opțional un nume
3. Alege liniile de monitorizat (sau acceptă-le pe toate)
4. Senzorii noii stații apar automat

Alternativ, folosește scriptul CLI:

```bash
docker exec homeassistant python3 /config/custom_components/stpt_transit/tools/manage_stations.py add 326 "Catedrala Metropolitană"
docker restart homeassistant
```

## Senzori

Fiecare linie monitorizată la o stație are propriul senzor. Starea arată **timpul până la următoarea sosire** ca text formatat (ex: `"17min"`, `"2h 43min"`).

| Atribut | Tip | Descriere |
|---------|-----|-----------|
| `stop_id` | str | ID-ul stației STPT |
| `station_name` | str | Numele stației |
| `line` | str | Numărul liniei |
| `source` | str | `"live"` (din API) sau `"schedule"` (program de rezervă) |
| `arrivals` | list | Lista sosirilor cu linie, destinație, minute, tip |
| `arrival_count` | int | Numărul de sosiri viitoare pentru această linie |
| `destination` | str | Destinația următorului vehicul |
| `next_arrival_time` | str | Ora programată a sosirii (format HH:MM) |
| `minutes_raw` | int | Minutele brute pentru automatizări |
| `vehicle_type` | str | `"tram"`, `"trolley"`, `"bus"` sau `"vaporetto"` |
| `latitude` | float | Latitudinea GPS a stației |
| `longitude` | float | Longitudinea GPS a stației |
| `error` | str sau null | Mesaj de eroare dacă preluarea a eșuat |

Pentru **automatizări**, folosește atributul `minutes_raw` cu un trigger numeric:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.pod_calea_sagului_e1
    attribute: minutes_raw
    below: 5
```

Câțiva senzori globali sunt disponibili:
- `sensor.stpt_latest_alert` — titlul celei mai recente alerte STPT
- `sensor.stpt_vehicles` — numărul total de vehicule active cu defalcarea `by_line`
- `binary_sensor.stpt_disruptions` — pornit/oprit dacă există alerte active

## Surse de date

- **API live**: `https://live.stpt.ro/proxy-smtt-cache.php?stopid=N`
- **API vehicule**: `https://live.stpt.ro/gtfs-vehicles.php`
- **Program**: `https://smtt.ro/linie-transport-public-{LINE}/` (cache 1h, HTML)

## Dezvoltare

```bash
cp -r custom_components/stpt_transit /path/to/ha/custom_components/
docker restart homeassistant
```

## Contribuții

Vrei să contribui? Ai găsit o problemă sau ai o sugestie? Deschide un issue sau un pull request pe [GitHub](https://github.com/vladirocox/stpt-ha-integration).

## Licență

MIT
