"""Config flow for Eco-Home."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .api import EcoHomeApi, EcoHomeApiError
from .const import (
    CONF_DEVICE_CODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class EcoHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Eco-Home."""

    VERSION = 1

    def __init__(self) -> None:
        self._token: str | None = None
        self._email: str = ""
        self._password: str = ""
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            session = aiohttp.ClientSession()
            try:
                api = EcoHomeApi(session)
                self._token = await api.login(self._email, self._password)
                self._devices = await api.get_device_list()
            except EcoHomeApiError as err:
                _LOGGER.debug("Login error: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            finally:
                await session.close()

            if not errors:
                if not self._devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        device_options = {
            d["device_code"]: f"{d.get('device_nick_name') or d['device_code']} ({d.get('device_status', 'UNKNOWN')})"
            for d in self._devices
        }

        if user_input is not None:
            device_code = user_input[CONF_DEVICE_CODE]
            await self.async_set_unique_id(device_code)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=device_options[device_code],
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_DEVICE_CODE: device_code,
                    "token": self._token,
                },
            )

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_CODE): vol.In(device_options)}
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return EcoHomeOptionsFlow(config_entry)


class EcoHomeOptionsFlow(config_entries.OptionsFlow):
    """Options flow — lets the user adjust polling interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=10, max=3600)
                    )
                }
            ),
        )
