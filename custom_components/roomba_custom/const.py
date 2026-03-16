"""Constants for the Roomba Local integration."""

DOMAIN = "roomba_custom"

# Config entry keys
CONF_BLID = "blid"
CONF_ROOMBA_PASSWORD = "roomba_password"
CONF_IP = "ip"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_LOW_BATTERY = "low_battery"
CONF_OFF_ACTION = "off_action"
CONF_HIDE_STUCK_SENSOR = "hide_stuck_sensor"
CONF_HIDE_BIN_SENSOR = "hide_bin_sensor"

# Defaults
DEFAULT_LOW_BATTERY = 20
DEFAULT_OFF_ACTION = "pause_dock"
DEFAULT_PROTOCOL_VERSION = 2

# MQTT
ROOMBA_MQTT_PORT = 8883

# Cipher list — ported directly from homebridge-iRobot-v2 v3.2.5-alpha.4
# Index 0 is tried first; on TLS / "identifier rejected" errors we fall back
# to index 1. This is the fix for "Don't infinite loop on ciphers".
ROBOT_CIPHERS = ["AES128-SHA256", "TLS_AES_256_GCM_SHA384"]

# How many reconnects within this window triggers a back-off (30 s, 5 reconnects)
RECONNECT_FLOOD_COUNT = 5
RECONNECT_FLOOD_WINDOW = 30  # seconds
RECONNECT_BACKOFF_SECONDS = 300  # 5 minutes

# Phase → HA VacuumActivity mapping  (mirrors platformAccessory.ts logic)
PHASE_MAP = {
    "charge":     "docked",
    "recharge":   "docked",
    "stop":       "idle",
    "stuck":      "error",
    "run":        "cleaning",
    "hmUsrDock":  "returning",
    "hmMidMsn":   "returning",
    "hmPostMsn":  "returning",
    "pause":      "paused",
    "evac":       "cleaning",
}

# Off-action options (matches config.schema.json offAction)
OFF_ACTIONS = {
    "pause_dock":  ("pause", "dock"),
    "stop_dock":   ("stop",  "dock"),
    "pause_find":  ("pause", "find"),
    "stop_find":   ("stop",  "find"),
    "pause":       ("pause", None),
    "stop":        ("stop",  None),
}

# Platforms
PLATFORMS = ["vacuum", "binary_sensor", "sensor"]
