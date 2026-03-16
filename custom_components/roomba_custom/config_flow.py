"""
Config flow for Roomba Custom.

Step flow mirrors the Homebridge plugin's setup exactly:

  Path A — Cloud (like Homebridge):
    user → cloud (email + password) → pick (if multiple robots) → done

  Path B — Manual (for users who don't want to use cloud credentials):
    user → manual (IP + BLID + password) → done

The cloud path logs into Gigya and the iRobot API to auto-discover all your
robots — same approach as getRoombaCredentials.js in homebridge-iRobot-v2.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_BLID,
    CONF_HIDE_BIN_SENSOR,
    CONF_HIDE_STUCK_SENSOR,
    CONF_IP,
    CONF_LOW_BATTERY,
    CONF_OFF_ACTION,
    CONF_PROTOCOL_VERSION,
    CONF_ROOMBA_PASSWORD,
    DEFAULT_LOW_BATTERY,
    DEFAULT_OFF_ACTION,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    OFF_ACTIONS,
)
from .irobot_cloud import CloudAuthError, DiscoveredRobot, discover_robots
from .roomba_mqtt import RoombaClient

_LOGGER = logging.getLogger(__name__)

# Extra config-flow-only keys (not stored in entry data)
CONF_IROBOT_EMAIL    = "irobot_email"
CONF_IROBOT_PASSWORD = "irobot_password"
CONF_SETUP_MODE      = "setup_mode"

SETUP_MODE_CLOUD  = "cloud"
SETUP_MODE_MANUAL = "manual"


class RoombaCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Multi-step config flow.

    Step 1  — choose cloud or manual
    Step 2a — cloud: enter iRobot email + password
    Step 2b — pick: if multiple robots found, choose one
    Step 2c — manual: enter IP, BLID, password
    """

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_robots: list[DiscoveredRobot] = []
        self._selected_robot: DiscoveredRobot | None = None

    # ------------------------------------------------------------------
    # Step 1 — choose setup mode
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """First screen — cloud vs manual."""
        if user_input is not None:
            if user_input[CONF_SETUP_MODE] == SETUP_MODE_CLOUD:
                return await self.async_step_cloud()
            return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SETUP_MODE, default=SETUP_MODE_CLOUD): vol.In({
                    SETUP_MODE_CLOUD:  "Sign in with iRobot account (recommended — finds your Roomba automatically)",
                    SETUP_MODE_MANUAL: "Enter credentials manually (IP address, BLID and local password)",
                }),
            }),
            description_placeholders={},
        )

    # ------------------------------------------------------------------
    # Step 2a — cloud login (email + password)
    # ------------------------------------------------------------------

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """
        Mirrors the Homebridge plugin's email + password login.
        Calls Gigya → iRobot cloud → UDP discovery automatically.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            email    = user_input[CONF_IROBOT_EMAIL].strip()
            password = user_input[CONF_IROBOT_PASSWORD]

            try:
                robots = await self.hass.async_add_executor_job(
                    lambda: self.hass.loop.run_until_complete(
                        discover_robots(email, password)
                    )
                )
            except CloudAuthError as exc:
                err = str(exc)
                if "invalid_credentials" in err:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cloud_error"
                _LOGGER.warning("Cloud discovery error: %s", exc)
                robots = []
            except Exception as exc:
                _LOGGER.exception("Unexpected cloud error: %s", exc)
                errors["base"] = "cloud_error"
                robots = []

            if robots and not errors:
                self._discovered_robots = robots

                if len(robots) == 1:
                    # Only one robot — skip the picker
                    self._selected_robot = robots[0]
                    return await self._create_or_confirm()

                # Multiple robots — show picker
                return await self.async_step_pick()

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema({
                vol.Required(CONF_IROBOT_EMAIL): str,
                vol.Required(CONF_IROBOT_PASSWORD): str,
            }),
            errors=errors,
            description_placeholders={},
        )

    # ------------------------------------------------------------------
    # Step 2b — pick robot (if account has multiple)
    # ------------------------------------------------------------------

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Let the user choose which robot to set up (multi-robot accounts)."""
        if user_input is not None:
            blid = user_input["robot"]
            self._selected_robot = next(
                (r for r in self._discovered_robots if r.blid == blid), None
            )
            if self._selected_robot:
                return await self._create_or_confirm()

        robot_options = {
            r.blid: f"{r.name}  ({r.ip or 'IP unknown'})"
            for r in self._discovered_robots
        }

        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema({
                vol.Required("robot"): vol.In(robot_options),
            }),
            description_placeholders={
                "count": str(len(self._discovered_robots)),
            },
        )

    # ------------------------------------------------------------------
    # Step 2c — manual entry (IP + BLID + local password)
    # ------------------------------------------------------------------

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manual credential entry — identical to the previous single-step flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            valid = await self._test_connection(
                host             = user_input[CONF_IP],
                blid             = user_input[CONF_BLID],
                password         = user_input[CONF_ROOMBA_PASSWORD],
                protocol_version = user_input.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION),
            )
            if valid:
                await self.async_set_unique_id(user_input[CONF_BLID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Roomba ({user_input[CONF_IP]})",
                    data={
                        **user_input,
                        CONF_LOW_BATTERY:     DEFAULT_LOW_BATTERY,
                        CONF_OFF_ACTION:      DEFAULT_OFF_ACTION,
                        CONF_HIDE_STUCK_SENSOR: False,
                        CONF_HIDE_BIN_SENSOR:   False,
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_IP):              str,
                vol.Required(CONF_BLID):            str,
                vol.Required(CONF_ROOMBA_PASSWORD): str,
                vol.Optional(CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION):
                    vol.In([1, 2, 3]),
            }),
            errors=errors,
            description_placeholders={
                "help_url": "https://github.com/jamesmcginnis/ha-roomba-custom#getting-your-credentials",
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_or_confirm(self) -> config_entries.FlowResult:
        """
        Create the config entry from a discovered robot.
        If the IP is missing (robot not on network right now), drop to manual
        entry pre-filled with the known BLID and password.
        """
        robot = self._selected_robot
        if not robot:
            return await self.async_step_manual()

        await self.async_set_unique_id(robot.blid)
        self._abort_if_unique_id_configured()

        # If we got an IP from cloud/UDP, create the entry straight away
        if robot.ip:
            return self.async_create_entry(
                title=robot.name,
                data={
                    CONF_IP:               robot.ip,
                    CONF_BLID:             robot.blid,
                    CONF_ROOMBA_PASSWORD:  robot.password,
                    CONF_PROTOCOL_VERSION: DEFAULT_PROTOCOL_VERSION,
                    CONF_LOW_BATTERY:      DEFAULT_LOW_BATTERY,
                    CONF_OFF_ACTION:       DEFAULT_OFF_ACTION,
                    CONF_HIDE_STUCK_SENSOR: False,
                    CONF_HIDE_BIN_SENSOR:   False,
                },
            )

        # No IP found — show manual form pre-filled with BLID + password
        _LOGGER.warning(
            "Could not auto-discover IP for %s — asking user to enter it", robot.name
        )
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_IP):              str,
                vol.Required(CONF_BLID,    default=robot.blid):     str,
                vol.Required(CONF_ROOMBA_PASSWORD, default=robot.password): str,
                vol.Optional(CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION):
                    vol.In([1, 2, 3]),
            }),
            errors={},
            description_placeholders={
                "help_url": "https://github.com/jamesmcginnis/ha-roomba-custom#getting-your-credentials",
            },
        )

    async def _test_connection(
        self,
        host: str,
        blid: str,
        password: str,
        protocol_version: int,
    ) -> bool:
        """Quick connection test to validate manual credentials."""
        import asyncio
        connected = asyncio.Event()
        client    = RoombaClient(host, blid, password, protocol_version)

        def _on_conn(is_connected: bool) -> None:
            if is_connected:
                connected.set()

        client.add_connection_callback(_on_conn)
        try:
            await self.hass.async_add_executor_job(client.start)
            try:
                await asyncio.wait_for(connected.wait(), timeout=15)
                return True
            except asyncio.TimeoutError:
                _LOGGER.warning("Timed out connecting to Roomba at %s", host)
                return False
        except Exception as exc:
            _LOGGER.error("Connection test failed: %s", exc)
            return False
        finally:
            await self.hass.async_add_executor_job(client.stop)

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RoombaCustomOptionsFlow:
        return RoombaCustomOptionsFlow(config_entry)


class RoombaCustomOptionsFlow(config_entries.OptionsFlow):
    """Options flow — shown when user clicks Configure on the integration card."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options or self._config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_LOW_BATTERY,
                    default=current.get(CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY),
                ): vol.All(int, vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_OFF_ACTION,
                    default=current.get(CONF_OFF_ACTION, DEFAULT_OFF_ACTION),
                ): vol.In(list(OFF_ACTIONS.keys())),
                vol.Optional(
                    CONF_HIDE_STUCK_SENSOR,
                    default=current.get(CONF_HIDE_STUCK_SENSOR, False),
                ): bool,
                vol.Optional(
                    CONF_HIDE_BIN_SENSOR,
                    default=current.get(CONF_HIDE_BIN_SENSOR, False),
                ): bool,
            }),
        )
