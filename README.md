# Eco-Home Pool Heat Pump

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant integration for pool heat pumps controlled by the [Eco-Home app](https://play.google.com/store/apps/details?id=com.nnt.ehome) (`com.nnt.ehome`).

## Features

- **Climate entity** per zone — on/off, heat/cool mode, target temperature
- **Sensors** — current water temperature and setpoint per zone
- **Status query sensors** — live refrigerant circuit data: suction/discharge temps, plate heat exchanger temps, ambient temperature, variable-speed pump speed & feedback, valve outputs, and any other registers the device exposes (disabled by default, opt-in per entity)
- **Switch** — master all-zones power
- **Binary sensors** — fault alert, cloud connectivity status
- Cloud polling (default every **30 seconds**, adjustable via Configure)
- Automatic token refresh

## Installation via HACS

1. In HACS → Integrations → top-right menu → **Custom repositories**
2. Add `https://github.com/itchannel/ha-echohomepool` as type **Integration**
3. Find **Eco-Home Pool Heat Pump** in HACS and install
4. Restart Home Assistant

## Manual installation

Copy `custom_components/eco_home/` into your HA `config/custom_components/` directory and restart.

## Setup

1. **Settings → Integrations → Add Integration → Eco-Home Pool Heat Pump**
2. Enter your Eco-Home app **email** and **password**
3. Select your device from the dropdown
4. Optionally adjust the polling interval via **Configure** (default: 30 s, minimum: 10 s)

## Entities

### Always enabled

| Entity | Type | Description |
|---|---|---|
| `climate.heat_pump_zone_1` | Climate | Zone 1 thermostat (on/off, heat/cool, set temp) |
| `climate.heat_pump_zone_2` | Climate | Zone 2 (if dual-zone) |
| `sensor.water_temperature_zone_1` | Sensor | Current water temperature |
| `sensor.target_temperature_zone_1` | Sensor | Active setpoint |
| `switch.power` | Switch | All-zones master power |
| `binary_sensor.fault` | Binary sensor | Fault / problem indicator |
| `binary_sensor.online` | Binary sensor | Cloud connectivity |

### Disabled by default — enable as needed

| Entity | Type | Description |
|---|---|---|
| `sensor.water_temperature_zone_2` | Sensor | Zone 2 current temp (dual-zone units) |
| `sensor.target_temperature_zone_2` | Sensor | Zone 2 setpoint (dual-zone units) |
| `sensor.<param_name>` | Sensor | One entity per status register returned by the device — e.g. suction temperature, plate heat exchanger in/out temps, ambient temperature, pump target speed, pump feedback speed, electromagnetic valve outputs |

To enable status sensors: **Settings → Entities**, search for your device, toggle the ones you want.

The exact set of status sensors depends on your specific unit's firmware. They are created dynamically from whatever registers the cloud API returns, so a firmware update may add new ones automatically.

## Polling

Both the main device state and the status parameter list are fetched on every poll cycle (default 30 s). The two requests run in parallel. If the status parameter fetch fails it is treated as non-fatal — the climate/switch/binary sensor entities continue to work normally.

## Compatibility

Tested against Eco-Home app v2.0.23 (`ehome.ne01.com` cloud API). Works with any pool heat pump provisioned through the Eco-Home app.
