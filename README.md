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
- `seguridad_alarma.yaml`: native alarm orchestration with label-based detector membership and reusable scripts. Native control starts automatically with Home Assistant.
- `alerts.yaml`: persistent alerts for energy waste, pool operation, and the entrance gate.
- `energia_supervision_circuitos.yaml`: probable circuit and lower differential outages, with family Telegram alerts. See [circuit monitoring](docs/electrical_circuit_monitoring.md) for the panel diagram, coverage and limitations.
- `car.yaml`: Hyundai Ioniq telemetry, state, and charging logic through MQTT using data published by [IOTConnect](https://github.com/hokus15/IOTConnect).
- `confort.yaml`: environmental sensors, shared floor/home temperature averages, weather, and sleep modes.
- `calefaccion.yaml`: virtual climate control, Tado readings, seasonal thresholds/permission, confirmed presence, the 24-hour mean, profile/manual setpoints, and the weekly schedule.
- `energia_aire_acondicionado_primera_planta.yaml` and `energia_aire_acondicionado_planta_baja.yaml`: energy monitoring and activity state for the first-floor and ground-floor air conditioning systems.
- `energia*.yaml`, `energy.yaml`, and `energy_tariffs.yaml`: energy monitoring and tariffs.
- `electrodomesticos.yaml`: energy monitoring and activity state for kitchen and laundry appliances.
- `cargador_ev.yaml`: EV charger control and monitoring.
- `energia_despacho_cargador_portatiles.yaml`: monitoring for the portable-device charger.
- `barrera_entrada.yaml`: sliding metal garden entrance barrier state and control.
- `lights.yaml`: grouped and virtual lights for indoor and outdoor areas.
- `phones.yaml` and `presence.yaml`: phone state, guest mode, and presence tracking.
- `seguridad.yaml`: cameras, motion detection, and supporting shell commands.
- `sistema_sai_hueco_escalera.yaml`: stairwell UPS status, battery state, and mains availability.
- `piscina.yaml`: pool pump and lighting MQTT controls, water-temperature fallback, filtration calculation, schedules, and energy monitoring.
- `system.yaml`: system sensors, Node-RED watchdog, and operational commands.

## Automations

Active automations live in `config/automations/`. Their filenames follow the automation filename convention below. Automations that should not be loaded are kept in `config/automations/disabled/` with a `.disabled` extension.

## Heating and Presence

`input_boolean.calefaccion_temporada_activo`, available in the Climatizacion dashboard, stores seasonal permission independently of the thermostat's actual mode. The two temperature automations enable it below `input_number.calefaccion_temporada_temperatura_activar` (configure from the dashboard, e.g. 18.5 °C) and disable it above `input_number.calefaccion_temporada_temperatura_desactivar` (e.g. 20 °C), using the 24-hour mean. Between those thresholds (including equality), it retains its previous value. You can also change it manually; a later temperature threshold crossing, threshold edit, startup, or sensor recovery can update it again.

The Calefacción view in the Climatizacion dashboard exposes both thresholds, seasonal permission, the thermostat, temperatures, and opening alerts. Values change in steps of 0.1 °C and persist across restarts. Both thresholds are configured manually in the dashboard. No initialization automation, flag, or `initial` value is used; new helpers start at their minimum of 5 °C and saved settings survive restart. Equal, inverted, or unavailable thresholds suspend automatic season/thermostat changes until corrected; the dashboard shows a short warning for invalid thresholds. Editing either threshold reevaluates the current mean immediately.

Heating uses four distinct concepts:

| Concept | Meaning |
| --- | --- |
| Modo de funcionamiento | Apagado (`off`), automático (`auto`), or manual (`heat`) on the virtual climate. |
| Perfil de temperatura | Ausente, vacaciones, eco, normal, confort, or caliente; selected by automatic rules or the schedule. |
| Consigna | The target temperature supplied by a profile or set manually. |
| Umbrales de temporada | Mean-temperature boundaries that enable or disable seasonal permission. |

`config/packages/calefaccion.yaml` defines `climate.calefaccion`, six profile setpoints, a separate manual setpoint, the weekly schedule, and control-state sensors. Configure all setpoints manually from the dashboard. Suggested values are 14 °C for ausente and vacaciones, 16 °C for eco, 18 °C for normal, 19 °C for confort, and 20 °C for caliente. The existing `input_number.calefaccion_temperatura_<perfil>` and `input_number.calefaccion_temperatura_manual` entity IDs are retained to preserve saved settings. No initializer, initialization flag, or `initial` value is used. New helpers start at their minimum of 5 °C; previously saved values survive restart.

`schedule.calefaccion` assigns a `perfil` attribute to each block:

| Days | Eco | Normal | Confort |
| --- | --- | --- | --- |
| Monday-Friday | 00:00-06:00, 06:45-12:00, 23:00-24:00 | 12:00-14:00 | 06:00-06:45, 14:00-23:00 |
| Saturday-Sunday | 00:00-11:00, 23:00-24:00 | 11:00-14:00 | 14:00-23:00 |

Block ends are exclusive. Adjacent blocks keep the schedule on and change its `perfil` attribute. All seven days are covered. An inactive gap falls back to eco; a missing schedule or invalid active profile blocks scheduled control. Schedule blocks accept eco, normal, confort, or caliente; ausente and vacaciones are automatic overrides. The schedule is defined in YAML, so edit `config/packages/calefaccion.yaml` and reload schedules to change its blocks. Profile setpoints remain editable in the dashboard.

`climate.calefaccion` is the user-facing thermostat, implemented with native Template Climate. `input_select.calefaccion_funcionamiento` persists its requested mode: `off`, `auto`, or `heat`, displayed as Apagado, Automático, and Manual. New installations start off; select Automático to follow the schedule. The virtual entity displays Tado's measured temperature and the effective setpoint, falling back to the saved manual setpoint when no effective setpoint applies. Its attributes are `modo_funcionamiento`, `perfil_activo`, `estado_control`, and `consigna_manual`. It does not invent a boiler `hvac_action` reading.

Editing the virtual thermostat's temperature saves the manual setpoint and selects manual (`heat`). If the same API request explicitly supplies `hvac_mode: auto` or `off`, that requested mode is preserved while the manual setpoint is saved. Manual ignores schedule changes but respects seasonal permission, holidays, and confirmed absence. When an override ends, manual recovers its saved setpoint and automatic recovers the current scheduled profile.

`sensor.calefaccion_estado` expresses the effective control decision: apagado, fuera_temporada, vacaciones, ausente, manual, a scheduled profile, or sin_datos. Priority is explicit apagado, fuera_temporada, vacaciones, ausente, then manual or the schedule. Explicit off remains effective even when automatic-control data is missing. `sin_datos` prevents new device commands. Invalid seasonal thresholds also suspend automatic/manual heating decisions.

`sensor.calefaccion_perfil_programado` identifies the scheduled profile. `sensor.calefaccion_perfil_activo` identifies one of the six actual profiles; it is ninguno for manual, explicit shutdown, or outside season, and sin_datos when the decision is unknown. `sensor.calefaccion_temperatura_objetivo` is the effective setpoint, including manual, and is unavailable when no setpoint applies. All templates are inline; no heating macros are used.

`binary_sensor.calefaccion_presencia` follows `group.invitado_y_familia`, with a five-minute off delay and immediate arrival detection. Unknown or unavailable group states cancel pending absence confirmation and block presence-based control. Holidays do not require presence data. A restart or template reload restarts the absence countdown. This configuration consumes `switch.holiday`; it does not add calendar-to-holiday synchronization.

`calefaccion_recibidor_aplicar_modo` replaces `calefaccion_recibidor_controlar_por_presencia` as the only automatic writer to Tado. It applies the physical HVAC mode and setpoint together, or turns Tado off for apagado/fuera_temporada. It listens to control-state and setpoint updates, startup, and device recovery. It reads the selected setpoint helper directly to avoid using an old displayed value during a transition, and coalesces split virtual-control updates for 100 ms. Matching settings generate no device call. Mode and setpoint are confirmed before logging. Direct manual edits on Tado persist until the next control event. Tado is configured to keep manual commands until its schedule is explicitly resumed; HA owns the weekly schedule and does not resume Tado's schedule.

Seasonal permission restores its previous state and is independent of the requested functioning mode. On first installation it starts off; enable it manually if heating is needed while the mean is between the seasonal thresholds. Deploy the complete configuration, restart HA, then refresh the dashboard. The Calefacción view shows functioning mode, control state, active/scheduled profiles, setpoints, season controls, presence, history, and opening alerts.

Heating entities have not yet been deployed: YAML `unique_id` values match their semantic entity IDs, including `calefaccion_estado` and `calefaccion_perfil_programado`. No entity registry migration is required. All heating-only definitions, recorder/logbook settings, and the 24-hour mean belong to `config/packages/calefaccion.yaml`; shared instantaneous floor/home averages remain in `confort.yaml` and may still reference the thermostat's temperature as one of their inputs.

### Open Door and Window Heating Alerts

`binary_sensor.energy_waste_alert` activates when estimated heating is active and at least one entity labelled `comprobacion_desperdicio_energetico` has been continuously open for more than ten minutes. Each opening is timed independently; `now()` refreshes the template every minute, and sensor changes also update it. If heating starts with an already overdue opening, no additional ten-minute delay is required.

`alert.energy_waste_alert` handles delivery, ten-minute repetitions, and acknowledgement directly. `skip_first: false` sends the first message as soon as the condition is met, without another ten-minute delay. The Telegram acknowledgement button silences the current alert episode. If the condition clears and becomes true again, a new episode can notify immediately, even if fewer than ten minutes have passed since the previous message. There is no separate notification automation or timestamp helper.

Messages retain the existing wording and list **all** currently open labelled entities, including those open for less than ten minutes. Destinations remain recibidor, suite, despacho, and Telegram. Minute-based template updates can add approximately one minute to threshold detection. Opening age uses each entity's `last_changed`; a Home Assistant restart or a sensor becoming unavailable can restart that age, so opening-duration persistence is not guaranteed.

## Secrets

Real secrets are not committed. Home Assistant loads runtime values from `config/secrets.yaml`, while the repository includes `config/secrets.fake.yaml` so CI can resolve every `!secret` reference.

When adding a new `!secret` reference, add a matching non-sensitive key to `config/secrets.fake.yaml` in the same change.

### Secret Naming Convention

Secret keys use lowercase ASCII Spanish `snake_case` and describe the protected value's purpose, not its implementation. Use:

```text
<subsystem>[_<area>]_<resource_or_function>[_<qualifier>]_<field_or_operation>
```

Use these final fields:

| Value type | Field |
| --- | --- |
| URL or endpoint | `url` |
| Network host | `host` |
| Network port | `puerto` |
| Username | `usuario` |
| Password | `contrasena` |
| Access token | `token` |
| API key | `api_key` |
| OAuth client identifier | `client_id` |
| OAuth client secret | `client_secret` |
| Command operation | `activar`, `desactivar`, or `estado` |

Retain established external technical identifiers when necessary, such as `ptz`, `url`, `db`, `mjpeg`, and an integration or product identifier. A URL qualifier precedes the final `url`; for example, use `imagen_estatica_url` and `stream_mjpeg_url`.

```text
camara_recibidor_deteccion_movimiento_activar
camara_piscina_deteccion_movimiento_estado
camara_salon_ptz_posicion_predefinida_principal
recorder_db_url
camara_caseta_imagen_estatica_url
camara_caseta_stream_mjpeg_url
```

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

The script validates the local working tree, not the remote `master` branch. It creates a temporary `.tmp-ha-ci/` directory, copies tracked and untracked non-ignored `config/` files into it, replaces real secrets with `secrets.fake.yaml`, creates the camera directory expected by the configuration, normalizes camera paths for the container, and runs:

```powershell
python -m homeassistant --config ./config --script check_config
```

New configuration files are included without staging them. Ignored files are excluded.

Run the security behavior tests with `./ci/check-security.ps1`. They exercise the Home Assistant scripts and automations with simulated Telegram/device services and test video processing with FFmpeg. They do not connect to the live installation or send notifications. The same tests run in CI for both Home Assistant versions.

## Maintenance Conventions

- Keep domain-specific configuration in `config/packages/` when it clearly belongs to a functional area.
- Use `config/automations/` for active automations and move disabled ones to `config/automations/disabled/`.
- Update `config/secrets.fake.yaml` whenever a new secret is introduced.
- Validate locally or wait for the GitHub Action before deploying relevant configuration changes.

### Comment Language Convention

Write all explanatory comments in English, including comments in configuration files, templates, scripts, tests, CI tooling, and disabled code.

## Commit Message Convention

When preparing a commit message or Commitizen answers for this repository, use this section as the project convention for `scope`.

For staged changes confined to one Home Assistant area, use that area's canonical lowercase ASCII Spanish `snake_case` name, such as `despacho`, `cocina`, or `habitacion_carlos`. Determine the affected area from the changed entities, devices, and automation targets, following the [entity naming convention](#entity-naming-convention) and the canonical area vocabulary documented at the end of this README. Base the scope on what the change affects; a reference to an entity in another area does not by itself make that area part of the scope.

For changes spanning multiple areas or affecting global behavior, use the shared functional subsystem, such as `energia`, `seguridad`, or `presencia`. For repository tooling or infrastructure, use the affected component, such as `ci`. If no single meaningful scope describes the staged changes, omit it.

Examples:

```text
fix(despacho): correct wallpanel charging threshold
feat(seguridad): add alarm controls across monitored areas
ci(ci): update configuration validation workflow
```

## Configuration File Naming Convention

Use lowercase ASCII `snake_case` and Spanish, without accents, for user-managed configuration filenames. Apply the same ASCII rules used for entity IDs: only `a-z`, `0-9`, and `_`; replace non-ASCII characters with their plain equivalents and omit spaces and punctuation.

Keep the standard filenames required by Home Assistant unchanged, including `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `customize.yaml`, and `secrets.yaml`.

Package filenames use the following pattern and contain one functional responsibility:

```text
<subsystem>[_<scope>].yaml
```

Examples:

```text
energia.yaml
cargador_ev.yaml
energia_aire_acondicionado_primera_planta.yaml
energia_aire_acondicionado_planta_baja.yaml
piscina.yaml
iluminacion.yaml
seguridad.yaml
presencia.yaml
```

Organize files by functional responsibility rather than by an individual entity, integration implementation, or device. Avoid generic names such as `misc.yaml`, `utils.yaml`, and `configuracion2.yaml`, and do not encode versions in filenames. Disabled configuration keeps its functional filename and uses the `.disabled` extension.

### Automation File Naming Convention

Automation filenames use lowercase ASCII `snake_case`, Spanish without accents, and the following pattern:

```text
<subsystem>[_<scope>]_<event_or_action>.yaml
```

`<subsystem>` identifies the functional domain, `<scope>` is included when it disambiguates the target area or device, and `<event_or_action>` describes the triggering event or intended action. Do not prefix the filename with `automation` and do not repeat a Home Assistant entity domain.

Examples:

```text
energia_cambio_tarifa.yaml
coche_carga_apagar_programada.yaml
piscina_depuradora_encender.yaml
wallpanel_despacho_gestion_cargador.yaml
sistema_sai_notificar_bateria_reemplazar.yaml
```

Technical external identifiers such as `wallpanel`, `ioniq`, and `zwave` are permitted when they identify the integration or product. Disabled automations retain the same base filename and append `.disabled`, for example `energia_cambio_tarifa.yaml.disabled`.

Automation `id` values use the same lowercase ASCII `snake_case` vocabulary and pattern as the filename, without the `.yaml` extension. For a new automation, the `id` normally matches the filename stem:

```yaml
- id: wallpanel_despacho_gestion_cargador
```

## Entity Naming Convention

Entity IDs use lowercase ASCII `snake_case`: only `a-z`, `0-9`, and `_`. Replace non-ASCII characters with their plain equivalents (`ñ` to `n`, never `ny`; `ç` to `c`; accented vowels to unaccented vowels) and omit spaces and punctuation. The domain is selected by Home Assistant and is not repeated in the object ID. Names describe the purpose of an entity, rather than its wiring or integration implementation.

Use Spanish, without accents, for areas, devices, and functions that belong to this home. English is reserved for Home Assistant domains, integration identifiers, brands, models, and other external technical terms. For example, use `potencia`, `bateria`, and `estado`, but retain identifiers such as `wallpanel`, `ioniq`, and `zwave` when they identify external products or integrations.

For every enabled entity tied to a physical device or a single-purpose detector assigned to one area, use:

```text
<domain>.<area>_<device_or_type>[_<function>]
```

The area is mandatory, even when the device is unique in the home. Omit the function only for the primary control or state of the device, such as `switch.coladuria_secadora` or `binary_sensor.despacho_movimiento`; include it for each measurement, state, diagnostic, maintenance control, or update entity, such as `sensor.coladuria_secadora_potencia`, `binary_sensor.coladuria_secadora_activo`, and `sensor.despacho_movimiento_temperatura`.

Examples:

```text
sensor.despacho_wallpanel_bateria
binary_sensor.cocina_puerta_porche
binary_sensor.habitacion_carlos_ventana
```

### Single-Purpose Detectors

For a single-purpose detector, its detected type is the `<device_or_type>` segment. Do not add the generic term `sensor` to the object ID. This applies to `movimiento`, `ventana`, `puerta`, and `persiana` when they identify the detector's primary purpose.

```text
<domain>.<area>_<type>[_<function>]
```

Use `binary_sensor.despacho_movimiento`, `sensor.despacho_movimiento_iluminancia`, and `sensor.despacho_movimiento_temperatura`; do not use `despacho_sensor_movimiento` for that detector. Use `sensor` in the object ID only when it is necessary to distinguish distinct physical devices in the same area.

The following forms are normative and take precedence over the general grammar when it could be interpreted differently:

| Physical element | Primary entity | Additional entity |
| --- | --- | --- |
| Motion detector | `binary_sensor.<area>_movimiento` | `sensor.<area>_movimiento_<function>` |
| Door detector | `binary_sensor.<area>_puerta[_<qualifier>]` | — |
| Window detector | `binary_sensor.<area>_ventana[_<qualifier>]` | — |
| Shutter detector | `binary_sensor.<area>_persiana[_<qualifier>]` | — |

### Alarm Arming Helpers

An entity that detects a physical event and a helper that decides whether that event arms or triggers the alarm have different purposes and must not share the same object ID. For an area-specific alarm helper, use:

```text
input_boolean.<area>_alarma_<event>_activo
```

For example, use `binary_sensor.despacho_movimiento` for the physical detector and `input_boolean.despacho_alarma_movimiento_activo` for the alarm arming helper. If a helper controls a different subsystem, use that subsystem instead of `alarma`.

Do not repeat information already expressed by the domain: use `binary_sensor.cocina_puerta_porche`, not `binary_sensor.cocina_sensor_puerta_porche`, and `light.salon_principal`, not `light.salon_luz_principal`. Add a qualifier such as `principal`, `mesa`, `techo`, or `puerta_piscina` only when it distinguishes multiple entities of the same type.

Use singular nouns by default. Plural names are reserved for groups and true aggregates, such as `light.luces_interiores`.

Use these canonical function terms and do not introduce synonyms or abbreviations for them: `temperatura`, `humedad`, `iluminancia`, `potencia`, `energia`, `bateria`, `estado`, `activo`, `consumo`, `movimiento`, `presencia`, `ventana`, and `puerta`. The permitted technical abbreviations are `ev`, `tv`, `sai`, `ups`, and `wifi`; use no other abbreviations unless they are an established external product or integration identifier.

`floor` is not included in entity IDs. Areas model the physical location in Home Assistant and are required for every enabled entity tied to a physical device with one assigned area. Do not add an area only when the entity is global, virtual, aggregated, or belongs to a device with no single functional area.

Use the controlled or observed area for an entity, even when its physical controller belongs to multiple areas. A multi-channel controller must not impose its name on each channel:

```text
light.salon_principal
light.comedor_principal
light.suite_principal
light.escalera_principal
```

Assign these logical entities directly to their functional area. The underlying controller may have a composite device name or no area when no single area accurately represents it.

Keep global, virtual, aggregate, and service entities that are not tied to one physical device in one area under a stable functional prefix instead of an area/device prefix:

```text
sensor.energia_potencia_casa
sensor.piscina_tiempo_filtrado
binary_sensor.coladuria_cargador_ev_estado
sensor.coche_ioniq_salud_bateria
```

Templates tied to a physical device follow that device's area and device prefix. A template is not an exception merely because it is YAML-defined.

Enabled integration-generated diagnostics, maintenance controls, update entities, and mobile-app telemetry follow the same entity-ID convention when they are migrated. Disabled integration-generated entities retain their integration-provided entity ID until they are enabled, at which point they are renamed as part of enabling them. Never modify integration-provided `unique_id` values; rename only the entity ID through Home Assistant's UI.

For entities defined in YAML, use a semantic `unique_id` that follows the same object-ID vocabulary, without the domain. For example, `binary_sensor.aire_acondicionado_primera_planta_activo` uses `aire_acondicionado_primera_planta_activo`.

User-defined `unique_id` values should normally remain stable after deployment. During an intentional naming migration, a YAML-defined `unique_id` may be changed to match the migrated object-ID vocabulary, but only as part of the same migration that renames the entity in Home Assistant, removes or resolves the old entity registry entry, updates helpers, dashboards, automations, recorder includes, and customizations, and verifies that no duplicate `_2` entity is created. Never modify integration-provided `unique_id` values.

## MQTT Topic Naming Convention

MQTT topics identify device endpoints. Fixed devices that belong to the home use the following namespace:

```text
casa/<house_name>/<area>/<device>/<protocol_prefix>/<endpoint>
```

Use lowercase ASCII Spanish `snake_case` for the semantic segments (`<house_name>`, `<area>`, and `<device>`). `<house_name>` is a stable installation identifier, not a street address. Do not include a Home Assistant domain such as `switch`, `light`, or `sensor` in a topic: the topic identifies the physical endpoint, not its Home Assistant representation. For Tasmota-compatible devices, retain protocol-defined segments exactly as the firmware defines them, including `cmnd`, `stat`, `tele`, `POWER`, `SENSOR`, and `LWT`.

```text
casa/<house_name>/piscina/depuradora/cmnd/POWER
casa/<house_name>/piscina/depuradora/stat/POWER
casa/<house_name>/piscina/depuradora/tele/SENSOR
casa/<house_name>/piscina/iluminacion/cmnd/POWER
casa/<house_name>/piscina/iluminacion/stat/POWER
casa/<house_name>/piscina/iluminacion/tele/LWT
```

Mobile clients and external application contracts use:

```text
<subsystem>/<device>/<kind>/<resource>
```

Use `telemetria` for reported state and `comando` for a command consumed by the client. The semantic segments use lowercase ASCII Spanish `snake_case`; product and client identifiers retain their established external form.

```text
coche/ioniq/telemetria/estado
coche/ioniq/telemetria/bateria
coche/ioniq/telemetria/ubicacion
telefono/hokus/comando/decir
```

Floor vocabulary is stable and uses `exterior`, `planta_baja`, and `primera_planta`. Area vocabulary is stable and uses the following object-ID forms: `salon`, `comedor`, `escalera`, `hueco_escalera`, `suite`, `cocina`, `coladuria`, `recibidor`, `despacho`, `aseo`, `bano_ninos`, `bano_suite`, `habitacion_carlos`, `habitacion_coque`, `jardin`, `entrada`, `porche`, `barbacoa`, `caseta`, `piscina`, `climatizacion_planta_baja`, and `climatizacion_primera_planta`. Use `escalera` for entities that serve the staircase and `hueco_escalera` only for entities physically or functionally associated with the space below it.
