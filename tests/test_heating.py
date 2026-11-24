"""Exercise heating templates with simulated Matter states, without device calls."""

import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2.sandbox import ImmutableSandboxedEnvironment
import yaml


ROOT = Path(__file__).resolve().parents[1]
THERMOSTAT = 'climate.recibidor_termostato'
MEAN = 'sensor.home_temperature_stats'
ACTIVE = 'binary_sensor.recibidor_termostato_activo'
TEMPERATURE = 'sensor.recibidor_termostato_temperatura'
TARGET = 'sensor.recibidor_termostato_temperatura_objetivo'
PERMISSION = 'input_boolean.calefaccion_temporada_activo'
PRESENCE = 'group.invitado_y_familia'
HOLIDAY = 'switch.holiday'
ALERT = yaml.safe_load((ROOT / 'config/packages/alerts.yaml').read_text(encoding='utf-8'))['template'][0]['binary_sensor'][0]
HEATING = yaml.safe_load((ROOT / 'config/packages/confort.yaml').read_text(encoding='utf-8'))['template'][0]['binary_sensor'][0]
AUTOMATIONS = [
    yaml.safe_load(path.read_text(encoding='utf-8'))[0]
    for path in sorted((ROOT / 'config/automations').glob('calefaccion_recibidor_*_por_temperatura_media.yaml'))
]
CONTROL = yaml.safe_load((ROOT / 'config/automations/calefaccion_recibidor_controlar_por_presencia.yaml').read_text(encoding='utf-8'))[0]


class HeatingTemplates(unittest.TestCase):
    def setUp(self):
        self.states = {
            THERMOSTAT: 'heat', MEAN: '18', ACTIVE: 'on',
            TEMPERATURE: '19.0', TARGET: '20.0',
            PERMISSION: 'on', PRESENCE: 'home', HOLIDAY: 'off',
        }
        self.openings = [SimpleNamespace(state='on')]
        self.env = ImmutableSandboxedEnvironment()
        self.env.filters['expand'] = lambda entities: entities
        self.env.globals.update(
            has_value=lambda entity: self.states.get(entity, 'unknown') not in ('unknown', 'unavailable'),
            is_state=lambda entity, value: self.states.get(entity, 'unknown') == value,
            states=lambda entity: self.states.get(entity, 'unknown'),
            label_entities=lambda label: self.openings,
            is_number=self.is_number,
        )

    @staticmethod
    def is_number(value):
        try:
            return math.isfinite(float(value))
        except (ValueError, TypeError):
            return False

    def evaluate(self, source, **variables):
        return self.env.from_string(source).render(**variables).strip() == 'True'

    def condition_passes(self, condition):
        if condition['condition'] == 'state':
            return self.states[condition['entity_id']] == condition['state']
        if condition['condition'] == 'template':
            return self.evaluate(condition['value_template'])
        if condition['condition'] == 'numeric_state':
            value = self.states[condition['entity_id']]
            if not self.is_number(value):
                return False
            return (('above' not in condition or float(value) > condition['above'])
                    and ('below' not in condition or float(value) < condition['below']))
        self.fail(f'Unsupported condition: {condition}')

    def update_permission(self):
        for automation in AUTOMATIONS:
            if all(self.condition_passes(c) for c in automation['conditions']):
                action = automation['actions'][0]
                self.assertEqual(action['target']['entity_id'], PERMISSION)
                self.states[PERMISSION] = 'on' if action['action'] == 'input_boolean.turn_on' else 'off'

    def requested_mode(self):
        if not all(self.condition_passes(c) for c in CONTROL['conditions']):
            return None
        mode = self.env.from_string(CONTROL['actions'][0]['variables']['desired_mode']).render().strip()
        if not self.evaluate(CONTROL['actions'][1]['value_template'], desired_mode=mode):
            return None
        return mode

    def test_waste_alert_needs_estimated_heating_and_an_open_door(self):
        self.assertTrue(self.evaluate(ALERT['state']))
        self.states[ACTIVE] = 'off'
        self.assertFalse(self.evaluate(ALERT['state']))
        self.states[ACTIVE] = 'on'
        self.openings[0].state = 'off'
        self.assertFalse(self.evaluate(ALERT['state']))

    def test_heating_estimate_changes_at_setpoint(self):
        for current, expected in [(19.9, True), (20.0, False), (20.1, False)]:
            with self.subTest(current=current):
                self.states[TEMPERATURE] = str(current)
                self.assertTrue(self.evaluate(HEATING['availability']))
                self.assertEqual(self.evaluate(HEATING['state']), expected)

    def test_off_is_inactive_even_below_setpoint_or_without_temperatures(self):
        self.states[THERMOSTAT] = 'off'
        for value in ['19.0', 'unknown']:
            self.states[TEMPERATURE] = value
            self.states[TARGET] = '20.0' if value == '19.0' else 'unknown'
            self.assertTrue(self.evaluate(HEATING['availability']))
            self.assertFalse(self.evaluate(HEATING['state']))

    def test_missing_or_invalid_temperatures_are_unavailable_in_heat_mode(self):
        for entity in [TEMPERATURE, TARGET]:
            for bad in [None, 'unknown', 'unavailable', 'bad', float('nan'), float('inf')]:
                with self.subTest(entity=entity, value=bad):
                    original = self.states[entity]
                    self.states[entity] = bad
                    self.assertFalse(self.evaluate(HEATING['availability']))
                    self.assertFalse(self.evaluate(HEATING['state']))
                    self.states[entity] = original

    def test_schedule_setpoint_change_updates_estimated_demand(self):
        self.states[TARGET] = '18'
        self.assertFalse(self.evaluate(HEATING['state']))
        self.states[TARGET] = '21'
        self.assertTrue(self.evaluate(HEATING['state']))

    def test_unavailable_estimate_cannot_raise_a_waste_alert(self):
        for state in ['unknown', 'unavailable']:
            with self.subTest(state=state):
                self.states[THERMOSTAT] = state
                self.assertFalse(self.evaluate(HEATING['availability']))
                self.assertFalse(self.evaluate(HEATING['state']))
                self.states[ACTIVE] = 'unavailable'
                self.assertFalse(self.evaluate(ALERT['availability']))
                self.assertFalse(self.evaluate(ALERT['state']))

    def test_recovery_trigger_needs_both_entities_available(self):
        self.assertEqual(len(AUTOMATIONS), 2)
        for automation in AUTOMATIONS:
            trigger = next(t['value_template'] for t in automation['triggers'] if t['trigger'] == 'template')
            for entity in [PERMISSION, MEAN]:
                for bad in ['unknown', 'unavailable']:
                    with self.subTest(automation=automation['id'], entity=entity, state=bad):
                        original = self.states[entity]
                        self.states[entity] = bad
                        self.assertFalse(self.evaluate(trigger))
                        self.states[entity] = original
                        self.assertTrue(self.evaluate(trigger))

    def test_manual_mode_changes_do_not_rearm_recovery_trigger(self):
        for automation in AUTOMATIONS:
            trigger = next(t['value_template'] for t in automation['triggers'] if t['trigger'] == 'template')
            results = []
            for state in ['heat', 'off', 'heat']:
                self.states[THERMOSTAT] = state
                results.append(self.evaluate(trigger))
            self.assertEqual(results, [True, True, True])

    def test_confirmation_requires_the_requested_mode(self):
        confirmation = next(a['wait_template'] for a in CONTROL['actions'] if 'wait_template' in a)
        for desired in ['heat', 'off']:
            for state in ['unknown', 'unavailable', 'off', 'heat']:
                with self.subTest(desired=desired, state=state):
                    self.states[THERMOSTAT] = state
                    self.assertEqual(self.evaluate(confirmation, desired_mode=desired), state == desired)

    def test_temperature_hysteresis_keeps_permission_between_thresholds(self):
        for mean, previous, expected in [
            ('18.4', 'off', 'on'), ('20.1', 'on', 'off'),
            ('18.5', 'off', 'off'), ('20', 'on', 'on'),
            ('19', 'on', 'on'), ('19', 'off', 'off'),
            ('unknown', 'on', 'on'), ('unavailable', 'off', 'off'),
        ]:
            with self.subTest(mean=mean, previous=previous):
                self.states.update({MEAN: mean, PERMISSION: previous})
                self.update_permission()
                self.assertEqual(self.states[PERMISSION], expected)

    def test_presence_only_heats_with_seasonal_permission(self):
        for permission in ['on', 'off']:
            for presence in ['home', 'not_home']:
                for mode in ['heat', 'off']:
                    with self.subTest(permission=permission, presence=presence, mode=mode):
                        self.states.update({PERMISSION: permission, PRESENCE: presence, THERMOSTAT: mode})
                        desired = 'heat' if permission == 'on' and presence == 'home' else 'off'
                        self.assertEqual(self.requested_mode(), desired if desired != mode else None)

    def test_holiday_and_unknown_entities_block_thermostat_commands(self):
        for entity, values in [
            (HOLIDAY, ['on', 'unknown', 'unavailable']),
            (PRESENCE, ['unknown', 'unavailable']),
            (PERMISSION, ['unknown', 'unavailable']),
            (THERMOSTAT, ['unknown', 'unavailable', 'auto']),
        ]:
            for bad in values:
                with self.subTest(entity=entity, value=bad):
                    previous = self.states[entity]
                    self.states[entity] = bad
                    self.assertIsNone(self.requested_mode())
                    self.states[entity] = previous

    def test_away_cold_then_arrival_and_summer_arrival(self):
        self.states.update({PRESENCE: 'not_home', PERMISSION: 'off'})
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'on')
        self.assertEqual(self.requested_mode(), 'off')
        self.states[THERMOSTAT] = 'off'
        self.states[PRESENCE] = 'home'
        self.assertEqual(self.requested_mode(), 'heat')
        self.states[MEAN] = '21'
        self.update_permission()
        self.assertIsNone(self.requested_mode())

    def test_holiday_exit_reconciles_updated_seasonal_permission(self):
        self.states.update({HOLIDAY: 'on', MEAN: '21'})
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'off')
        self.assertIsNone(self.requested_mode())
        self.states[HOLIDAY] = 'off'
        self.assertEqual(self.requested_mode(), 'off')

    def test_restored_permission_cannot_heat_before_hot_temperature_is_applied(self):
        self.states.update({PERMISSION: 'on', MEAN: '21', THERMOSTAT: 'off'})
        self.assertIsNone(self.requested_mode())

    def test_controller_recovers_without_overriding_manual_mode_changes(self):
        recovery = next(t['value_template'] for t in CONTROL['triggers'] if t['trigger'] == 'template')
        for state, expected in [('unavailable', False), ('off', True), ('heat', True), ('off', True)]:
            self.states[THERMOSTAT] = state
            self.assertEqual(self.evaluate(recovery), expected)
        entities = CONTROL['triggers'][0]['entity_id']
        self.assertEqual(set(entities), {PERMISSION, PRESENCE, HOLIDAY})
        self.assertIn('to', CONTROL['triggers'][0])
        self.assertIsNone(CONTROL['triggers'][0]['to'])


if __name__ == '__main__':
    unittest.main()
