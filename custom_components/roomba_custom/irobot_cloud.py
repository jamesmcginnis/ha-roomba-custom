"""
iRobot cloud discovery:
  - Gigya login → iRobot API for account authentication
  - UDP broadcast discovery for finding the robot's local IP
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

GIGYA_API_KEY = "3_rWtvxmUKwgOzu3AUPTMLnM46lj-LxURGflmu5PcE_sGptTbD-wMeshVbLvYpq01K"
GIGYA_URL     = "https://accounts.us1.gigya.com/accounts.login"
IROBOT_APP_ID = "ANDROID-C7FB240E-DF34-42D7-AE4E-A8C17079A294"

IROBOT_LOGIN_URLS = [
    "https://unauth1.prod.iot.irobotapi.com/v2/login",
    "https://unauth2.prod.iot.irobotapi.com/v2/login",
]

DISCOVERY_PORT    = 5678
DISCOVERY_MESSAGE = b"irobotmcs"
DISCOVERY_TIMEOUT = 5.0
DISCOVERY_RETRIES = 3


@dataclass
class DiscoveredRobot:
    name:     str
    blid:     str
    password: str
    ip:       str
    model:    str = ""
    sku:      str = ""


class CloudAuthError(Exception):
    """Raised when Gigya or iRobot login fails."""


# ---------------------------------------------------------------------------
# Step 1 — Gigya login
# ---------------------------------------------------------------------------

async def _gigya_login(session: aiohttp.ClientSession, email: str, password: str) -> dict:
    """POST to Gigya accounts.login."""
    params = {
        "apiKey":     GIGYA_API_KEY,
        "targetenv":  "mobile",
        "loginID":    email,
        "password":   password,
        "format":     "json",
        "targetEnv":  "mobile",
    }

    try:
        async with session.post(GIGYA_URL, params=params) as resp:
            if resp.status in (401, 403):
                raise CloudAuthError("invalid_credentials")
            if resp.status == 400:
                raise CloudAuthError("bad_request")
            if resp.status != 200:
                raise CloudAuthError(f"gigya_http_{resp.status}")
            body = await resp.json(content_type=None)
    except CloudAuthError:
        raise
    except Exception as exc:
        raise CloudAuthError("gigya_connection_failed") from exc

    if body.get("statusCode") in (400, 403):
        raise CloudAuthError("invalid_credentials")
    if body.get("errorCode", 0) != 0:
        raise CloudAuthError(f"gigya_error_{body.get('errorCode')}")

    required = ("UID", "UIDSignature", "signatureTimestamp", "sessionInfo")
    if not all(body.get(k) for k in required):
        raise CloudAuthError("gigya_missing_fields")

    _LOGGER.debug("Gigya login OK for %s", email)
    return body


# ---------------------------------------------------------------------------
# Step 2 — iRobot /v2/login
# ---------------------------------------------------------------------------

async def _irobot_login(session: aiohttp.ClientSession, gigya_body: dict) -> dict[str, Any]:
    """POST to iRobot unauth server to complete login."""
    payload = {
        "app_id":                 IROBOT_APP_ID,
        "assume_robot_ownership": 0,
        "gigya": {
            "signature":  gigya_body["UIDSignature"],
            "timestamp":  gigya_body["signatureTimestamp"],
            "uid":        gigya_body["UID"],
        },
    }

    last_error: Exception | None = None
    for url in IROBOT_LOGIN_URLS:
        try:
            async with session.post(url, json=payload) as resp:
                body = await resp.json(content_type=None)
            if "robots" in body:
                _LOGGER.debug("iRobot login OK via %s — %d robot(s)", url, len(body["robots"]))
                return body["robots"]
            _LOGGER.debug("iRobot login: no robots key in response from %s: %s", url, body)
        except Exception as exc:
            last_error = exc
            _LOGGER.debug("iRobot login failed on %s: %s", url, exc)

    raise CloudAuthError("irobot_login_failed") from last_error


# ---------------------------------------------------------------------------
# Step 3 — UDP IP discovery
# ---------------------------------------------------------------------------

async def _discover_ip(blid: str) -> str | None:
    """
    Send 'irobotmcs' UDP broadcast and listen for the robot's reply.

    Uses allow_broadcast=True on the datagram endpoint. Without this flag
    the broadcast send fails silently on most OS/network configurations and
    no response is ever received.
    """
    # Use get_running_loop() — get_event_loop() is deprecated in Python 3.10+
    loop = asyncio.get_running_loop()

    for attempt in range(1, DISCOVERY_RETRIES + 1):
        _LOGGER.debug("UDP discovery attempt %d/%d for blid %s", attempt, DISCOVERY_RETRIES, blid)

        found_ip: str | None = None
        event    = asyncio.Event()

        class _Protocol(asyncio.DatagramProtocol):
            def datagram_received(self, data: bytes, addr: tuple) -> None:
                nonlocal found_ip
                try:
                    msg      = json.loads(data.decode("utf-8", errors="replace"))
                    hostname = msg.get("hostname", "")
                    parts    = hostname.split("-")
                    if (
                        len(parts) >= 2
                        and parts[0] in ("Roomba", "iRobot")
                        and parts[1] == blid
                        and msg.get("ip")
                    ):
                        found_ip = msg["ip"]
                        event.set()
                except Exception:
                    pass

            def error_received(self, exc: Exception) -> None:
                _LOGGER.debug("UDP error_received: %s", exc)

        try:
            transport, _ = await loop.create_datagram_endpoint(
                _Protocol,
                family=socket.AF_INET,
                allow_broadcast=True,   # FIX: required for broadcast to work
            )
            try:
                transport.sendto(DISCOVERY_MESSAGE, ("<broadcast>", DISCOVERY_PORT))
                await asyncio.wait_for(event.wait(), timeout=DISCOVERY_TIMEOUT)
            except asyncio.TimeoutError:
                pass
            finally:
                transport.close()

            if found_ip:
                _LOGGER.debug("UDP found blid %s at %s", blid, found_ip)
                return found_ip

        except Exception as exc:
            _LOGGER.debug("UDP attempt %d failed: %s", attempt, exc)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def discover_robots(email: str, password: str) -> list[DiscoveredRobot]:
    """
    Full cloud + local discovery flow.

    This is a native coroutine — call it with `await discover_robots(...)`.
    Do NOT wrap it in run_until_complete() or async_add_executor_job().
    """
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        gigya_body = await _gigya_login(session, email, password)
        robots_raw = await _irobot_login(session, gigya_body)

    robots: list[DiscoveredRobot] = []

    for blid, info in robots_raw.items():
        name     = info.get("name") or f"Roomba ({blid[:6]})"
        password = info.get("password", "")

        ip = info.get("ip") or ""
        if not ip:
            _LOGGER.info("No cloud IP for '%s' — trying UDP broadcast discovery", name)
            ip = await _discover_ip(blid) or ""

        if not ip:
            _LOGGER.warning("Could not find IP for '%s' — user will need to enter it manually", name)

        robots.append(DiscoveredRobot(
            name=name, blid=blid, password=password, ip=ip,
            sku=info.get("sku", ""),
        ))
        _LOGGER.info("Robot: name=%s  blid=%s  ip=%s", name, blid, ip or "not found")

    return robots
