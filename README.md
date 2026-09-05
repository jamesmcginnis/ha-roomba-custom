# Roomba Custom (Legacy TLS)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/jamesmcginnis/ha-roomba-custom.svg?style=flat-square)](LICENSE)

A Home Assistant custom integration for iRobot Roomba that connects **directly over your local network** — no cloud polling, no internet dependency once set up.

Includes a cipher-rotation fix that makes older Roomba firmware work reliably with modern Python/OpenSSL.

---

## Install via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jamesmcginnis&repository=ha-roomba-custom&category=integration)

1. Click the button above — Home Assistant opens and asks you to confirm adding the repo
2. In HACS find **Roomba Custom (Legacy TLS)** and click **Download**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** → search **Roomba Custom**

### Manual installation

1. Download `ha-roomba-custom.zip` from the [latest release](https://github.com/jamesmcginnis/ha-roomba-custom/releases/latest)
2. Extract and copy the `custom_components/roomba_custom` folder into `/config/custom_components/`
3. Restart Home Assistant

---

## Why this integration?

The built-in HA Roomba integration uses `roombapy`, which has recurring TLS cipher compatibility issues with certain Roomba firmware versions under modern Python 3.12 / OpenSSL 3. This integration works around it with a "don't infinite loop on ciphers" fix:

Two cipher strings are tried in sequence (`AES128-SHA256` → `TLS_AES_256_GCM_SHA384`). If the robot rejects the first via a TLS error or MQTT "identifier rejected" response, it automatically retries with the second — once, not in a loop.

---

## Features

- ✅ Sign in with your iRobot email and password — Roomba found automatically
- ✅ Start, pause, stop, dock, locate
- ✅ Real-time state updates: cleaning / docked / returning / paused / idle / error
- ✅ Battery level with configurable low-battery threshold
- ✅ Bin full binary sensor
- ✅ Stuck binary sensor
- ✅ Mission time and area cleaned sensors
- ✅ Reconnect flood protection (backs off 5 min after 5 reconnects in 30 s)
- ✅ Configurable off-action (pause+dock, stop+dock, pause only, etc.)
- ✅ Room-by-room cleaning via `vacuum.send_command`

---

## Setup

Enter the same **email and password** you use in the iRobot app. The integration logs into your account, finds your Roomba, and discovers its IP address automatically. If you have multiple Roombas you will be shown a list to pick from.

---

## Configuration options

After setup, click **Configure** on the integration card to adjust:

| Option | Default | Description |
|---|---|---|
| Low battery threshold | 20% | Battery % that triggers the low battery warning |
| Off action | Pause then dock | What happens when the vacuum entity is turned off |
| Hide Stuck sensor | Off | Removes the stuck binary sensor |
| Hide Bin Full sensor | Off | Removes the bin full binary sensor |

---

## Entities

| Entity | Type | Description |
|---|---|---|
| `vacuum.your_roomba` | Vacuum | Main control — start, pause, stop, dock, locate |
| `sensor.your_roomba_battery` | Sensor | Battery percentage |
| `sensor.your_roomba_mission_time` | Sensor | Minutes cleaning this session |
| `sensor.your_roomba_area_cleaned` | Sensor | Square feet cleaned this session |
| `binary_sensor.your_roomba_bin_full` | Binary Sensor | On when the bin is full |
| `binary_sensor.your_roomba_stuck` | Binary Sensor | On when the robot is stuck |

---

## Room-by-room cleaning

```yaml
action: vacuum.send_command
target:
  entity_id: vacuum.your_roomba
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

The `pmap_id` and region values appear in the vacuum's `extra_state_attributes` under `last_command` after a manual room clean via the iRobot app.

---

## Compatible models

Confirmed working: Y0.

---

## Troubleshooting

**Cannot connect during setup**
- Close the iRobot app completely — the robot only allows one local MQTT connection at a time
- Confirm the IP address is reachable from HA on port 8883
- Disable the built-in HA iRobot integration if it is also running

**Entities go unavailable**
- Something else is holding the MQTT connection — check HA logs for `roomba_custom`
- The integration backs off automatically for 5 minutes after 5 reconnects in 30 seconds

---

## License

MIT © [jamesmcginnis](https://github.com/jamesmcginnis)
