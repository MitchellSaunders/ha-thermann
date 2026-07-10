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
PLATFORMS = [Platform.WATER_HEATER, Platform.SENSOR, Platform.BINARY_SENSOR]


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

    # Fields we need present on a device dict for it to be usable as a full
    # status reading (whichever endpoint it came from).
    _REQUIRED_STATUS_FIELDS = {"T_SetPoint", "T_Avg", "Cmd"}

    def _poll_all(self) -> dict[str, dict]:
        data: dict[str, dict] = {}

        # /user-info is what populates the app's own device list/dashboard,
        # so it's our best bet for a reading that reflects changes made
        # directly in the app. /status is used only as a per-device fallback
        # for whichever fields are missing from /user-info.
        try:
            fresh_devices = self.client.list_devices()
        except ThermowattApiError as err:
            _LOGGER.debug("list_devices() poll failed, falling back to /status only: %s", err)
            fresh_devices = []

        fresh_by_serial = {d.get("seriale"): d for d in fresh_devices if d.get("seriale")}
        _LOGGER.debug("user-info device payload: %s", fresh_by_serial)

        for serial in self.devices:
            info = fresh_by_serial.get(serial, {})
            if self._REQUIRED_STATUS_FIELDS <= info.keys():
                data[serial] = info
            else:
                _LOGGER.debug(
                    "user-info missing status fields for %s, falling back to /status", serial
                )
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

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options (e.g. element_kw) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded