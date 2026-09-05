"""
Roomba local MQTT client.

Key fix — 'Don't infinite loop on ciphers':
  ROBOT_CIPHERS = ['AES128-SHA256', 'TLS_AES_256_GCM_SHA384'].
  Index 0 is tried first. On a TLS error or 'identifier rejected' the cipher
  index is incremented once (bounded by list length) and the client
  reconnects. This prevents the infinite retry loop that older Roomba
  firmware causes with modern OpenSSL/Python.

  Implementation: build a custom ssl.SSLContext and call set_ciphers() with
  whichever cipher string is currently selected.

Reconnect flood protection:
  If the robot reconnects more than 5 times within 30 seconds, disconnect and
  wait 5 minutes before trying again.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
from collections.abc import Callable
from threading import Event, Thread
from typing import Any

import paho.mqtt.client as mqtt

from .const import (
    RECONNECT_BACKOFF_SECONDS,
    RECONNECT_FLOOD_COUNT,
    RECONNECT_FLOOD_WINDOW,
    ROBOT_CIPHERS,
    ROOMBA_MQTT_PORT,
)

_LOGGER = logging.getLogger(__name__)


def _build_ssl_context(cipher: str) -> ssl.SSLContext:
    """
    Build an SSL context for the given cipher string.

    Approach:
      - No certificate verification (Roomba uses a self-signed cert).
      - SECLEVEL=0 so that the older cipher suites the robot advertises are
        accepted without OpenSSL rejecting them.
      - OP_LEGACY_SERVER_CONNECT enables unsafe renegotiation on
        Python 3.12+ / OpenSSL 3 where it is disabled by default.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Try with SECLEVEL=0 first (needed for AES128-SHA256 on OpenSSL 3).
    # Fall back to the cipher string alone if the platform rejects SECLEVEL.
    for cipher_str in (f"{cipher}:@SECLEVEL=0", cipher, "DEFAULT@SECLEVEL=0"):
        try:
            ctx.set_ciphers(cipher_str)
            break
        except ssl.SSLError:
            continue

    # Allow legacy unsafe renegotiation — available Python 3.12+ / OpenSSL 3.
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT  # type: ignore[attr-defined]

    return ctx


def _should_try_different_cipher(error: Exception) -> bool:
    """
    Decide whether a connection error indicates a cipher mismatch.

    Returns True when the error looks like a TLS handshake failure or an
    MQTT 'identifier rejected' response — both indicate the robot rejected
    the current cipher and we should retry with the next one.
    """
    msg = str(error).lower()
    return "tls" in msg or "ssl" in msg or "identifier rejected" in msg


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _merge_state(base: dict, update: dict) -> dict:
    """Recursively merge *update* into *base* (in-place) and return base."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_state(base[key], value)
        else:
            base[key] = value
    return base


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class RoombaClient:
    """
    Local MQTT client for iRobot Roomba.

    Fires callbacks whenever the robot state changes. Handles cipher
    rotation and reconnect-flood protection.

    Usage:
        client = RoombaClient(host, blid, password)
        client.add_state_callback(my_callback)
        client.start()
        ...
        client.stop()
    """

    def __init__(
        self,
        host: str,
        blid: str,
        password: str,
        protocol_version: int = 2,
    ) -> None:
        self._host = host
        self._blid = blid
        self._password = password
        self._protocol_version = protocol_version

        self._cipher_index = 0
        self._client: mqtt.Client | None = None
        self._thread: Thread | None = None
        self._stop_event = Event()

        # Full merged robot state dict — updated on every MQTT message.
        self._state: dict[str, Any] = {}
        self._connected = False

        # Reconnect flood detection
        self._reconnect_timestamps: list[float] = []

        # Callbacks: called with the full state dict on every state update.
        self._state_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._connection_callbacks: list[Callable[[bool], None]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def add_state_callback(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self._state_callbacks.append(cb)

    def add_connection_callback(self, cb: Callable[[bool], None]) -> None:
        self._connection_callbacks.append(cb)

    def start(self) -> None:
        """Connect and start the background MQTT loop thread."""
        self._stop_event.clear()
        self._connect()

    def stop(self) -> None:
        """Disconnect and stop the background thread cleanly."""
        self._stop_event.set()
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client.loop_stop()
        _LOGGER.info("Roomba client stopped")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def clean(self) -> None:
        self._publish_command("start")

    def resume(self) -> None:
        self._publish_command("resume")

    def pause(self) -> None:
        self._publish_command("pause")

    def stop_cleaning(self) -> None:
        self._publish_command("stop")

    def dock(self) -> None:
        self._publish_command("dock")

    def find(self) -> None:
        self._publish_command("find")

    def evac(self) -> None:
        self._publish_command("evac")

    def clean_room(self, args: dict) -> None:
        """Start a room-by-room clean with the supplied pmap/region args."""
        payload = {
            "command": "start",
            "time": int(time.time()),
            "initiator": "localApp",
            **args,
        }
        self._publish("cmd", payload)

    # ------------------------------------------------------------------
    # Internal — connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """
        Create a new paho client and connect using the current cipher index.

        If the client already exists (e.g. retrying after cipher error) it is
        torn down cleanly first so we never hold two simultaneous connections
        to the robot (which only allows one).
        """
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client.loop_stop()
            self._client = None

        cipher = ROBOT_CIPHERS[self._cipher_index]
        _LOGGER.debug("Connecting to Roomba %s with cipher '%s'", self._host, cipher)

        client = mqtt.Client(
            client_id=self._blid,
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        client.username_pw_set(self._blid, self._password)
        client.tls_set_context(_build_ssl_context(cipher))

        client.on_connect    = self._on_connect
        client.on_message    = self._on_message
        client.on_disconnect = self._on_disconnect
        client.on_error      = self._on_error  # type: ignore[assignment]

        # Catch connection errors at the socket level (e.g. TLS handshake
        # failures that paho surfaces as exceptions rather than callbacks).
        try:
            client.connect(self._host, ROOMBA_MQTT_PORT, keepalive=60)
        except Exception as exc:
            self._handle_error(exc)
            return

        self._client = client
        client.loop_start()

    def _reconnect_after_delay(self, delay: float) -> None:
        """Schedule a reconnection attempt after *delay* seconds."""
        def _delayed():
            if not self._stop_event.is_set():
                _LOGGER.info("Attempting Roomba reconnection...")
                self._connect()

        t = Thread(target=lambda: (time.sleep(delay), _delayed()), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Internal — paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._connected = True
            _LOGGER.info("Connected to Roomba at %s", self._host)
            client.subscribe("#")
            self._notify_connection(True)
        elif rc == 2:
            # rc=2 → "identifier rejected" — try the other cipher.
            _LOGGER.warning("Roomba rejected client identifier (rc=2); trying next cipher")
            self._try_next_cipher()
        else:
            _LOGGER.warning("Roomba connection refused (rc=%s)", rc)
            self._connected = False
            self._notify_connection(False)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Roomba publishes state as shadow updates; the relevant fields live
        # under state.reported (AWS IoT shadow format).
        reported = None
        if isinstance(payload, dict):
            reported = (
                payload.get("state", {}).get("reported")
                or payload  # some firmware versions send flat payloads
            )

        if isinstance(reported, dict):
            _merge_state(self._state, reported)
            # Only fire callbacks when we have the minimum fields needed.
            if "cleanMissionStatus" in self._state:
                self._notify_state()

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        self._notify_connection(False)

        if self._stop_event.is_set():
            _LOGGER.info("Roomba disconnected (intentional shutdown)")
            return

        _LOGGER.warning("Roomba unexpectedly disconnected (rc=%s)", rc)

        # Reconnect flood protection:
        # if >5 reconnects in <=30 s, back off for 5 minutes.
        now = time.time()
        self._reconnect_timestamps.append(now)
        if len(self._reconnect_timestamps) > RECONNECT_FLOOD_COUNT:
            self._reconnect_timestamps.pop(0)

        if (
            len(self._reconnect_timestamps) == RECONNECT_FLOOD_COUNT
            and (self._reconnect_timestamps[-1] - self._reconnect_timestamps[0])
            <= RECONNECT_FLOOD_WINDOW
        ):
            _LOGGER.error(
                "Roomba has reconnected %d times in %d seconds — backing off for %d minutes. "
                "Check that no other app is connected to the robot at the same time.",
                RECONNECT_FLOOD_COUNT,
                RECONNECT_FLOOD_WINDOW,
                RECONNECT_BACKOFF_SECONDS // 60,
            )
            self._reconnect_timestamps.clear()
            self._reconnect_after_delay(RECONNECT_BACKOFF_SECONDS)
        else:
            self._reconnect_after_delay(10)

    def _on_error(self, client, userdata, error) -> None:
        self._handle_error(error)

    # ------------------------------------------------------------------
    # Internal — cipher rotation
    # ------------------------------------------------------------------

    def _handle_error(self, exc: Exception) -> None:
        """
        Decide whether to rotate cipher or just log.

        Rotates to the next cipher when the error looks like a cipher
        mismatch and there's still an untried cipher left in the list.
        """
        _LOGGER.error("Roomba error: %s", exc)

        if (
            _should_try_different_cipher(exc)
            and self._cipher_index < len(ROBOT_CIPHERS) - 1
        ):
            self._try_next_cipher()

    def _try_next_cipher(self) -> None:
        """Advance cipher index by one and reconnect (once only)."""
        self._cipher_index += 1
        new_cipher = ROBOT_CIPHERS[self._cipher_index]
        _LOGGER.warning("Switching to cipher '%s' and reconnecting", new_cipher)
        if not self._stop_event.is_set():
            self._connect()

    # ------------------------------------------------------------------
    # Internal — publishing
    # ------------------------------------------------------------------

    def _publish_command(self, command: str) -> None:
        payload = {
            "command": command,
            "time": int(time.time()),
            "initiator": "localApp",
        }
        self._publish("cmd", payload)

    def _publish(self, topic: str, payload: dict) -> None:
        if self._client and self._connected:
            self._client.publish(topic, json.dumps(payload))
        else:
            _LOGGER.warning("Cannot send '%s' — not connected to Roomba", topic)

    # ------------------------------------------------------------------
    # Internal — notifications
    # ------------------------------------------------------------------

    def _notify_state(self) -> None:
        for cb in self._state_callbacks:
            try:
                cb(dict(self._state))
            except Exception:
                _LOGGER.exception("Error in Roomba state callback")

    def _notify_connection(self, connected: bool) -> None:
        for cb in self._connection_callbacks:
            try:
                cb(connected)
            except Exception:
                _LOGGER.exception("Error in Roomba connection callback")
