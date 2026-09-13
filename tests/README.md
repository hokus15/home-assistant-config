# What the Tests Verify

| File | Coverage | Limitations |
| --- | --- | --- |
| `test_security.py` | Alarm transitions, pauses, exclusions, time boundaries, camera resolution, and actual conversion with FFmpeg. | Timestamps are supplied to the macro; these tests do not exercise Home Assistant's time trigger. Actual conversion requires FFmpeg and FFprobe. |
| `test_energy_circuits.py` | Diagnosis and messages from the actual templates, available/unavailable/unknown device references, and YAML wiring between sensors, alerts, and the notifier. | These tests do not run the `alert` integration: they do not verify its timers, repetitions, or actual Telegram delivery. |
| `test_security_runtime.py` | Actual Home Assistant scripts and automations: the good-night routine, panel feedback, sensors, presence, buttons, exclusions, Folder Watcher events, recording classification, and data restoration. | Devices, Telegram, and conversion results are simulated. Restoration checks persisted sensors and the pause deadline; it does not reproduce the complete startup of a household installation. |

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
