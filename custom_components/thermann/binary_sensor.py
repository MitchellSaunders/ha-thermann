"""Binary sensor platform for Thermann Smart - is the element actively heating."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ThermowattCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ThermowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ThermannHeatingBinarySensor(coordinator, serial, name)
        for serial, name in coordinator.devices.items()
    )


class ThermannHeatingBinarySensor(CoordinatorEntity[ThermowattCoordinator], BinarySensorEntity):
    """True while the heating element is actively on."""

    _attr_has_entity_name = True
    _attr_translation_key = "heating"
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator: ThermowattCoordinator, serial: str, name: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"thermann_{serial}_heating"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Thermowatt",
            name=name,
            model="Thermann Smart Electric",
        )

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(self._serial)
        if status is None:
            return None
        try:
            water_heater_sts = int(status.get("WaterHeaterSts", 0) or 0)
        except (TypeError, ValueError):
            return None
        return bool(water_heater_sts & 1)