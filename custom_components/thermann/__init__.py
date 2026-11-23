"""The Thermowatt Smart (Thermann Smart Electric) integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ThermowattApiError, ThermowattAuthError, ThermowattClient, ThermowattRateLimitError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_APP_VERSION,
    CONF_DEVICE_UUID,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_BACKOFF_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.WATER_HEATER, Platform.SENSOR, Platform.BINARY_SENSOR]


@callback
def async_save_tokens(hass: HomeAssistant, entry: ConfigEntry, client: ThermowattClient) -> None:
    """Persist the client's current tokens in the entry if they changed."""
    access, refresh = client.tokens
    if not access or not refresh:
        return
    if (entry.data.get(CONF_ACCESS_TOKEN), entry.data.get(CONF_REFRESH_TOKEN)) == (access, refresh):
        return
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ACCESS_TOKEN: access, CONF_REFRESH_TOKEN: refresh}
    )


class ThermowattCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Polls /status for every device on the account, with backoff on errors."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ThermowattClient,
        devices: list[dict],
    ) -> None:
        self._base_interval = timedelta(
            seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._base_interval,
        )
        self.client = client
        self.devices = {d["seriale"]: d.get("nome", "Boiler") for d in devices if d.get("seriale")}
        # Options at setup time; lets the update listener tell an options
        # change (needs reload) from a token save (must NOT reload).
        self.options_snapshot = dict(entry.options)

    def _poll_all(self) -> dict[str, dict]:
        # One /status call per device. /user-info is account-level and only
        # fetched once at setup.
        return {serial: self.client.get_status(serial) for serial in self.devices}

    def _back_off(self, retry_after: float | None) -> None:
        current = self.update_interval or self._base_interval
        wanted = max(current * 2, timedelta(seconds=retry_after or 0))
        ceiling = max(timedelta(seconds=MAX_BACKOFF_INTERVAL), self._base_interval)
        self.update_interval = min(wanted, ceiling)

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            data = await self.hass.async_add_executor_job(self._poll_all)
        except ThermowattAuthError as err:
            # Stops polling and asks the user to re-authenticate. We never
            # retry a password login automatically.
            raise ConfigEntryAuthFailed(str(err)) from err
        except ThermowattRateLimitError as err:
            self._back_off(err.retry_after)
            raise UpdateFailed(f"{err}; backing off to {self.update_interval}") from err
        except ThermowattApiError as err:
            self._back_off(None)
            raise UpdateFailed(f"{err}; backing off to {self.update_interval}") from err
        finally:
            # A refresh may have rotated the tokens even if the poll failed.
            async_save_tokens(self.hass, self.config_entry, self.client)

        if self.update_interval != self._base_interval:
            _LOGGER.info("Thermowatt poll recovered; back to %s interval", self._base_interval)
            self.update_interval = self._base_interval
        return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermowatt Smart from a config entry."""
    client = ThermowattClient(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        device_uuid=entry.data[CONF_DEVICE_UUID],
        app_version=entry.data[CONF_APP_VERSION],
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )

    def _connect() -> list[dict]:
        # Reuse the stored session when possible; a restart should not cost a
        # password login. Fall back to exactly one login if it is dead.
        if client.has_tokens:
            try:
                return client.list_devices()
            except ThermowattAuthError:
                _LOGGER.debug("Stored Thermowatt session is no longer valid; logging in once")
        client.login()
        return client.list_devices()

    try:
        devices = await hass.async_add_executor_job(_connect)
    except ThermowattAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ThermowattRateLimitError as err:
        # Don't let HA's setup retry keep hammering a rate-limited account.
        # Reauth puts the next attempt in the user's hands.
        _LOGGER.warning(
            "Thermowatt is rate limiting this account (%s). Polling is paused; "
            "wait for the lockout to clear, then re-authenticate from Devices & Services.",
            err,
        )
        raise ConfigEntryAuthFailed(str(err)) from err
    except ThermowattApiError as err:
        raise ConfigEntryNotReady(str(err)) from err
    finally:
        async_save_tokens(hass, entry, client)

    if not devices:
        raise ConfigEntryNotReady("Thermowatt account returned zero devices")

    coordinator = ThermowattCoordinator(hass, entry, client, devices)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change. Token saves also fire this; ignore those."""
    coordinator: ThermowattCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator.options_snapshot == dict(entry.options):
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: ThermowattCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(coordinator.client.session.close)
    return unloaded
