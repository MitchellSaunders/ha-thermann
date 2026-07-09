"""The Thermowatt Smart (Thermann Smart Electric) integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ThermowattApiError, ThermowattAuthError, ThermowattClient
from .const import CONF_APP_VERSION, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.WATER_HEATER]


class ThermowattCoordinator(DataUpdateCoordinator):
    """Polls status for all devices on the account."""

    def __init__(self, hass: HomeAssistant, client: ThermowattClient, devices: list[dict]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.client = client
        self.devices = {d["seriale"]: d.get("nome", "Boiler") for d in devices}

    def _poll_all(self) -> dict[str, dict]:
        data: dict[str, dict] = {}
        for serial in self.devices:
            data[serial] = self.client.get_status(serial)
        return data

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            return await self.hass.async_add_executor_job(self._poll_all)
        except ThermowattAuthError as err:
            raise ConfigEntryAuthFailed from err
        except ThermowattApiError as err:
            raise UpdateFailed(str(err)) from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermowatt Smart from a config entry."""
    client = ThermowattClient(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        device_uuid=entry.data["device_uuid"],
        app_version=entry.data[CONF_APP_VERSION],
    )

    try:
        await hass.async_add_executor_job(client.login)
        devices = await hass.async_add_executor_job(client.list_devices)
    except ThermowattAuthError as err:
        raise ConfigEntryAuthFailed from err
    except ThermowattApiError as err:
        raise ConfigEntryNotReady from err

    if not devices:
        raise ConfigEntryNotReady("Thermowatt account returned zero devices")

    coordinator = ThermowattCoordinator(hass, client, devices)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
