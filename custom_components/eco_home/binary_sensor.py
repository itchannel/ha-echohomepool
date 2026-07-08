"""Binary sensors for Eco-Home pool heat pump."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_CODE, DOMAIN
from .coordinator import EcoHomeCoordinator

_FAULT_MSG_KEYS = (
    "faultMsg", "fault_msg", "alarmMsg", "alarm_msg", "errorMsg",
    "error_msg", "faultInfo", "fault_info", "alarmInfo", "alarm_info",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EcoHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_code = entry.data[CONF_DEVICE_CODE]
    async_add_entities([
        EcoHomeFaultSensor(coordinator, device_code),
        EcoHomeOnlineSensor(coordinator, device_code),
    ])


class EcoHomeFaultSensor(CoordinatorEntity[EcoHomeCoordinator], BinarySensorEntity):
    """True when the device reports a fault."""

    _attr_has_entity_name = True
    _attr_name = "Fault"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: EcoHomeCoordinator, device_code: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_code}_fault"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("isFault", False))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        attrs: dict = {}
        for key in _FAULT_MSG_KEYS:
            if val := data.get(key):
                attrs[key] = val
        # Also scan cardList for per-zone fault messages
        for card in data.get("cardList", []):
            for key in _FAULT_MSG_KEYS:
                if val := card.get(key):
                    zone = card.get("card", "?")
                    attrs[f"zone_{zone}_{key}"] = val
        return attrs


class EcoHomeOnlineSensor(CoordinatorEntity[EcoHomeCoordinator], BinarySensorEntity):
    """True when the device is online."""

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: EcoHomeCoordinator, device_code: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_code}_online"

    @property
    def is_on(self) -> bool:
        status = self.coordinator.data.get("deviceStatus", "ONLINE")
        return str(status).upper() == "ONLINE"
