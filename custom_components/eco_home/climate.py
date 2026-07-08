"""Climate entity for Eco-Home pool heat pump."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EcoHomeApiError
from .const import (
    CONF_DEVICE_CODE,
    DOMAIN,
    MODE_MEANING_AUTO_KEYWORDS,
    MODE_MEANING_COOL_KEYWORDS,
    MODE_MEANING_HEAT_KEYWORDS,
)
from .coordinator import EcoHomeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EcoHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    card_list = coordinator.data.get("cardList", [])

    entities = []
    for card in card_list:
        card_id = card.get("card", "0")
        if card_id == "0":
            # card "0" is the "all zones" master — skip, handled by switch
            continue
        entities.append(
            EcoHomeClimate(coordinator, entry.data[CONF_DEVICE_CODE], card_id)
        )

    # If we only got card "0" or nothing, create one entity from card index 0
    if not entities:
        entities.append(EcoHomeClimate(coordinator, entry.data[CONF_DEVICE_CODE], None))

    async_add_entities(entities)


def _meaning_to_hvac_mode(meaning: str) -> HVACMode:
    m = meaning.lower()
    for kw in MODE_MEANING_COOL_KEYWORDS:
        if kw.lower() in m:
            return HVACMode.COOL
    for kw in MODE_MEANING_HEAT_KEYWORDS:
        if kw.lower() in m:
            return HVACMode.HEAT
    for kw in MODE_MEANING_AUTO_KEYWORDS:
        if kw.lower() in m:
            return HVACMode.AUTO
    return HVACMode.AUTO


class EcoHomeClimate(CoordinatorEntity[EcoHomeCoordinator], ClimateEntity):
    """Pool heat pump zone climate entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: EcoHomeCoordinator,
        device_code: str,
        card_id: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._device_code = device_code
        self._card_id = card_id

        suffix = f"_zone{card_id}" if card_id else ""
        self._attr_unique_id = f"{device_code}{suffix}_climate"
        label = f"Zone {card_id}" if card_id else "Heat Pump"
        self._attr_name = label

    @property
    def device_info(self):
        return self.coordinator.device_info

    # ------------------------------------------------------------------
    # Helpers to read current card data
    # ------------------------------------------------------------------

    def _card(self) -> dict[str, Any]:
        cards: list[dict] = self.coordinator.data.get("cardList", [])
        if self._card_id is not None:
            for c in cards:
                if str(c.get("card")) == str(self._card_id):
                    return c
        result = cards[0] if cards else {}
        if result and not hasattr(self, "_card_logged"):
            self._card_logged = True
            _LOGGER.debug("Card data keys/values: %s", result)
        return result

    def _build_hvac_modes(self) -> list[HVACMode]:
        modes = {HVACMode.OFF}
        for entry in self._card().get("modeList", []):
            modes.add(_meaning_to_hvac_mode(entry.get("modeMeaning", "")))
        return list(modes) if len(modes) > 1 else [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return self._build_hvac_modes()

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.lower() not in ("false", "0", "")
        return bool(value)

    @property
    def hvac_mode(self) -> HVACMode:
        card = self._card()
        if not self._to_bool(card.get("curSwitch", False)):
            return HVACMode.OFF

        try:
            cur_mode_idx = int(float(card.get("curMode") or 0))
        except (TypeError, ValueError):
            cur_mode_idx = 0
        mode_list: list[dict] = card.get("modeList", [])
        if mode_list and cur_mode_idx < len(mode_list):
            meaning = mode_list[cur_mode_idx].get("modeMeaning", "")
            return _meaning_to_hvac_mode(meaning)
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.coordinator.data.get("isFault"):
            return HVACAction.IDLE
        card = self._card()
        cur = self._parse_temp(card.get("curTempMain") or card.get("cur_temp"))
        target = self._parse_temp(card.get("settingTemp"))
        if cur is None or target is None:
            return HVACAction.HEATING
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING if cur < target else HVACAction.IDLE
        if mode == HVACMode.COOL:
            return HVACAction.COOLING if cur > target else HVACAction.IDLE
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        card = self._card()
        return self._parse_temp(card.get("curTempMain") or card.get("cur_temp"))

    @property
    def target_temperature(self) -> float | None:
        return self._parse_temp(self._card().get("settingTemp"))

    @property
    def min_temp(self) -> float:
        return self._parse_temp(self._card().get("lowerTemp") or self._card().get("lower_temp")) or 10.0

    @property
    def max_temp(self) -> float:
        return self._parse_temp(self._card().get("upperTemp") or self._card().get("upper_temp")) or 40.0

    @property
    def target_temperature_step(self) -> float:
        return 1.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        card = self._card()
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "is_fault": data.get("isFault", False),
            "device_online": data.get("deviceStatus", "UNKNOWN"),
            "card_id": self._card_id,
            "switch_address": card.get("switchAddress"),
            "temp_address": card.get("settingAddress") or card.get("temp_address"),
            "mode_address": (card.get("modeList") or [{}])[0].get("address"),
        }
        # Surface any fault/alarm messages from the API
        for key in ("faultMsg", "fault_msg", "alarmMsg", "alarm_msg", "errorMsg",
                    "error_msg", "faultCode", "fault_code", "alarmInfo", "alarm_info",
                    "faultInfo", "fault_info"):
            if val := data.get(key) or card.get(key):
                attrs[key] = val
        if spa := card.get("isSpa"):
            attrs["is_spa"] = spa
        return attrs

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        card = self._card()

        switch_addr = card.get("switchAddress") or card.get("switch_address") or ""

        if hvac_mode == HVACMode.OFF:
            try:
                await self.coordinator.api.set_switch(self._device_code, False, switch_addr)
            except EcoHomeApiError as err:
                _LOGGER.error("Failed to turn off: %s", err)
            await self.coordinator.async_request_refresh()
            return

        # If currently off, turn on first
        if not self._to_bool(card.get("curSwitch", False)):
            try:
                await self.coordinator.api.set_switch(self._device_code, True, switch_addr)
            except EcoHomeApiError as err:
                _LOGGER.error("Failed to turn on: %s", err)
                await self.coordinator.async_request_refresh()
                return

        # Find matching mode entry
        mode_list: list[dict] = card.get("modeList", [])
        target_entry = None
        for entry in mode_list:
            if _meaning_to_hvac_mode(entry.get("modeMeaning", "")) == hvac_mode:
                target_entry = entry
                break

        if target_entry is None:
            _LOGGER.debug("No mode entry for %s in modeList: %s", hvac_mode, mode_list)
            await self.coordinator.async_request_refresh()
            return

        mode_value = target_entry.get("modeValue")
        mode_addr = target_entry.get("address") or target_entry.get("modeAddress")

        if mode_value is None or mode_addr is None:
            _LOGGER.error(
                "Mode entry missing modeValue/address keys: %s", target_entry
            )
            await self.coordinator.async_request_refresh()
            return

        try:
            await self.coordinator.api.set_mode(self._device_code, mode_value, mode_addr)
        except EcoHomeApiError as err:
            _LOGGER.error("Failed to set mode: %s", err)

        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        card = self._card()
        address = (
            card.get("settingAddress")
            or card.get("tempAddress")
            or card.get("temp_address")
        )
        if not address:
            _LOGGER.error("No temperature address in card data: %s", card)
            return
        try:
            await self.coordinator.api.set_temperature(self._device_code, temp, address)
        except EcoHomeApiError as err:
            _LOGGER.error("Failed to set temperature: %s", err)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        card = self._card()
        switch_addr = card.get("switchAddress") or card.get("switch_address") or ""
        try:
            await self.coordinator.api.set_switch(self._device_code, True, switch_addr)
        except EcoHomeApiError as err:
            _LOGGER.error("Failed to turn on: %s", err)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        card = self._card()
        switch_addr = card.get("switchAddress") or card.get("switch_address") or ""
        try:
            await self.coordinator.api.set_switch(self._device_code, False, switch_addr)
        except EcoHomeApiError as err:
            _LOGGER.error("Failed to turn off: %s", err)
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_temp(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
