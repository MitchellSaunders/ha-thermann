"""Sensor platform for Thermann Smart: current temperature + estimated energy use."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ThermowattCoordinator
from .const import CONF_ELEMENT_KW, DEFAULT_ELEMENT_KW, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ThermowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    element_kw = entry.options.get(CONF_ELEMENT_KW, DEFAULT_ELEMENT_KW)

    entities: list[SensorEntity] = []
    for serial, name in coordinator.devices.items():
        entities.append(ThermannTemperatureSensor(coordinator, serial, name))
        entities.append(ThermannEnergySensor(coordinator, serial, name, element_kw))
    async_add_entities(entities)


def _device_info(serial: str, name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, serial)},
        manufacturer="Thermowatt",
        name=name,
        model="Thermann Smart Electric",
    )


class ThermannTemperatureSensor(CoordinatorEntity[ThermowattCoordinator], SensorEntity):
    """Current tank temperature as a standalone sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: ThermowattCoordinator, serial: str, name: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"thermann_{serial}_current_temperature"
        self._attr_device_info = _device_info(serial, name)

    @property
    def native_value(self) -> float | None:
        val = self.coordinator.data.get(self._serial, {}).get("T_Avg")
        return float(val) if val is not None else None


class ThermannEnergySensor(CoordinatorEntity[ThermowattCoordinator], RestoreSensor):
    """Estimated cumulative energy use, integrated from heating on/off time * element kW.

    This is an estimate, not a measurement from a real power meter: it assumes
    the element draws a constant `element_kw` (set in the integration's
    Configure/Options screen) for the entire time the cloud reports it as
    heating. Suitable for rough tracking / the Energy dashboard, not billing.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self, coordinator: ThermowattCoordinator, serial: str, name: str, element_kw: float
    ) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._element_kw = element_kw
        self._attr_unique_id = f"thermann_{serial}_energy"
        self._attr_device_info = _device_info(serial, name)
        self._total_kwh = 0.0
        self._last_update = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data is not None and last_data.native_value is not None:
            try:
                self._total_kwh = float(last_data.native_value)
            except (TypeError, ValueError):
                self._total_kwh = 0.0
        self._last_update = dt_util.utcnow()

    @property
    def native_value(self) -> float:
        return round(self._total_kwh, 3)

    @property
    def extra_state_attributes(self) -> dict:
        return {"element_kw": self._element_kw}

    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        if self._last_update is not None:
            elapsed_hours = (now - self._last_update).total_seconds() / 3600
            status = self.coordinator.data.get(self._serial, {})
            try:
                water_heater_sts = int(status.get("WaterHeaterSts", 0) or 0)
            except (TypeError, ValueError):
                water_heater_sts = 0
            if water_heater_sts & 1:
                self._total_kwh += self._element_kw * elapsed_hours
        self._last_update = now
        super()._handle_coordinator_update()