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
- `energia_aire_acondicionado_primera_planta.yaml`: energy monitoring and activity state for the first-floor air conditioning system.
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

### Local Validation

Requirements:

- PowerShell.
- Git available in `PATH`.
- Docker installed and running.
- Network access to pull `ghcr.io/home-assistant/home-assistant` images when they are not already cached.
- `config/secrets.fake.yaml` kept in sync with every `!secret` reference used by the configuration.

Run the same configuration check locally from the repository root:

```powershell
.\ci\check-home-assistant.ps1
```

Without parameters, the script validates two Home Assistant Core images:

- The installed version declared in `config/.HA_VERSION`.
- `stable`.

Check a specific Home Assistant version:

```powershell
.\ci\check-home-assistant.ps1 -Version 2026.8.1
```

Check multiple versions in one run:

```powershell
.\ci\check-home-assistant.ps1 -Version 2026.8.1,stable
```

The script validates the local working tree, not the remote `master` branch. It creates a temporary `.tmp-ha-ci/` directory, copies the Git-tracked `config/` files into it, replaces real secrets with `secrets.fake.yaml`, creates the camera directory expected by the configuration, normalizes camera paths for the container, and runs:

```powershell
python -m homeassistant --config ./config --script check_config
```

Because files are selected with `git ls-files config`, modified tracked files are included, but brand-new files are ignored until they are added to Git with `git add`.

## Maintenance Conventions

- Keep domain-specific configuration in `config/packages/` when it clearly belongs to a functional area.
- Use `config/automations/` for active automations and move disabled ones to `config/automations/disabled/`.
- Update `config/secrets.fake.yaml` whenever a new secret is introduced.
- Validate locally or wait for the GitHub Action before deploying relevant configuration changes.

## Configuration File Naming Convention

Use lowercase ASCII `snake_case` and Spanish, without accents, for user-managed configuration filenames. Apply the same ASCII rules used for entity IDs: only `a-z`, `0-9`, and `_`; replace non-ASCII characters with their plain equivalents and omit spaces and punctuation.

Keep the standard filenames required by Home Assistant unchanged, including `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `customize.yaml`, and `secrets.yaml`.

Package filenames use the following pattern and contain one functional responsibility:

```text
<subsistema>[_<alcance>].yaml
```

Examples:

```text
energia.yaml
energia_cargador_ev.yaml
energia_aire_acondicionado_primera_planta.yaml
piscina.yaml
iluminacion.yaml
seguridad.yaml
presencia.yaml
```

Organize files by functional responsibility rather than by an individual entity, integration implementation, or device. Avoid generic names such as `misc.yaml`, `utils.yaml`, and `configuracion2.yaml`, and do not encode versions in filenames. Disabled configuration keeps its functional filename and uses the `.disabled` extension.

## Entity Naming Convention

Entity IDs use lowercase ASCII `snake_case`: only `a-z`, `0-9`, and `_`. Replace non-ASCII characters with their plain equivalents (`ñ` to `n`, `ç` to `c`, accented vowels to unaccented vowels) and omit spaces and punctuation. The domain is selected by Home Assistant and is not repeated in the object ID. Names describe the purpose of an entity, rather than its wiring or integration implementation.

Use Spanish, without accents, for areas, devices, and functions that belong to this home. English is reserved for Home Assistant domains, integration identifiers, brands, models, and other external technical terms. For example, use `potencia`, `bateria`, and `estado`, but retain identifiers such as `wallpanel`, `ioniq`, and `zwave` when they identify external products or integrations.

For a physical device located in a single area, use:

```text
<domain>.<area>_<device>_<function>
```

This is a guide, not a mandatory number of segments. Omit unnecessary terms: `sensor.salon_temperatura` is preferable to `sensor.salon_sensor_temperatura`.

Examples:

```text
sensor.despacho_wallpanel_bateria
binary_sensor.cocina_puerta_porche
binary_sensor.habitacion_carlos_ventana
```

Do not repeat information already expressed by the domain: use `binary_sensor.cocina_puerta_porche`, not `binary_sensor.cocina_sensor_puerta_porche`, and `light.salon_principal`, not `light.salon_luz_principal`. Add a qualifier such as `principal`, `mesa`, `techo`, or `puerta_piscina` only when it distinguishes multiple entities of the same type.

Use singular nouns by default. Plural names are reserved for groups and true aggregates, such as `light.luces_interiores`.

Use these canonical function terms and do not introduce synonyms or abbreviations for them: `temperatura`, `humedad`, `potencia`, `energia`, `bateria`, `estado`, `activo`, `consumo`, `movimiento`, `presencia`, `ventana`, and `puerta`. The permitted technical abbreviations are `ev`, `tv`, `ups`, and `wifi`; use no other abbreviations unless they are an established external product or integration identifier.

`floor` is not included in entity IDs. Floors and areas model the physical location in Home Assistant; the ID only needs the functional area when it provides useful context.

Use the controlled or observed area for an entity, even when its physical controller belongs to multiple areas. A multi-channel controller must not impose its name on each channel:

```text
light.salon_principal
light.comedor_principal
light.suite_principal
light.escalera_principal
```

Assign these logical entities directly to their functional area. The underlying controller may have a composite device name or no area when no single area accurately represents it.

Keep entities that represent a functional subsystem, template, aggregate, or service under a stable functional prefix instead of an area/device prefix:

```text
sensor.energia_potencia_casa
sensor.piscina_tiempo_filtrado
binary_sensor.cargador_ev_estado
sensor.coche_ioniq_salud_bateria
```

Integration-generated diagnostics, maintenance controls, update entities, and mobile-app telemetry retain the integration or device prefix unless their entity ID is directly used as part of the home-facing configuration. Avoid renaming these solely for cosmetic consistency.

For entities defined in YAML, use a semantic `unique_id` that follows the same object-ID vocabulary, without the domain. For example, `binary_sensor.aire_acondicionado_primera_planta_activo` uses `aire_acondicionado_primera_planta_activo`. Treat user-defined `unique_id` values as immutable after deployment. Never modify integration-provided `unique_id` values.

Floor vocabulary is stable and uses `exterior`, `planta_baja`, and `primera_planta`. Area vocabulary is stable and uses the following object-ID forms: `salon`, `comedor`, `escalera`, `hueco_escalera`, `suite`, `cocina`, `coladuria`, `recibidor`, `despacho`, `aseo`, `bano_ninos`, `bano_suite`, `habitacion_carlos`, `habitacion_coque`, `jardin`, `entrada`, `barbacoa`, `caseta`, `piscina`, `climatizacion_planta_baja`, and `climatizacion_primera_planta`. Use `escalera` for entities that serve the staircase and `hueco_escalera` only for entities physically or functionally associated with the space below it.
