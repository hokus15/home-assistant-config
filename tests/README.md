# What the Tests Verify

| File | Coverage | Limitations |
| --- | --- | --- |
| `test_heating.py` | Estimated heating demand, setpoint changes, invalid readings, configurable temperature hysteresis, invalid thresholds, manual threshold configuration, seasonal permission, effective presence, absence grace period, immediate arrival, missing presence data, holiday/absence priority, virtual climate auto/heat/off actions, saved manual targets, override priority, scheduled profiles, full-week timetable coverage, active temperature edits, missing control data, recovery predicates, mode confirmation, individual opening ages, messages listing recent openings, and alert repetition/acknowledgement/destination wiring. | Evaluates the actual YAML templates and conditions with simulated states; does not confirm boiler activity or run Home Assistant's trigger engine, alert lifecycle, timers, or device and Telegram services. |
| `test_heating_runtime.py` | Actual Home Assistant manual configuration of seasonal thresholds, immediate reevaluation on edits, invalid-range recovery, crossings after threshold edits, dashboard template rendering, and helper restoration after restart. | Runs in a container with simulated temperatures and notification services; does not control the thermostat or send real messages. |
| `test_security.py` | Alarm transitions, pauses, exclusions, time boundaries, camera resolution, and actual conversion with FFmpeg. | Timestamps are supplied to the macro; these tests do not exercise Home Assistant's time trigger. Actual conversion requires FFmpeg and FFprobe. |
| `test_energy_circuits.py` | Diagnosis and messages from the actual templates, available/unavailable/unknown device references, and YAML wiring between sensors, alerts, and the notifier. | These tests do not run the `alert` integration: they do not verify its timers, repetitions, or actual Telegram delivery. |
| `test_security_runtime.py` | Actual Home Assistant scripts and automations: the good-night routine, panel feedback, sensors, presence, buttons, exclusions, Folder Watcher events, recording classification, and data restoration. | Devices, Telegram, and conversion results are simulated. Restoration checks persisted sensors and the pause deadline; it does not reproduce the complete startup of a household installation. |

## Heating Mode Scenarios

`test_heating.py` renders the inline heating sensors, virtual-climate fields/actions and controller conditions, checks the manually configured profile/manual setpoint helpers, automatic override priority, schedule attribute changes while its state stays on, active-profile setpoint edits, fallback eco versus missing schedule data, confirmation of thermostat mode/setpoint, and every minute of all seven configured days. Local template tests simulate helper updates from virtual-climate actions; they do not instantiate the native climate platform, execute its service dispatch or the controller debounce, run the Home Assistant schedule engine, or exercise persistence.

## Heating Threshold Scenarios

Run `python /repo/tests/test_heating_runtime.py` inside the Home Assistant container. CI runs it for both configured versions. The test starts with a new configuration directory, verifies that both new threshold helpers start at 5 °C, configures them manually, edits the thresholds without changing the temperature, rejects an inverted range, corrects it, and crosses both edited thresholds. A second Home Assistant instance reuses the storage directory to verify that custom values survive restart.

## Security Scenarios

`Movimiento existente` is the name of the simulated sensor `binary_sensor.movimiento_existente`. The detection script builds its message from the sensor's `friendly_name`. The test checks that motion already present when arming is not reported, then causes an `off → on` transition on that same sensor and requires exactly `🚨 Movimiento detectado: Movimiento existente`.

The window that is initially open must appear in the arming notification. Open sensors must not produce new detections when rearming; subsequently closing and reopening the door must generate a detection.

Recordings enter through Folder Watcher events, using both the event bus and an event entity. The indoor camera first records without sending a notification; after its label changes, its next recording must produce a notification. Tests verify which files are converted and delivered, duplicate suppression, the upload delay, and fallback notifications for conversion and upload failures.

Persistence checks use a nonempty exclusion list and file history, and compare the restored deadline with the exact deadline saved.

The panel feedback scenario checks that a good-night request produces one controller execution and one arming notification. It also simulates loss of `internal_contexts` to verify that internal panel calls remain filtered. Manual rearming must still reset exclusions, and manual disarming must cancel pauses.

## Circuit Diagnosis Scenarios

Circuit tests distinguish disconnected devices from available relays, valid numeric power readings, and unknown states. They cover individual circuit outages, the requirement for at least two disconnected lower circuits before diagnosing a possible residual-current device (RCD) outage, and the available references needed to support that diagnosis.

Message tests verify that disconnected and communicating devices are reported correctly. Camera availability affects supplementary observations without changing the circuit diagnosis. YAML checks verify that each sensor uses the corresponding alert message and that alerts use the family notifier.

## Running the Tests

`./ci/check-security.ps1 -Version 2026.8.3` runs the security rules, conversion, and integration tests in isolated containers. CI also runs `test_energy_circuits.py`. Running `unittest discover` does not execute the integration scenario: run it with `python /repo/tests/test_security_runtime.py` inside the container.
