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
Copy `custom_components/thermowatt_smart/` into your `config/custom_components/` directory and restart Home Assistant.

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
- A `heating` attribute (whether the element is actively on right now)

## Known limitations

- Cloud-dependent: if Thermowatt's backend or your internet is down, this integration can't reach your heater (same as the official app).
- The API was reverse-engineered from app traffic, not officially documented or supported by Thermowatt/Thermann. Endpoint or auth changes on their end can break this without notice - if that happens, check whether the app version bumped and update the `app_version` option first.
- Not affiliated with or endorsed by Thermowatt, Thermann, Rheem, or Ariston.
