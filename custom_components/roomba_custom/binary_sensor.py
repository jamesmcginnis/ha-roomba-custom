"""Binary sensors for Roomba Local.

  - Bin Full   — on when the robot reports the bin is full
  - Stuck      — on when the robot reports it is stuck (configurable via
                 the "Hide Stuck sensor" option)
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SIGNAL_CONNECTION_CHANGED, SIGNAL_STATE_UPDATED, RoombaData
from .const import CONF_HIDE_BIN_SENSOR, CONF_HIDE_STUCK_SENSOR, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: RoombaData = hass.data[DOMAIN][entry.entry_id]
    entities = []

    if not entry.data.get(CONF_HIDE_BIN_SENSOR, False):
        entities.append(RoombaBinSensor(entry, data))

    if not entry.data.get(CONF_HIDE_STUCK_SENSOR, False):
        entities.append(RoombaStuckSensor(entry, data))

    async_add_entities(entities)


class _RoombaBaseSensor(BinarySensorEntity):
    """Shared base for Roomba binary sensors."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, data: RoombaData) -> None:
        self._entry = entry
        self._data = data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="iRobot",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_UPDATED.format(entry_id=self._entry.entry_id),
                self._on_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION_CHANGED.format(entry_id=self._entry.entry_id),
                self._on_update,
            )
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._data.connected


class RoombaBinSensor(_RoombaBaseSensor):
    """
    Bin-full sensor.

    A single binary_sensor with device_class=problem covers all cases.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Bin Full"

    def __init__(self, entry: ConfigEntry, data: RoombaData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_bin_full"

    @property
    def is_on(self) -> bool:
        return bool(self._data.state.get("bin", {}).get("full", False))


class RoombaStuckSensor(_RoombaBaseSensor):
    """
    Stuck sensor.

    Fires when phase == 'stuck'.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Stuck"

    def __init__(self, entry: ConfigEntry, data: RoombaData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_stuck"

    @property
    def is_on(self) -> bool:
        phase = self._data.state.get("cleanMissionStatus", {}).get("phase", "")
        return phase == "stuck"
