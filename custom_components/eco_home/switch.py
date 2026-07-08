"""Master power switch for Eco-Home pool heat pump."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EcoHomeApiError
from .const import CONF_DEVICE_CODE, DOMAIN
from .coordinator import EcoHomeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EcoHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EcoHomeMasterSwitch(coordinator, entry.data[CONF_DEVICE_CODE])])


class EcoHomeMasterSwitch(CoordinatorEntity[EcoHomeCoordinator], SwitchEntity):
    """Turns all zones on/off with a single command."""

    _attr_has_entity_name = True
    _attr_name = "Power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: EcoHomeCoordinator, device_code: str) -> None:
        super().__init__(coordinator)
        self._device_code = device_code
        self._attr_unique_id = f"{device_code}_master_switch"

    @property
    def device_info(self):
        return self.coordinator.device_info

    @property
    def is_on(self) -> bool:
        cards = self.coordinator.data.get("cardList", [])
        # On if any non-master card is on
        active = [c for c in cards if str(c.get("card")) != "0"]
        return any(c.get("curSwitch", False) for c in active) if active else False

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.coordinator.api.set_all_switch(self._device_code, True)
        except EcoHomeApiError as err:
            _LOGGER.error("Failed to turn on all zones: %s", err)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.coordinator.api.set_all_switch(self._device_code, False)
        except EcoHomeApiError as err:
            _LOGGER.error("Failed to turn off all zones: %s", err)
        await self.coordinator.async_request_refresh()
