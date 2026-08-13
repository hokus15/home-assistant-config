# Home Assistant Config

Personal [Home Assistant](https://www.home-assistant.io/) configuration organized with packages, domain-based automations, and continuous validation against Home Assistant Core.

![GitHub last commit](https://img.shields.io/github/last-commit/hokus15/home-assistant-config?logo=github)
[![Build Status](https://github.com/hokus15/home-assistant-config/actions/workflows/home-assistant.yaml/badge.svg)](https://github.com/hokus15/home-assistant-config/actions)
[![Home Assistant version](https://img.shields.io/badge/dynamic/json?color=blue&label=Home%20Assistant&query=%24.version&url=https%3A%2F%2Fraw.githubusercontent.com%2Fhokus15%2Fhome-assistant-config%2Fmaster%2Fconfig%2FHA_VERSION.json&logo=home-assistant)](https://www.home-assistant.io/)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/hokus15/home-assistant-config?logo=github)

## Overview

This repository contains the configuration for a Home Assistant installation with:

- Raspberry Pi 4 as the main host.
- APC Back-UPS 650VA UPS.
- [Home Assistant Connect ZWA-2](https://www.home-assistant.io/connect/zwa-2/) for Z-Wave and Z-Wave Long Range devices.
- MQTT, Telegram, FreeDNS, TTS, cameras, presence, energy, swimming pool, electric car, and security integrations.
- [IOTConnect](https://github.com/hokus15/IOTConnect) as the external service used to monitor the car and publish Hyundai Ioniq telemetry to Home Assistant.

This is a personal configuration repository, not a turnkey setup. Entity IDs, secrets, devices, and automations are specific to this installation.

## Repository Layout

```text
config/
  configuration.yaml        Main Home Assistant configuration
  automations/              Active automations, split by use case
  automations/disabled/     Preserved but disabled automations
  packages/                 Modular configuration by functional domain
  packages/disabled/        Disabled packages
  blueprints/               Automation, script, and template blueprints
  www/                      Static assets served from /local
  secrets.fake.yaml         Safe secrets template used by CI validation
ci/
  check-home-assistant.ps1  Local Docker-based validation script
```

## Main Packages

- `alarm.yaml`: manual alarm control panel.
- `alerts.yaml`: persistent alerts for energy, pool, car, fence, and electrical status.
- `car.yaml`: Hyundai Ioniq telemetry, state, and charging logic through MQTT using data published by [IOTConnect](https://github.com/hokus15/IOTConnect).
- `comfort.yaml`: aggregated temperature sensors and comfort/sleep modes.
- `diagnostico_aa.yaml`: air conditioning diagnostics using derived sensors.
- `energy*.yaml`: energy monitoring, tariffs, UPS, EV charger, and appliances.
- `fence.yaml`: external gate state and control.
- `lights.yaml`: grouped and virtual lights for indoor and outdoor areas.
- `phones.yaml` and `presence.yaml`: phone state, guest mode, and presence tracking.
- `security.yaml`: cameras, motion detection, and supporting shell commands.
- `swimming_pool.yaml`: pump control, temperature, schedules, and optimization rules.
- `system.yaml`: system sensors, Node-RED watchdog, and operational commands.

## Automations

Active automations live in `config/automations/` and use a domain-based naming convention:

- `Alarm - ...`
- `Car - ...`
- `Comfort - ...`
- `Energy - ...`
- `Presence - ...`
- `Swimming Pool - ...`
- `System - ...`
- `Webhook - ...`

Automations that should not be loaded are kept in `config/automations/disabled/` with a `.disabled` extension.

## Secrets

Real secrets are not committed. Home Assistant loads runtime values from `config/secrets.yaml`, while the repository includes `config/secrets.fake.yaml` so CI can resolve every `!secret` reference.

When adding a new `!secret` reference, add a matching non-sensitive key to `config/secrets.fake.yaml` in the same change.

## Validation

The `Home Assistant Configuration Check` GitHub Action validates the configuration on every `push`, `pull_request`, and manual run. The matrix checks:

- The installed version declared in `config/.HA_VERSION`.
- The `stable` Home Assistant Core version.

It also verifies that every `!secret` key used by the configuration exists in `config/secrets.fake.yaml`.

Run the same configuration check locally with Docker:

```powershell
.\ci\check-home-assistant.ps1
```

Check a specific Home Assistant version:

```powershell
.\ci\check-home-assistant.ps1 -Version 2026.8.1
```

## Maintenance Conventions

- Keep domain-specific configuration in `config/packages/` when it clearly belongs to a functional area.
- Use `config/automations/` for active automations and move disabled ones to `config/automations/disabled/`.
- Update `config/secrets.fake.yaml` whenever a new secret is introduced.
- Validate locally or wait for the GitHub Action before deploying relevant configuration changes.
