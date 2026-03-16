"""Sensors for Roomba Local.

Provides extra diagnostic sensors beyond what VacuumEntity exposes:
  - Battery percentage (mirroring BatteryLevel characteristic)
  - Mission duration in minutes
  - Area cleaned in square feet
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SIGNAL_CONNECTION_CHANGED, SIGNAL_STATE_UPDATED, RoombaData
from .const import CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: RoombaData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            RoombaBatterySensor(entry, data),
            RoombaMissionTimeSensor(entry, data),
            RoombaAreaSensor(entry, data),
        ]
    )


class _RoombaBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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


class RoombaBatterySensor(_RoombaBaseSensor):
    """Battery percentage — mirrors BatteryLevel + StatusLowBattery characteristics."""

    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = None  # show prominently

    def __init__(self, entry: ConfigEntry, data: RoombaData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_battery"

    @property
    def native_value(self) -> int | None:
        return self._data.state.get("batPct")

    @property
    def extra_state_attributes(self) -> dict:
        low_threshold = self._entry.options.get(
            CONF_LOW_BATTERY,
            self._entry.data.get(CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY),
        )
        phase = self._data.state.get("cleanMissionStatus", {}).get("phase", "")
        return {
            "charging": phase == "charge",
            "low_battery": (self.native_value or 100) <= low_threshold,
        }


class RoombaMissionTimeSensor(_RoombaBaseSensor):
    """Mission duration in minutes — mirrors mssnM from cleanMissionStatus."""

    _attr_name = "Mission Time"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, data: RoombaData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_mission_time"

    @property
    def native_value(self) -> int | None:
        return self._data.state.get("cleanMissionStatus", {}).get("mssnM")


class RoombaAreaSensor(_RoombaBaseSensor):
    """Area cleaned in square feet — mirrors sqft from cleanMissionStatus."""

    _attr_name = "Area Cleaned"
    _attr_native_unit_of_measurement = "sqft"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, data: RoombaData) -> None:
        super().__init__(entry, data)
        self._attr_unique_id = f"{entry.entry_id}_area_cleaned"

    @property
    def native_value(self) -> int | None:
        return self._data.state.get("cleanMissionStatus", {}).get("sqft")
