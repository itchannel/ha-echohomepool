# Changelog

All notable changes to this integration are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-07-08

### Fixed

- **Setup failure on first install** (`-1: Error querying device list`): the
  cloudservice fallback for device detail was sending the device code under
  the wrong parameter key (`deviceCode` instead of `device_code`), causing
  the backend to fail looking up the device. All `CLOUD_API` endpoints now
  use `device_code` consistently.
- **Crash on startup** (`TypeError: '<' not supported between instances of
  'str' and 'int'`): `curMode` is sometimes returned as a string by the API;
  it's now safely cast to `int` before being used as a list index.
- **Status/dynamic sensors permanently empty**: an expired auth token was
  silently swallowed when fetching status parameters, so the coordinator
  never reauthenticated. Token expiry is now detected and triggers a
  re-login + retry, regardless of which API call surfaces it.
- **New status sensors never appeared after firmware/register changes**: the
  listener that adds newly-discovered status sensors was declared as an
  `async` function but called synchronously by Home Assistant, so it silently
  did nothing (visible as `RuntimeWarning: coroutine ... was never awaited`
  in the logs). It's now a plain synchronous callback.
- **Temperature sensors ignoring HA's unit system**: sensors tagged with
  `device_class: temperature` now always carry a proper `°C`/`°F` unit
  instead of passing through the device's raw unit string, so Home
  Assistant's automatic metric/imperial conversion works correctly.
- **"Online" binary sensor always showed online**: the API has no
  `deviceStatus`/online field at all. It now reflects whether the last poll
  actually succeeded instead of a hardcoded default.
- **Device page showed "0" as the model**: the `deviceType` field is a
  meaningless numeric code, not a model name, but was overriding the
  friendly default because non-empty strings (including `"0"`) are truthy.
  The device page now shows the device ID instead.
- **Fault sensor had no message**: the previous fault-message field names
  were guesses that didn't match the real API. The Fault binary sensor now
  calls the dedicated fault-info endpoint and surfaces the real
  human-readable description (`fault_message`) plus the numeric fault code
  (`fault_code`) as attributes.

### Added

- **Preset modes on the climate entity**: every mode the device reports
  (e.g. distinct heat sources like "Electric Heating" vs "Solar Heating")
  is now individually selectable via `preset_mode`, instead of being
  collapsed into Home Assistant's fixed `hvac_mode` categories.
- **Dry / Fan-only mode recognition**: `hvac_mode` mapping now recognises
  dehumidify and fan-only keywords instead of defaulting everything
  unrecognised to Auto.
- **Power/energy sensor classification**: dynamically-discovered status
  registers whose names indicate power, energy, current, or voltage are now
  tagged with the correct Home Assistant device class and unit (W, kWh, A,
  V), including `total_increasing` state class for energy so it can be
  added to the Energy dashboard.

## [1.0.0] - Initial release
