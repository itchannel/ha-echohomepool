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
    "Connection": "keep-alive",
    "Accept": "*/*",
    "app-id-type": "0",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
        "Html5Plus/1.0 (Immersed/20) uni-app"
    ),
}


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


class EcoHomeApiError(Exception):
    """Raised when the API returns a failure."""


class EcoHomeApi:
    """Async wrapper around the Eco-Home cloud REST API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> str:
        """Login and return the x-token. Password is MD5-hashed before sending."""
        data = await self._post(
            f"{CLOUD_API}/app/user/login.json",
            {"user_name": email, "password": _md5(password), "type": 2},
            authenticated=False,
        )
        token = data.get("object_result", {}).get("x-token")
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
        """Fetch current device state from crmservice V3."""
        data = await self._post(
            f"{CRM_API}/app/deviceInfo/getDeviceDetailV3",
            {"deviceCode": device_code},
        )
        result = data.get("objectResult")
        if not result:
            raise EcoHomeApiError(f"Empty device detail for {device_code}")
        return result

    async def get_status_params(self, device_code: str) -> list[dict[str, Any]]:
        """Fetch live status sensor registers.

        Type 0 = system status (flat list of {point_name, address_value, unit})
        Type 1 = module status (grouped: [{moduleContent: [{point_name, ...}]}])

        Returns a single flat list combining both.
        """
        results: list[dict[str, Any]] = []
        for param_type in (0, 1):
            items = await self._fetch_param_list(device_code, param_type)
            results.extend(items)
        return results

    async def _fetch_param_list(
        self, device_code: str, param_type: int
    ) -> list[dict[str, Any]]:
        data = await self._post(
            f"{CRM_API}/app/deviceInfo/paramListV3",
            {"deviceCode": device_code, "type": param_type, "isAutoRefresh": False},
        )
        raw = data.get("objectResult")

        _LOGGER.warning(
            "paramListV3 type=%s raw response keys=%s objectResult type=%s value=%s",
            param_type,
            list(data.keys()),
            type(raw).__name__,
            str(raw)[:500],
        )

        if not isinstance(raw, list):
            _LOGGER.warning("paramListV3 type=%s returned non-list: %s", param_type, type(raw))
            return []

        flat: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            if "moduleContent" in item:
                # Type 1 grouped structure
                content = item["moduleContent"]
                if isinstance(content, list):
                    flat.extend(i for i in content if isinstance(i, dict))
            elif "point_name" in item:
                flat.append(item)

        return flat

    # ------------------------------------------------------------------
    # Control commands
    # ------------------------------------------------------------------

    async def set_switch(self, device_code: str, value: bool, address: str) -> None:
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/updateSwitchSate.json",
            {"device_code": device_code, "value": value, "address": address},
        )

    async def set_all_switch(self, device_code: str, value: bool) -> None:
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/updateAllSwitchSate.json",
            {"device_code": device_code, "value": value},
        )

    async def set_temperature(self, device_code: str, value: int | float, address: str) -> None:
        await self._post(
            f"{CLOUD_API}/app/deviceInfo/controlOfValue.json",
            {"device_code": device_code, "value": int(value), "address": address},
        )

    async def set_mode(self, device_code: str, mode_value: str, address: str) -> None:
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
                full_url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise EcoHomeApiError(f"HTTP error: {err}") from err

        _LOGGER.debug("Response: %s", data)

        if data.get("sub_code") == "-100":
            raise EcoHomeApiError("Token expired (sub_code -100)")

        # errorCode style (some endpoints)
        if "errorCode" in data and data["errorCode"] != 200:
            raise EcoHomeApiError(f"{data['errorCode']}: {data.get('errorMsg', 'error')}")

        # error_code style (cloudservice endpoints)
        if data.get("error_code", "0") != "0":
            raise EcoHomeApiError(f"{data['error_code']}: {data.get('error_msg', 'error')}")

        # is_reuslt_suc style (typo is intentional — matches the API)
        if "is_reuslt_suc" in data and not data["is_reuslt_suc"]:
            raise EcoHomeApiError(data.get("error_msg", "Unknown API error"))

        return data
