"""Sensor entities for Eco-Home pool heat pump."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_CODE, DOMAIN
from .coordinator import EcoHomeCoordinator

_LOGGER = logging.getLogger(__name__)


def _parse_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Static sensors from the main device detail poll (cardList)
# ---------------------------------------------------------------------------

@dataclass
class EcoHomeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] | None = None


STATIC_SENSORS: list[EcoHomeSensorDescription] = [
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
    ),
]


# ---------------------------------------------------------------------------
# Keywords that indicate a temperature sensor in the status param name
# ---------------------------------------------------------------------------
_TEMP_KEYWORDS = (
    "temperature", "temp", "suction", "discharge", "exhaust",
    "coil", "condenser", "evaporator", "ambient", "inlet", "outlet",
    "water", "defrost", "plate", "effluent", "solar", "hot water",
    "floor heating", "room",
)

_SPEED_KEYWORDS = ("speed", "rpm", "frequency", "hz")
_PRESSURE_KEYWORDS = ("pressure",)
_BOOL_KEYWORDS = ("valve", "pump", "output", "switch", "status", "state")

# Cumulative energy (kWh) vs. instantaneous power (W) — checked in this order
# since a name like "power consumption" would otherwise match "power" first.
# This is a best-effort keyword guess like the others in this file; verify
# against the actual entity once it appears (name, unit, and whether the
# value keeps counting up vs. fluctuates) and let us know if it's misclassified.
_ENERGY_KEYWORDS = ("energy", "kwh", "electricity consumption", "power consumption")
_POWER_KEYWORDS = ("power", "watt")
_CURRENT_KEYWORDS = ("current", "amp")
_VOLTAGE_KEYWORDS = ("voltage", "volt")


def _guess_device_class(name: str) -> SensorDeviceClass | None:
    n = name.lower()
    if any(k in n for k in _TEMP_KEYWORDS):
        return SensorDeviceClass.TEMPERATURE
    if any(k in n for k in _ENERGY_KEYWORDS):
        return SensorDeviceClass.ENERGY
    if any(k in n for k in _POWER_KEYWORDS):
        return SensorDeviceClass.POWER
    if any(k in n for k in _CURRENT_KEYWORDS):
        return SensorDeviceClass.CURRENT
    if any(k in n for k in _VOLTAGE_KEYWORDS):
        return SensorDeviceClass.VOLTAGE
    if any(k in n for k in _SPEED_KEYWORDS):
        return None  # no HA device class for rpm/frequency generically
    if any(k in n for k in _PRESSURE_KEYWORDS):
        return SensorDeviceClass.PRESSURE
    return None


def _guess_unit(name: str, unit_from_api: str | None) -> str | None:
    """Prefer whatever unit the API returns, fallback to guessing from name.

    Temperature sensors are always normalised to a proper HA UnitOfTemperature
    enum value (never the raw device string) so that HA's automatic
    metric/imperial unit conversion — based on device_class + unit — actually
    kicks in. _guess_device_class tags these as SensorDeviceClass.TEMPERATURE
    independently of the raw unit text, so if we let an unrecognised raw
    string through here, HA can't reconcile the two and conversion silently
    never happens.
    """
    n = name.lower()
    if any(k in n for k in _TEMP_KEYWORDS):
        if unit_from_api and any(f in unit_from_api for f in ("℉", "°F", "F")):
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    # Same reasoning as temperature above: force a proper HA unit enum for
    # electrical measurements so device-class validation and (for energy)
    # the Energy dashboard actually accept the sensor.
    if any(k in n for k in _ENERGY_KEYWORDS):
        return UnitOfEnergy.KILO_WATT_HOUR
    if any(k in n for k in _POWER_KEYWORDS):
        return UnitOfPower.WATT
    if any(k in n for k in _CURRENT_KEYWORDS):
        return UnitOfElectricCurrent.AMPERE
    if any(k in n for k in _VOLTAGE_KEYWORDS):
        return UnitOfElectricPotential.VOLT

    if unit_from_api and unit_from_api.strip():
        return unit_from_api.strip()
    return None


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EcoHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_code = entry.data[CONF_DEVICE_CODE]

    entities: list[SensorEntity] = [
        EcoHomeStaticSensor(coordinator, device_code, desc)
        for desc in STATIC_SENSORS
    ]

    # Build dynamic status param sensors from the first data snapshot
    entities += _build_status_sensors(coordinator, device_code)

    async_add_entities(entities)

    # Re-scan for new status params each time data refreshes (handles firmware updates
    # that expose new registers). CoordinatorEntity already handles updates; we only
    # add *new* entities here, existing ones update themselves.
    known_keys: set[str] = {e.unique_id for e in entities if e.unique_id}

    def _add_new_params() -> None:
        new = [
            e for e in _build_status_sensors(coordinator, device_code)
            if e.unique_id not in known_keys
        ]
        if new:
            known_keys.update(e.unique_id for e in new if e.unique_id)
            async_add_entities(new)

    coordinator.async_add_listener(_add_new_params)


def _build_status_sensors(
    coordinator: EcoHomeCoordinator, device_code: str
) -> list["EcoHomeStatusSensor"]:
    """Build one sensor per entry in statusParams."""
    params: list[dict] = coordinator.data.get("statusParams", [])
    sensors = []
    seen: set[str] = set()
    for item in params:
        name = item.get("pointName")
        if not name or name in seen:
            continue
        seen.add(name)
        sensors.append(EcoHomeStatusSensor(coordinator, device_code, name, item))
    return sensors


# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------

class EcoHomeStaticSensor(CoordinatorEntity[EcoHomeCoordinator], SensorEntity):
    """A sensor with a fixed value_fn against coordinator.data."""

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
    def device_info(self):
        return self.coordinator.device_info

    @property
    def native_value(self) -> Any:
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None


class EcoHomeStatusSensor(CoordinatorEntity[EcoHomeCoordinator], SensorEntity):
    """A dynamic sensor sourced from the paramListV2 status query response.

    The API returns a list of {name, value, unit} objects covering live
    refrigerant circuit sensors: suction temperature, plate heat exchanger temps,
    ambient temperature, variable-speed pump speed/feedback, valve states, etc.
    We surface all of them; HA's entity registry disables unknown ones by default
    so the user can opt in to what they care about.
    """

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: EcoHomeCoordinator,
        device_code: str,
        param_name: str,
        initial_item: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._param_name = param_name
        self._device_code = device_code

        slug = _slugify(param_name)
        self._attr_unique_id = f"{device_code}_status_{slug}"
        self._attr_name = param_name

        unit = _guess_unit(param_name, initial_item.get("unit"))
        self._attr_native_unit_of_measurement = unit
        device_class = _guess_device_class(param_name)
        self._attr_device_class = device_class
        if device_class == SensorDeviceClass.ENERGY:
            # Energy dashboard compatibility requires total/total_increasing,
            # not measurement, for a cumulative kWh counter.
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT if unit else None

    @property
    def device_info(self):
        return self.coordinator.device_info

    def _find_item(self) -> dict[str, Any] | None:
        for item in self.coordinator.data.get("statusParams", []):
            if item.get("pointName") == self._param_name:
                return item
        return None

    @property
    def native_value(self) -> Any:
        item = self._find_item()
        if item is None:
            return None
        raw = item.get("addressValue")
        parsed = _parse_float(raw)
        return parsed if parsed is not None else raw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._find_item() or {}
        attrs: dict[str, Any] = {}
        if "address" in item:
            attrs["register_address"] = item["address"]
        return attrs

    @property
    def available(self) -> bool:
        return super().available and self._find_item() is not None
