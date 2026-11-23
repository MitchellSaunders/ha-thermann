"""Config flow for Thermowatt Smart."""
from __future__ import annotations

from collections.abc import Mapping
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback

from .api import ThermowattApiError, ThermowattAuthError, ThermowattClient, ThermowattRateLimitError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_APP_VERSION,
    CONF_DEVICE_UUID,
    CONF_ELEMENT_KW,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    DEFAULT_APP_VERSION,
    DEFAULT_ELEMENT_KW,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_APP_VERSION, default=DEFAULT_APP_VERSION): str,
    }
)


async def _login(
    hass: HomeAssistant, email: str, password: str, app_version: str, device_uuid: str
) -> dict[str, str]:
    """Do one real login. Returns the token fields to store. Raises on failure."""
    client = ThermowattClient(
        email=email, password=password, device_uuid=device_uuid, app_version=app_version
    )
    try:
        await hass.async_add_executor_job(client.login)
    finally:
        await hass.async_add_executor_job(client.session.close)
    access, refresh = client.tokens
    return {CONF_ACCESS_TOKEN: access, CONF_REFRESH_TOKEN: refresh}


def _error_key(err: Exception) -> str:
    if isinstance(err, ThermowattRateLimitError):
        return "rate_limited"
    if isinstance(err, ThermowattAuthError):
        return "invalid_auth"
    if isinstance(err, ThermowattApiError):
        return "cannot_connect"
    return "unknown"


class ThermowattSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thermowatt Smart."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "ThermannOptionsFlow":
        return ThermannOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            device_uuid = str(uuid.uuid4())
            try:
                tokens = await _login(
                    self.hass,
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_APP_VERSION],
                    device_uuid,
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                # Store the tokens so setup reuses this session instead of
                # sending a second login straight away.
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={**user_input, CONF_DEVICE_UUID: device_uuid, **tokens},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Triggered when the session can't be refreshed or the account is rate limited."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            app_version = user_input.get(CONF_APP_VERSION, entry.data[CONF_APP_VERSION])
            try:
                tokens = await _login(
                    self.hass,
                    entry.data[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                    app_version,
                    # Keep the same device id so the account doesn't
                    # accumulate a new "phone" on every reauth.
                    entry.data[CONF_DEVICE_UUID],
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_APP_VERSION: app_version,
                        **tokens,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(
                        CONF_APP_VERSION, default=entry.data.get(CONF_APP_VERSION, DEFAULT_APP_VERSION)
                    ): str,
                }
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )


class ThermannOptionsFlow(config_entries.OptionsFlow):
    """Element power rating (energy estimate) and poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ELEMENT_KW, default=options.get(CONF_ELEMENT_KW, DEFAULT_ELEMENT_KW)
                ): vol.Coerce(float),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
