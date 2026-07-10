"""Water heater platform for Thermowatt Smart."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ThermowattCoordinator
from .const import CMD_TO_MODE, DEFAULT_TEMP, DOMAIN, MAX_TEMP, MIN_TEMP, OPERATION_MODES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ThermowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ThermowattWaterHeater(coordinator, serial, name)
        for serial, name in coordinator.devices.items()
    )


class ThermowattWaterHeater(CoordinatorEntity[ThermowattCoordinator], WaterHeaterEntity):
    """Representation of one Thermowatt/Thermann Smart boiler."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_operation_list = OPERATION_MODES
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )

    def __init__(self, coordinator: ThermowattCoordinator, serial: str, name: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"thermowatt_{serial}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Thermowatt",
            name=name,
            model="Thermann Smart Electric",
        )
        self._last_setpoint = DEFAULT_TEMP

    @property
    def _status(self) -> dict:
        return self.coordinator.data.get(self._serial, {})

    @property
    def current_temperature(self) -> float | None:
        val = self._status.get("T_Avg")
        return float(val) if val is not None else None

    @property
    def target_temperature(self) -> float | None:
        val = self._status.get("T_SetPoint")
        if val is not None:
            self._last_setpoint = int(float(val))
        return float(val) if val is not None else None

    @property
    def current_operation(self) -> str | None:
        cmd = self._status.get("Cmd")
        try:
            return CMD_TO_MODE.get(int(cmd), None)
        except (TypeError, ValueError):
            return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = int(kwargs[ATTR_TEMPERATURE])
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_temperature, self._serial, temp
        )
        self._last_setpoint = temp
        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_mode, self._serial, operation_mode, self._last_setpoint
        )
        await self.coordinator.async_request_refresh()