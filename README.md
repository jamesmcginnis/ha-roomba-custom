# Roomba Custom (Legacy TLS)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/jamesmcginnis/ha-roomba-custom.svg?style=flat-square)](LICENSE)

A Home Assistant custom integration for iRobot Roomba that connects **directly over your local network** — no cloud polling, no internet dependency once set up.

Ported from [homebridge-iRobot-v2 v3.2.5-alpha.4](https://github.com/taurgis/homebridge-iRobot-v2/releases/tag/3.2.5-alpha.4) by taurgis, including the exact cipher-rotation fix that makes older Roomba firmware work with modern Python/OpenSSL.

---

## Screenshots

### Dashboard card

![Roomba Custom dashboard card showing robot status, battery level, and controls](preview1.png)

### Setup wizard

![Setup wizard showing iRobot account sign-in screen](preview2.png)

### Entities created in Home Assistant

![List of entities created by the integration in Home Assistant](preview3.png)

---

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jamesmcginnis&repository=ha-roomba-custom&category=integration)

1. Click the button above — Home Assistant opens and asks you to confirm adding the repo
2. In HACS find **Roomba Custom (Legacy TLS)** and click **Download**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** → search **Roomba Custom**

### Manual

1. Download `ha-roomba-custom.zip` from the [latest release](https://github.com/jamesmcginnis/ha-roomba-custom/releases/latest)
2. Extract and copy the `custom_components/roomba_custom` folder into your `/config/custom_components/` directory
3. Restart Home Assistant

---

## Why this integration?

The built-in HA Roomba integration uses `roombapy`, which has recurring TLS cipher compatibility issues with certain Roomba firmware versions under modern Python 3.12 / OpenSSL 3. This integration ports the exact fix from the Homebridge plugin:

> **"Don't infinite loop on ciphers"** — commit `ec541a8`, homebridge-iRobot-v2 v3.2.5-alpha.4

Two cipher strings are tried in sequence (`AES128-SHA256` → `TLS_AES_256_GCM_SHA384`). If the robot rejects the first cipher via a TLS error or MQTT "identifier rejected" response, it automatically retries with the second — once, not in a loop.

---

## Features

- ✅ Sign in with your iRobot email and password — Roomba found automatically
- ✅ Start, pause, stop, dock, locate
- ✅ Real-time state updates: cleaning / docked / returning / paused / idle / error
- ✅ Battery level with configurable low-battery threshold
- ✅ Bin full binary sensor
- ✅ Stuck binary sensor with notifications
- ✅ Mission time and area cleaned sensors
- ✅ Reconnect flood protection
- ✅ Configurable off-action (pause+dock, stop+dock, pause only, etc.)
- ✅ Room-by-room cleaning via `vacuum.send_command`
- ✅ Custom Lovelace dashboard card included

---

## Setup

When you add the integration you will be asked how you want to connect:

### Option A — iRobot account (recommended)

Enter the same **email and password** you use in the iRobot app. The integration logs into your account, finds your Roomba, and discovers its IP address on your local network automatically. If you have multiple Roombas you will be shown a list to pick from.

### Option B — Manual entry

If you prefer not to enter your cloud credentials, you can supply the IP address, BLID and local password directly. To retrieve these run the following in your HA terminal:

```bash
docker exec homeassistant python -c \
  'import roombapy.entry_points; roombapy.entry_points.password()' YOUR_ROOMBA_IP
```

Hold the **HOME button** on the robot for ~2 seconds when prompted. Note the `BLID` and `Password` values from the output.

> ⚠️ Close the iRobot app on your phone first. The Roomba only allows one local connection at a time.

---

## Configuration options

After setup, click **Configure** on the integration card to adjust:

| Option | Default | Description |
|---|---|---|
| Low battery threshold | 20% | Battery % that triggers the low battery state |
| Off action | Pause then dock | What happens when the vacuum entity is turned off |
| Hide Stuck sensor | Off | Removes the stuck binary sensor |
| Hide Bin Full sensor | Off | Removes the bin full binary sensor |

---

## Dashboard card

A custom Lovelace card is included in `www/roomba-card.js`.

**Install the card:**

1. Copy `www/roomba-card.js` to `/config/www/roomba-card.js`
2. Go to **Settings → Dashboards → ⋮ → Resources → Add Resource**
   - URL: `/local/roomba-card.js`
   - Type: **JavaScript module**
3. Hard-refresh your browser (Ctrl+Shift+R / Cmd+Shift+R)

**Add to a dashboard** using a Manual card:

```yaml
type: custom:roomba-card
entity: vacuum.roomba
name: Roomba
battery_entity: sensor.roomba_battery
bin_entity: binary_sensor.roomba_bin_full
stuck_entity: binary_sensor.roomba_stuck
mission_time_entity: sensor.roomba_mission_time
area_entity: sensor.roomba_area_cleaned
```

Only `entity` is required — all sensor lines are optional.

---

## Entities

| Entity | Type | Description |
|---|---|---|
| `vacuum.roomba` | Vacuum | Main control — start, pause, stop, dock, locate |
| `sensor.roomba_battery` | Sensor | Battery percentage |
| `sensor.roomba_mission_time` | Sensor | Minutes cleaning this session |
| `sensor.roomba_area_cleaned` | Sensor | Square feet cleaned this session |
| `binary_sensor.roomba_bin_full` | Binary Sensor | On when the bin is full |
| `binary_sensor.roomba_stuck` | Binary Sensor | On when the robot is stuck |

---

## Room-by-room cleaning

```yaml
service: vacuum.send_command
target:
  entity_id: vacuum.roomba
data:
  command: clean_room
  params:
    pmap_id: "YOUR_PMAP_ID"
    user_pmapv_id: "YOUR_PMAPV_ID"
    ordered: 1
    regions:
      - region_id: "5"
        type: "rid"
```

The `pmap_id` and region values appear in the vacuum's `extra_state_attributes` under `last_command` after a manual room clean via the iRobot app — copy those values from there.

---

## Compatible models

This integration uses the same local MQTT/TLS protocol as the Homebridge plugin it is ported from. If your robot works with that plugin it will work here. Confirmed working families include the 600, 800, 900, e, i, j, and s series, Braava m6, and Roomba Combo models including the Y0 series.

Very new Matter-first hardware (e.g. Combo Max 705) uses a different v4 protocol that is not yet supported.

---

## Troubleshooting

**Cannot connect during setup**
- Close the iRobot app completely — the robot only allows one local MQTT connection at a time
- Check the IP address is reachable from your HA host on port 8883
- Disable the built-in HA iRobot integration if it is running at the same time

**Entities go unavailable**
- Something else is holding the connection — check HA logs for `roomba_custom`
- If the robot reconnects more than 5 times in 30 seconds the integration backs off for 5 minutes automatically

**Still failing to connect**
- Try setting Protocol Version to `3` in the manual setup — some older 800-series firmware requires this

---

## Publishing a release

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds and attaches the zip to the release automatically. HACS users will see an update notification.

---

## Credits

- [taurgis/homebridge-iRobot-v2](https://github.com/taurgis/homebridge-iRobot-v2) — original Homebridge plugin this is ported from
- [koalazak/dorita980](https://github.com/koalazak/dorita980) — Roomba local MQTT protocol research
- [pschmitt/roombapy](https://github.com/pschmitt/roombapy) — Python Roomba library

---

## License

MIT © [jamesmcginnis](https://github.com/jamesmcginnis)
