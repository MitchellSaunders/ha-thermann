# Thermowatt Smart for Home Assistant

A native Home Assistant **integration** (not an add-on) for Thermowatt-based
smart electric water heaters, including the Australian **Thermann Smart
Electric** range. Talks directly to the Thermowatt cloud API used by the
MyThermowatt / Thermann Control apps - no separate MQTT broker or Docker
add-on required.

This started as a rewrite of
[waterheater-dev/ha-thermowatt-heater](https://github.com/waterheater-dev/ha-thermowatt-heater)
(an add-on), restructured as a proper `custom_components` integration with:

- Config flow (UI setup, no YAML)
- Credentials stored in HA's encrypted config entry storage, not a plaintext options file
- No dependency on Mosquitto/MQTT - polling happens inside HA itself via a `DataUpdateCoordinator`
- TLS certificate verification enabled on all requests (the original add-on had it disabled)

## Installation

### Via HACS (custom repository)
1. HACS -> Integrations -> ⋮ -> **Custom repositories**
2. Add this repo's URL, category **Integration**
3. Search for "Thermowatt Smart", install, restart Home Assistant

### Manual
Copy `custom_components/thermann/` into your `config/custom_components/` directory and restart Home Assistant.

## Setup

Settings -> Devices & Services -> Add Integration -> "Thermowatt Smart".
Enter your Thermann Control / MyThermowatt email and password.

If setup fails with an auth error, expand "App version" in the form and set
it to match your installed app's current version number (Thermowatt's
backend has been observed to reject requests claiming an old app version).

## What you get

One `water_heater` entity per boiler on your account, with:
- Current and target temperature
- Operation modes: `off`, `eco`, `manual`, `auto`, `holiday`
- A `Heating` binary sensor (whether the element is actively on right now)
- A `Temperature` sensor and an estimated `Energy` sensor (kWh, from heating time x element power)

## Polling and rate limits

Thermowatt's cloud locks accounts that make too many requests. This integration:

- Polls `/status` once per heater every **60 s** by default (configurable, 30-3600 s, under Configure).
- Backs off (doubling, up to 15 min, honouring `Retry-After`) after HTTP 429 or other errors, and returns to the normal interval after a success.
- Never retries a password login on its own. If the session can't be refreshed, polling stops and Home Assistant asks you to re-authenticate.
- Saves the session tokens, so restarting Home Assistant doesn't send a new login.

If your account was locked, wait until you can sign in to the app again before re-authenticating.

## Known limitations

- Cloud-dependent: if Thermowatt's backend or your internet is down, this integration can't reach your heater (same as the official app).
- The API was reverse-engineered from app traffic, not officially documented or supported by Thermowatt/Thermann. Endpoint or auth changes on their end can break this without notice - if that happens, check whether the app version bumped and update the `app_version` option first.
- Not affiliated with or endorsed by Thermowatt, Thermann, Rheem, or Ariston.
