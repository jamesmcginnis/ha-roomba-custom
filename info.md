# Roomba Custom (Legacy TLS)

If you enjoy Roomba Custom, you can support its development:

[![Buy Me a Coffee](https://img.buymeacoffee.com/button-api/?text=Buy%20Me%20a%20Coffee&emoji=&slug=jamesmcginnis&button_colour=FFDD00&font_colour=000000&font_family=Inter&outline_colour=000000&coffee_colour=ffffff)](https://buymeacoffee.com/jamesmcginnis)

Local network control for iRobot Roomba — with a cipher-rotation fix that makes older firmware work reliably with modern Home Assistant.

## What's included

- **Automatic setup** — sign in with your iRobot email and password, your Roomba is found automatically
- **Local push** — connects directly over your LAN via MQTT/TLS, no cloud polling after setup
- **Full control** — start, pause, stop, dock, locate, room-by-room cleaning
- **Sensors** — battery level, bin full, stuck detection, mission time, area cleaned

## Install via HACS

**Step 1 — Add the repository to HACS:**

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jamesmcginnis&repository=ha-roomba-custom&category=integration)

**Step 2 — After downloading and restarting, add the integration:**

[![Open your Home Assistant instance and start setting up Roomba Custom.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=roomba_custom)

## Why not the built-in integration?

Certain Roomba firmware versions reject the TLS cipher that modern Python/OpenSSL offers by default, causing the connection to fail silently. This integration tries two cipher strings in sequence and automatically switches if the first is rejected.

## Compatible models

Confirmed working: Y0+.

---

For full documentation see the [README](https://github.com/jamesmcginnis/ha-roomba-custom#readme).
