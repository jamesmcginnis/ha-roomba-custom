"""Vacuum platform for Roomba Local.

Ported from iRobotPlatformAccessory in homebridge-iRobot-v2 v3.2.5-alpha.4.

State mapping (mirrors getHomekitActive / platformAccessory phase logic):
  phase=run          → cleaning
  cycle=evac         → cleaning
  phase=charge       → docked
  phase=recharge     → docked
  phase=hmUsrDock /
  phase=hmMidMsn /
  phase=hmPostMsn    → returning
  phase=pause        → paused
  phase=stop         → idle
  phase=stuck        → error

Off-action (mirrors config offAction):
  first_action()  → e.g. pause()  (sent immediately)
  second_action() → e.g. dock()   (sent after state settles, up to 5 s)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SIGNAL_CONNECTION_CHANGED, SIGNAL_STATE_UPDATED, RoombaData
from .const import (
    CONF_HIDE_BIN_SENSOR,
    CONF_LOW_BATTERY,
    CONF_OFF_ACTION,
    DEFAULT_LOW_BATTERY,
    DEFAULT_OFF_ACTION,
    DOMAIN,
    OFF_ACTIONS,
    PHASE_MAP,
)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    VacuumEntityFeature.START
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.BATTERY
    | VacuumEntityFeature.STATE
    | VacuumEntityFeature.SEND_COMMAND
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: RoombaData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RoombaVacuum(hass, entry, data)])


class RoombaVacuum(StateVacuumEntity):
    """Representation of a Roomba vacuum.

    Exposes all state and commands that the Homebridge plugin provided,
    translated into Home Assistant's VacuumEntity interface.
    """

    _attr_has_entity_name = True
    _attr_name = None  # uses device name
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        data: RoombaData,
    ) -> None:
        self._entry = entry
        self._data = data
        self._client = data.client

        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="iRobot",
        )

        self._state: dict[str, Any] = {}
        self._connected = False
        self._starting = False  # mirrors `starting` flag in platformAccessory.ts

    # ------------------------------------------------------------------
    # HA lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        # FIX 1: Seed local state from the shared data object immediately on
        # registration. The MQTT client may have already connected and fired
        # callbacks before this entity subscribed to the dispatcher signals,
        # leaving self._connected stuck at False and all controls greyed out.
        self._connected = self._data.connected
        self._state = self._data.state

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_UPDATED.format(entry_id=self._entry.entry_id),
                self._handle_state_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION_CHANGED.format(entry_id=self._entry.entry_id),
                self._handle_connection_change,
            )
        )

    @callback
    def _handle_state_update(self) -> None:
        self._state = self._data.state
        self.async_write_ha_state()

    @callback
    def _handle_connection_change(self) -> None:
        self._connected = self._data.connected
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._connected

    @property
    def activity(self) -> VacuumActivity | None:
        cms = self._state.get("cleanMissionStatus", {})
        phase = cms.get("phase", "")
        cycle = cms.get("cycle", "")

        # cycle=evac wins over phase for identifying evacuation runs
        if cycle == "evac":
            return VacuumActivity.CLEANING

        ha_state = PHASE_MAP.get(phase)
        if ha_state == "cleaning":
            return VacuumActivity.CLEANING
        if ha_state == "docked":
            return VacuumActivity.DOCKED
        if ha_state == "returning":
            return VacuumActivity.RETURNING
        if ha_state == "paused":
            return VacuumActivity.PAUSED
        if ha_state == "idle":
            return VacuumActivity.IDLE
        if ha_state == "error":
            return VacuumActivity.ERROR

        # FIX 2: Return IDLE instead of None when the phase is unrecognised or
        # the first state update hasn't arrived yet. Returning None causes HA to
        # treat the entity as fully unknown and disables all controls including
        # the on/off toggle, even when the robot is connected and ready.
        return VacuumActivity.IDLE

    @property
    def battery_level(self) -> int | None:
        return self._state.get("batPct")

    @property
    def battery_icon(self) -> str:
        low_threshold = self._entry.options.get(
            CONF_LOW_BATTERY,
            self._entry.data.get(CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY),
        )
        level = self.battery_level or 0
        charging = self._state.get("cleanMissionStatus", {}).get("phase") == "charge"
        if charging:
            return "mdi:battery-charging"
        if level <= low_threshold:
            return "mdi:battery-alert"
        return "mdi:battery"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cms = self._state.get("cleanMissionStatus", {})
        return {
            "cycle": cms.get("cycle"),
            "phase": cms.get("phase"),
            "error_code": cms.get("error", 0),
            "not_ready_code": cms.get("notReady", 0),
            "mission_minutes": cms.get("mssnM", 0),
            "sqft_cleaned": cms.get("sqft", 0),
            "bin_full": self._state.get("bin", {}).get("full", False),
            "last_command": self._state.get("lastCommand", {}).get("command"),
        }

    # ------------------------------------------------------------------
    # Commands — mirrors set() and related methods in platformAccessory.ts
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Start cleaning. Mirrors set(value=1) in platformAccessory.ts."""
        if self._starting:
            _LOGGER.info("Roomba is already starting a cycle, skipping")
            return

        self._starting = True
        # Small delay to let automations/scenes settle (mirrors setTimeout 0ms
        # for non-multi-room mode in the Homebridge plugin).
        await asyncio.sleep(0)
        try:
            await self.hass.async_add_executor_job(self._client.clean)
            await self.hass.async_add_executor_job(self._client.resume)
        finally:
            self._starting = False

    async def async_pause(self) -> None:
        await self.hass.async_add_executor_job(self._client.pause)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop and perform the configured off-action.

        Mirrors set(value=0) in platformAccessory.ts: fire first action
        immediately, then wait up to 5 s for a state update before firing
        the second action.
        """
        off_action_key = self._entry.options.get(
            CONF_OFF_ACTION,
            self._entry.data.get(CONF_OFF_ACTION, DEFAULT_OFF_ACTION),
        )
        first, second = OFF_ACTIONS.get(off_action_key, ("pause", "dock"))

        cmd1 = getattr(self._client, first if first != "stop" else "stop_cleaning", None)
        if cmd1:
            await self.hass.async_add_executor_job(cmd1)

        if second:
            # Wait up to 5 s for the robot state to settle, then send second command.
            await asyncio.sleep(5)
            cmd2 = getattr(self._client, second, None)
            if cmd2:
                await self.hass.async_add_executor_job(cmd2)

        self._starting = False

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._client.dock)

    async def async_locate(self, **kwargs: Any) -> None:
        """Make the robot beep. Mirrors identify() in platformAccessory.ts."""
        await self.hass.async_add_executor_job(self._client.find)

    async def async_send_command(
        self,
        command: str,
        params: dict[str, Any] | list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Send a raw command to the robot.

        Supports:
          clean_room  — params must include pmap_id, user_pmapv_id, regions list
          evac        — trigger evacuation/emptying
          any dorita980 command name
        """
        if command == "clean_room" and isinstance(params, dict):
            await self.hass.async_add_executor_job(
                self._client.clean_room, params
            )
        elif command == "evac":
            await self.hass.async_add_executor_job(self._client.evac)
        else:
            cmd = getattr(self._client, command, None)
            if cmd:
                await self.hass.async_add_executor_job(cmd)
            else:
                _LOGGER.warning("Unknown Roomba command: %s", command)
