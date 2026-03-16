"""
iRobot cloud discovery — Python port of:
  - src/scripts/getRoombaCredentials.js  (Gigya login → iRobot API)
  - src/scripts/getRoombaIP.js           (UDP broadcast discovery)

from homebridge-iRobot-v2 v3.2.5-alpha.4 (taurgis/homebridge-iRobot-v2)

Flow (mirrors the Homebridge scripts exactly):
  1. POST to Gigya accounts.login  →  get UID + UIDSignature + sessionToken
  2. POST to iRobot /v2/login      →  get robot list with blid, password, name
  3. UDP broadcast 'irobotmcs' on port 5678  →  get each robot's current IP

All credentials stay on your local network after step 2 — the IP discovery
in step 3 is purely local and requires no internet.
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

# --- Constants ported directly from getRoombaCredentials.js ---
GIGYA_API_KEY = "3_rWtvxmUKwgOzu3AUPTMLnM46lj-LxURGflmu5PcE_sGptTbD-wMeshVbLvYpq01K"
GIGYA_URL     = "https://accounts.us1.gigya.com/accounts.login"
IROBOT_APP_ID = "ANDROID-C7FB240E-DF34-42D7-AE4E-A8C17079A294"

# iRobot tries server 1 then falls back to server 2 (mirrors loginToIRobot)
IROBOT_LOGIN_URLS = [
    "https://unauth1.prod.iot.irobotapi.com/v2/login",
    "https://unauth2.prod.iot.irobotapi.com/v2/login",
]

# UDP discovery (mirrors getRoombaIP.js)
DISCOVERY_PORT    = 5678
DISCOVERY_MESSAGE = b"irobotmcs"
DISCOVERY_TIMEOUT = 5.0   # seconds per attempt
DISCOVERY_RETRIES = 5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

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


class RobotNotFoundError(Exception):
    """Raised when UDP discovery cannot locate a robot."""


# ---------------------------------------------------------------------------
# Step 1 — Gigya login
# ---------------------------------------------------------------------------

async def _gigya_login(session: aiohttp.ClientSession, email: str, password: str) -> dict:
    """
    POST to Gigya accounts.login.
    Mirrors gigyaLoginOptions + loginGigyaResponseHandler in getRoombaCredentials.js
    """
    params = {
        "apiKey":          GIGYA_API_KEY,
        "targetenv":       "mobile",
        "loginID":         email,
        "password":        password,
        "format":          "json",
        "targetEnv":       "mobile",
    }

    async with session.post(GIGYA_URL, params=params) as resp:
        if resp.status in (401, 403):
            raise CloudAuthError("invalid_credentials")
        if resp.status == 400:
            raise CloudAuthError("bad_request")
        if resp.status != 200:
            raise CloudAuthError(f"gigya_error_{resp.status}")

        body = await resp.json(content_type=None)

    if body.get("statusCode") == 403:
        raise CloudAuthError("invalid_credentials")
    if body.get("statusCode") == 400 or body.get("errorCode", 0) != 0:
        raise CloudAuthError("gigya_error")

    required = ("UID", "UIDSignature", "signatureTimestamp", "sessionInfo")
    if not all(body.get(k) for k in required):
        raise CloudAuthError("gigya_missing_fields")

    _LOGGER.debug("Gigya login successful for %s", email)
    return body


# ---------------------------------------------------------------------------
# Step 2 — iRobot /v2/login
# ---------------------------------------------------------------------------

async def _irobot_login(session: aiohttp.ClientSession, gigya_body: dict) -> dict[str, Any]:
    """
    POST to iRobot unauth server.
    Mirrors loginToIRobot + loginIrobotResponseHandler in getRoombaCredentials.js
    Falls back from server 1 → server 2 exactly as the JS does.
    """
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
                _LOGGER.debug("iRobot login OK via %s, found %d robot(s)", url, len(body["robots"]))
                return body["robots"]
        except Exception as exc:
            last_error = exc
            _LOGGER.debug("iRobot login failed on %s: %s — trying next server", url, exc)

    raise CloudAuthError("irobot_login_failed") from last_error


# ---------------------------------------------------------------------------
# Step 3 — UDP IP discovery
# ---------------------------------------------------------------------------

async def _discover_ip(blid: str) -> str | None:
    """
    Send 'irobotmcs' UDP broadcast and listen for the robot's announcement.
    Mirrors getRoombaIP.js — same port (5678), same message, same hostname check.

    Returns the IP string, or None if not found within timeout.
    """
    loop = asyncio.get_event_loop()

    for attempt in range(1, DISCOVERY_RETRIES + 1):
        _LOGGER.debug("UDP discovery attempt %d/%d for blid %s", attempt, DISCOVERY_RETRIES, blid)

        found_ip: str | None = None
        event = asyncio.Event()

        class _Protocol(asyncio.DatagramProtocol):
            def datagram_received(self, data: bytes, addr: tuple) -> None:
                nonlocal found_ip
                try:
                    msg = json.loads(data.decode("utf-8", errors="replace"))
                    hostname: str = msg.get("hostname", "")
                    # mirrors: hostname.split('-')[0] === 'Roomba' || 'iRobot'
                    #      and: hostname.split('-')[1] === blid
                    parts = hostname.split("-")
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

        try:
            transport, _ = await loop.create_datagram_endpoint(
                _Protocol,
                family=socket.AF_INET,
            )
            transport.sendto(DISCOVERY_MESSAGE, ("<broadcast>", DISCOVERY_PORT))

            try:
                await asyncio.wait_for(event.wait(), timeout=DISCOVERY_TIMEOUT)
            except asyncio.TimeoutError:
                pass
            finally:
                transport.close()

            if found_ip:
                _LOGGER.debug("Found %s at %s", blid, found_ip)
                return found_ip

        except Exception as exc:
            _LOGGER.debug("UDP error on attempt %d: %s", attempt, exc)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def discover_robots(email: str, password: str) -> list[DiscoveredRobot]:
    """
    Full discovery flow mirroring the Homebridge plugin's getRoombas():
      1. Gigya login with iRobot email + password
      2. iRobot cloud API to get robot list (blid, password, name)
      3. UDP broadcast to find each robot's current IP on the LAN

    Returns a list of DiscoveredRobot dataclasses ready to use in the config flow.
    Raises CloudAuthError on login failure.
    """
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Step 1 & 2 — cloud auth
        gigya_body   = await _gigya_login(session, email, password)
        robots_raw   = await _irobot_login(session, gigya_body)

    # robots_raw is a dict keyed by blid:
    #   { "blid123": { "name": "Roomba", "password": ":1:...", "ip": "..." }, ... }
    robots: list[DiscoveredRobot] = []

    for blid, info in robots_raw.items():
        name     = info.get("name", f"Roomba ({blid[:6]})")
        password = info.get("password", "")

        # Try IP from cloud first (sometimes present), then UDP discovery
        ip = info.get("ip") or ""
        if not ip:
            _LOGGER.info("No cloud IP for %s — trying UDP discovery", name)
            ip = await _discover_ip(blid) or ""

        if not ip:
            _LOGGER.warning("Could not find IP for %s — you can enter it manually", name)

        robots.append(DiscoveredRobot(
            name     = name,
            blid     = blid,
            password = password,
            ip       = ip,
            sku      = info.get("sku", ""),
        ))
        _LOGGER.info("Discovered robot: %s  blid=%s  ip=%s", name, blid, ip or "unknown")

    return robots
