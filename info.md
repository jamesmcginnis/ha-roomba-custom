# Roomba Custom (Legacy TLS)

Local network control for iRobot Roomba — ported from homebridge-iRobot-v2 with the cipher fix that makes older firmware work with modern Home Assistant.

![Roomba Custom dashboard card showing robot status, battery level, and controls](preview1.png)

## What's included

- **Automatic setup** — sign in with your iRobot email and password, Roomba found automatically
- **Local push** — connects directly over your LAN via MQTT/TLS, no cloud polling
- **Full control** — start, pause, stop, dock, locate, room-by-room cleaning
- **Sensors** — battery level, bin full, stuck detection, mission time, area cleaned
- **Dashboard card** — custom Lovelace card with live status and controls

![Setup wizard showing iRobot account sign-in and automatic robot discovery](preview2.png)

## Why not the built-in integration?

Certain Roomba firmware versions reject the TLS cipher that modern Python/OpenSSL offers by default, causing the connection to fail silently. This integration tries two cipher strings in sequence and automatically switches if the first is rejected — the exact fix from homebridge-iRobot-v2 v3.2.5-alpha.4.

![Entities created in Home Assistant including vacuum, sensors, and binary sensors](preview3.png)

## Compatible models

600, 800, 900, e, i, j, s series · Braava m6 · Roomba Combo including Y0 series

---

For full documentation see the [README](https://github.com/jamesmcginnis/ha-roomba-custom#readme).
