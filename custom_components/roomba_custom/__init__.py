"""Roomba Local — Home Assistant custom integration.

Ported from homebridge-iRobot-v2 v3.2.5-alpha.4 (taurgis/homebridge-iRobot-v2).
Connects directly to the Roomba on your LAN via MQTT/TLS with the same
cipher-rotation fix that makes older firmware models work with modern OpenSSL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_BLID,
    CONF_IP,
    CONF_PROTOCOL_VERSION,
    CONF_ROOMBA_PASSWORD,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    PLATFORMS,
)
from .roomba_mqtt import RoombaClient

_LOGGER = logging.getLogger(__name__)

SIGNAL_STATE_UPDATED = f"{DOMAIN}_state_updated_{{entry_id}}"
SIGNAL_CONNECTION_CHANGED = f"{DOMAIN}_connection_changed_{{entry_id}}"


# ---------------------------------------------------------------------------
# Runtime data stored on the config entry
# ---------------------------------------------------------------------------

@dataclass
class RoombaData:
    client: RoombaClient
    state: dict[str, Any] = field(default_factory=dict)
    connected: bool = False


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Roomba Local from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = RoombaClient(
        host=entry.data[CONF_IP],
        blid=entry.data[CONF_BLID],
        password=entry.data[CONF_ROOMBA_PASSWORD],
        protocol_version=entry.data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION),
    )

    data = RoombaData(client=client)
    hass.data[DOMAIN][entry.entry_id] = data

    def _on_state(state: dict) -> None:
        data.state = state
        async_dispatcher_send(
            hass, SIGNAL_STATE_UPDATED.format(entry_id=entry.entry_id)
        )

    def _on_connection(connected: bool) -> None:
        data.connected = connected
        async_dispatcher_send(
            hass, SIGNAL_CONNECTION_CHANGED.format(entry_id=entry.entry_id)
        )

    client.add_state_callback(_on_state)
    client.add_connection_callback(_on_connection)

    # Start the MQTT loop in the executor so it doesn't block the event loop.
    await hass.async_add_executor_job(client.start)

    async def _stop(_event) -> None:
        await hass.async_add_executor_job(client.stop)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data: RoombaData = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data.client.stop)
    return unload_ok
