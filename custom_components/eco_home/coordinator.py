"""DataUpdateCoordinator for Eco-Home."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EcoHomeApi, EcoHomeApiError
from .const import (
    CONF_DEVICE_CODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)

_LOGGER = logging.getLogger(__name__)


class EcoHomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the Eco-Home cloud for one device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.device_code: str = entry.data[CONF_DEVICE_CODE]
        self._email: str = entry.data[CONF_EMAIL]
        self._password: str = entry.data[CONF_PASSWORD]
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        self._session = aiohttp.ClientSession()
        self.api = EcoHomeApi(self._session)

        # Restore saved token if available
        if token := entry.data.get("token"):
            self.api.set_token(token)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.device_code}",
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._fetch_all()
        except EcoHomeApiError as err:
            if "Token expired" in str(err) or "Not authenticated" in str(err):
                await self._reauthenticate()
                try:
                    return await self._fetch_all()
                except EcoHomeApiError as err2:
                    raise UpdateFailed(str(err2)) from err2
            raise UpdateFailed(str(err)) from err

    async def _fetch_all(self) -> dict[str, Any]:
        """Fetch device detail and status params, merge into one dict."""
        detail, status_params = await asyncio.gather(
            self.api.get_device_detail(self.device_code),
            self.api.get_status_params(self.device_code),
            return_exceptions=True,
        )
        if isinstance(detail, Exception):
            raise detail
        if isinstance(status_params, Exception):
            _LOGGER.warning("Status params fetch failed (non-fatal): %s", status_params)
            status_params = []

        detail["statusParams"] = status_params
        return detail

    async def _reauthenticate(self) -> None:
        try:
            token = await self.api.login(self._email, self._password)
            # Persist new token into config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, "token": token},
            )
        except EcoHomeApiError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

    @property
    def device_info(self) -> DeviceInfo:
        data = self.data if isinstance(self.data, dict) else {}
        name = (
            data.get("deviceNickName")
            or data.get("device_nick_name")
            or self.device_code
        )
        sw_version = data.get("softVersion") or data.get("soft_version")
        model = data.get("deviceType") or data.get("device_type") or MODEL
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_code)},
            name=name,
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=sw_version,
        )

    async def async_shutdown(self) -> None:
        await self._session.close()
        await super().async_shutdown()
