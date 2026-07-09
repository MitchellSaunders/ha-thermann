"""Config flow for Thermowatt Smart."""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import ThermowattAuthError, ThermowattClient
from .const import CONF_APP_VERSION, DEFAULT_APP_VERSION, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_APP_VERSION, default=DEFAULT_APP_VERSION): str,
    }
)


async def _validate_login(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Attempt a real login. Returns the device_uuid to persist. Raises on failure."""
    device_uuid = str(uuid.uuid4())
    client = ThermowattClient(
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        device_uuid=device_uuid,
        app_version=data[CONF_APP_VERSION],
    )
    try:
        await hass.async_add_executor_job(client.login)
    except ThermowattAuthError as err:
        raise InvalidAuth from err
    return device_uuid


class ThermowattSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thermowatt Smart."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            try:
                device_uuid = await _validate_login(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={**user_input, "device_uuid": device_uuid},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class InvalidAuth(HomeAssistantError):
    """Error to indicate login failed."""
