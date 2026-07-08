"""Sensor entities for Eco-Home pool heat pump."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_CODE, DOMAIN
from .coordinator import EcoHomeCoordinator


@dataclass
class EcoHomeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] | None = None


def _card0(data: dict) -> dict:
    cards = data.get("cardList", [{}])
    return cards[0] if cards else {}


def _parse_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


SENSOR_DESCRIPTIONS: list[EcoHomeSensorDescription] = [
    EcoHomeSensorDescription(
        key="current_temp_zone1",
        name="Water Temperature Zone 1",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _parse_float(
            (d.get("cardList") or [{}])[0].get("curTempMain")
            or (d.get("cardList") or [{}])[0].get("cur_temp")
        ),
    ),
    EcoHomeSensorDescription(
        key="set_temp_zone1",
        name="Target Temperature Zone 1",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _parse_float(
            (d.get("cardList") or [{}])[0].get("settingTemp")
        ),
    ),
    EcoHomeSensorDescription(
        key="current_temp_zone2",
        name="Water Temperature Zone 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _parse_float(
            (d.get("cardList") or [{}, {}])[1].get("curTempMain")
            if len(d.get("cardList", [])) > 1 else None
        ),
        entity_registry_enabled_default=False,
    ),
    EcoHomeSensorDescription(
        key="set_temp_zone2",
        name="Target Temperature Zone 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _parse_float(
            (d.get("cardList") or [{}, {}])[1].get("settingTemp")
            if len(d.get("cardList", [])) > 1 else None
        ),
        entity_registry_enabled_default=False,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EcoHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_code = entry.data[CONF_DEVICE_CODE]

    async_add_entities(
        EcoHomeSensor(coordinator, device_code, desc)
        for desc in SENSOR_DESCRIPTIONS
    )


class EcoHomeSensor(CoordinatorEntity[EcoHomeCoordinator], SensorEntity):
    """A sensor reading from the pool heat pump."""

    entity_description: EcoHomeSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EcoHomeCoordinator,
        device_code: str,
        description: EcoHomeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_code}_{description.key}"

    @property
    def native_value(self) -> Any:
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.native_value is not None
