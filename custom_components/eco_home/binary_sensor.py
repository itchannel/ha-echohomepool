"""Binary sensors for Eco-Home pool heat pump."""
from __future__ import annotations

import logging

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

_LOGGER = logging.getLogger(__name__)


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
    def device_info(self):
        return self.coordinator.device_info

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("isFault", False))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        attrs: dict = {}
        # faultNum is a real field confirmed from a live payload dump.
        fault_num = data.get("faultNum")
        if fault_num not in (None, 0, "0"):
            attrs["fault_code"] = fault_num

        # getDeviceFaultInfo.json returns a LIST of fault records (confirmed
        # live), each with a "description" field — that's the actual
        # human-readable message, not a single "fault_msg_list" string.
        fault_list = data.get("faultInfoList") or []
        descriptions = [
            f.get("description") for f in fault_list
            if isinstance(f, dict) and f.get("description")
        ]
        if descriptions:
            attrs["fault_message"] = "; ".join(descriptions)
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
    def device_info(self):
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        # Deliberately don't defer to CoordinatorEntity's default (which
        # ties availability to last_update_success) — this entity's whole
        # job is to show "off" when the device can't be reached, so it must
        # stay available even when the coordinator's poll fails.
        return True

    @property
    def is_on(self) -> bool:
        # The device detail response has no "deviceStatus"/online field at
        # all (confirmed from a live payload dump), so the old code always
        # defaulted to "ONLINE" regardless of reality. The only genuine
        # connectivity signal this API gives us is whether the last poll
        # actually succeeded.
        return self.coordinator.last_update_success
