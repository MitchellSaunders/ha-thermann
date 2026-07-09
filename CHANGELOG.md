# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2026-07-09 (fork)

### Security

- Re-enabled TLS certificate verification on all requests to the Thermowatt API (was previously disabled with `verify=False`, exposing credentials/tokens to potential interception).

### Removed

- Unused `client.crt`, `client.key`, `root.pem` files left over from the removed AWS IoT MQTT bridge; no longer copied into the Docker image.

### Added

- `app_version` is now a configurable add-on option instead of a hardcoded `"3.14"`, since the Thermowatt backend appears to reject requests from stale app versions.

---

## [1.3.0] - 2026-01-27

### Removed

- AWS MQTT bridge for real-time status updates
- Certificate-based AWS IoT authentication

### Added

- Added polling loop to avoid rate limiting issues

### Fixed

- Rate limiting issues from frequent API polling, by performing polling in the correct, acceptable way.

---

## [1.2.0] - 2026-01-25

### Added

- AWS MQTT bridge for real-time status updates (replaces polling)
- Support for multiple devices with per-device AWS MQTT clients
- Certificate-based AWS IoT authentication
- Command cooldown mechanism to prevent stale status updates after commands

### Changed

- Commands now use REST API (matching app behavior)
- Status updates come from AWS MQTT instead of polling
- Removed polling loop to avoid rate limiting issues
- Updated status format handling to match AWS MQTT format

### Fixed

- Rate limiting issues from frequent API polling
- Status update cooldown after commands to prevent stale values overwriting optimistic updates

---

## [1.1.1] - 2026-01-24

### Changed

- Polling interval set to 60 seconds
- Updated HomeAssistant mode names to match app behavior

---

## [1.1.0] - 2026-01-24

### Changed

- Upgraded to support breaking backend changes observed after the release of app version 3.14

---

## [1.0.0] - 2026-01-18

### Added

- Initial release
- Basic MQTT bridge functionality
- Home Assistant discovery integration
- Support for temperature and mode control

---

[1.2.0]: https://github.com/waterheater-dev/ha-thermowatt-heater/compare/1.1.1...1.2.0
[1.1.1]: https://github.com/waterheater-dev/ha-thermowatt-heater/compare/1.1.0...1.1.1
[1.1.0]: https://github.com/waterheater-dev/ha-thermowatt-heater/compare/1.0.0...1.1.0
[1.0.0]: https://github.com/waterheater-dev/ha-thermowatt-heater/releases/tag/1.0.0
