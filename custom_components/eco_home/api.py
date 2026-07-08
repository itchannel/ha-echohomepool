"""Eco-Home cloud API client."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp

from .const import CLOUD_API, CRM_API

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "app-id-type": "0",
}


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


class EcoHomeApiError(Exception):
    """Raised when the API returns a failure."""


class EcoHomeApi:
    """Thin async wrapper around the Eco-Home cloud REST API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> str:
        """Login and return the x-token. Password is MD5-hashed before sending."""
        payload = {
            "user_name": email,
            "password": _md5(password),
            "type": "2",
        }
        data = await self._post(
            f"{CLOUD_API}/app/user/login.json",
            payload,
            authenticated=False,
        )
        token = data.get("x-token") or data.get("object_result", {}).get("x-token")
        if not token:
            # Some firmware versions nest the token differently
            token = data.get("object_result") if isinstance(data.get("object_result"), str) else None
        if not token:
            raise EcoHomeApiError("Login succeeded but no x-token in response")
        self._token = token
        return token

    def set_token(self, token: str) -> None:
        self._token = token

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def get_device_list(self) -> list[dict[str, Any]]:
        """Return list of all devices on the account."""
        data = await self._post(
            f"{CLOUD_API}/app/device/deviceList.json",
            {"page_index": "1", "page_size": "1000"},
        )
        result = data.get("object_result", [])
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Device state
    # ------------------------------------------------------------------

    async def get_device_detail(self, device_code: str) -> dict[str, Any]:
        """Fetch current device state. Tries V3 (crmservice) first, falls back to V1."""
        try:
            data = await self._post(
                f"{CRM_API}/app/deviceInfo/getDeviceDetailV3",
                {"deviceCode": device_code},
            )
            result = data.get("objectResult") or data.get("object_result")
            if result:
                return result
        except EcoHomeApiError:
            pass

        # Fallback to V1
        data = await self._post(
            f"{CLOUD_API}/app/deviceInfo/getDeviceDetail.json",
            {"deviceCode": device_code},
        )
        result = data.get("objectResult") or data.get("object_result")
        if not result:
            raise EcoHomeApiError(f"Empty device detail for {device_code}")
        return result

    # ------------------------------------------------------------------
    # Control commands
    # ------------------------------------------------------------------

    async def set_switch(self, device_code: str, value: bool, address: str) -> None:
        """Turn a single zone on or off."""
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/updateSwitchSate.json",
            {"device_code": device_code, "value": value, "address": address},
        )

    async def set_all_switch(self, device_code: str, value: bool) -> None:
        """Turn all zones on or off simultaneously."""
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/updateAllSwitchSate.json",
            {"device_code": device_code, "value": value},
        )

    async def set_temperature(
        self, device_code: str, value: int | float, address: str
    ) -> None:
        """Set target temperature for a zone."""
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/controlOfValue.json",
            {"device_code": device_code, "value": int(value), "address": address},
        )

    async def set_mode(
        self, device_code: str, mode_value: str, address: str
    ) -> None:
        """Change operating mode (cool/heat/auto)."""
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/updateModeValue.json",
            {"device_code": device_code, "value": mode_value, "address": address},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _post(
        self,
        url: str,
        payload: dict[str, Any],
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = dict(_HEADERS)
        if authenticated:
            if not self._token:
                raise EcoHomeApiError("Not authenticated")
            headers["x-token"] = self._token

        full_url = f"{url}?lang=en_US"
        _LOGGER.debug("POST %s %s", full_url, payload)

        try:
            async with self._session.post(
                full_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise EcoHomeApiError(f"HTTP error: {err}") from err

        _LOGGER.debug("Response: %s", data)

        # API signals auth expiry with sub_code -100
        if data.get("sub_code") == "-100":
            raise EcoHomeApiError("Token expired (sub_code -100)")

        if not data.get("is_reuslt_suc", True):
            raise EcoHomeApiError(data.get("error_msg", "Unknown API error"))

        return data
