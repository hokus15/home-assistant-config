"""Exercise heating templates with simulated Matter states, without device calls."""

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2.sandbox import ImmutableSandboxedEnvironment
import yaml


ROOT = Path(__file__).resolve().parents[1]
HEATING_CONFIG = yaml.safe_load((ROOT / 'config/packages/calefaccion.yaml').read_text(encoding='utf-8'))
THERMOSTAT = 'climate.recibidor_termostato'
MEAN = 'sensor.home_temperature_stats'
ACTIVE = 'binary_sensor.recibidor_termostato_activo'
TEMPERATURE = 'sensor.recibidor_termostato_temperatura'
TARGET = 'sensor.recibidor_termostato_temperatura_objetivo'
PERMISSION = 'input_boolean.calefaccion_temporada_activo'
PRESENCE = 'group.invitado_y_familia'
EFFECTIVE_PRESENCE = 'binary_sensor.calefaccion_presencia'
HOLIDAY = 'switch.holiday'
CONTROL_STATE = 'sensor.calefaccion_estado'
DESIRED_TEMPERATURE = 'sensor.calefaccion_temperatura_objetivo'
SCHEDULE = 'schedule.calefaccion'
FUNCTION_MODE = 'input_select.calefaccion_funcionamiento'
MANUAL = 'input_number.calefaccion_temperatura_manual'
LOWER = 'input_number.calefaccion_temporada_temperatura_activar'
UPPER = 'input_number.calefaccion_temporada_temperatura_desactivar'
VALID = 'binary_sensor.calefaccion_umbrales_validos'
VALIDATION = next(sensor for sensor in yaml.safe_load((ROOT / 'config/packages/calefaccion.yaml').read_text(encoding='utf-8'))['template'][0]['binary_sensor'] if sensor.get('unique_id') == 'calefaccion_umbrales_validos')
ALERT = yaml.safe_load((ROOT / 'config/packages/alerts.yaml').read_text(encoding='utf-8'))['template'][0]['binary_sensor'][0]
HEATING = yaml.safe_load((ROOT / 'config/packages/calefaccion.yaml').read_text(encoding='utf-8'))['template'][0]['binary_sensor'][0]
AUTOMATIONS = [
    yaml.safe_load(path.read_text(encoding='utf-8'))[0]
    for path in sorted((ROOT / 'config/automations').glob('calefaccion_recibidor_*_por_temperatura_media.yaml'))
]
CONTROL = yaml.safe_load((ROOT / 'config/automations/calefaccion_recibidor_aplicar_modo.yaml').read_text(encoding='utf-8'))[0]
NOTICE = yaml.safe_load((ROOT / 'config/packages/alerts.yaml').read_text(encoding='utf-8'))['alert']['energy_waste_alert']
HEATING_SENSORS = {sensor['unique_id']: sensor for sensor in HEATING_CONFIG['template'][0]['sensor']}
VIRTUAL = HEATING_CONFIG['template'][0]['climate'][0]


class HeatingTemplates(unittest.TestCase):
    def setUp(self):
        self.states = {
            THERMOSTAT: 'heat', MEAN: '18', ACTIVE: 'on',
            TEMPERATURE: '19.0', TARGET: '20.0',
            PERMISSION: 'on', PRESENCE: 'home', EFFECTIVE_PRESENCE: 'on', HOLIDAY: 'off',
            LOWER: '18.5', UPPER: '20', VALID: 'on', SCHEDULE: 'on', FUNCTION_MODE: 'auto', MANUAL: '18',
            **{'input_number.calefaccion_temperatura_' + profile: str(value) for profile, value in
               [('ausente', 14), ('vacaciones', 14), ('eco', 16), ('normal', 18), ('confort', 19), ('caliente', 20)]},
        }
        self.now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
        self.openings = [self.opening('Ventana salón', 900)]
        self.attributes = {SCHEDULE: {'perfil': 'confort'}, THERMOSTAT: {'temperature': 19, 'min_temp': 5, 'max_temp': 30}}
        self.env = ImmutableSandboxedEnvironment()
        self.env.filters['expand'] = lambda entities: entities
        self.env.globals.update(
            has_value=lambda entity: self.states.get(entity, 'unknown') not in ('unknown', 'unavailable'),
            is_state=lambda entity, value: self.states.get(entity, 'unknown') == value,
            states=lambda entity: self.states.get(entity, 'unknown'),
            label_entities=lambda label: self.openings,
            is_number=self.is_number,
            state_attr=lambda entity, attribute: self.attributes.get(entity, {}).get(attribute),
            now=lambda: self.now,
            as_timestamp=lambda value: value.timestamp(),
            relative_time=lambda value: f'{int((self.now - value).total_seconds() // 60)} minutes',
        )

    def opening(self, name, age, state='on'):
        return SimpleNamespace(
            state=state,
            last_changed=self.now - timedelta(seconds=age),
            attributes=SimpleNamespace(friendly_name=name),
        )

    @staticmethod
    def is_number(value):
        try:
            return math.isfinite(float(value))
        except (ValueError, TypeError):
            return False

    def evaluate(self, source, **variables):
        return self.env.from_string(source).render(**variables).strip() == 'True'

    def condition_passes(self, condition, **variables):
        if condition['condition'] == 'state':
            return self.states[condition['entity_id']] == condition['state']
        if condition['condition'] == 'template':
            return self.evaluate(condition['value_template'], **variables)
        if condition['condition'] == 'numeric_state':
            value = self.states[condition['entity_id']]
            if not self.is_number(value):
                return False
            def boundary(key):
                threshold = condition[key]
                return float(self.states[threshold]) if isinstance(threshold, str) else threshold
            return (('above' not in condition or float(value) > boundary('above'))
                    and ('below' not in condition or float(value) < boundary('below')))
        self.fail(f'Unsupported condition: {condition}')

    def update_permission(self):
        for automation in AUTOMATIONS:
            if all(self.condition_passes(c) for c in automation['conditions']):
                action = automation['actions'][0]
                self.assertEqual(action['target']['entity_id'], PERMISSION)
                self.states[PERMISSION] = 'on' if action['action'] == 'input_boolean.turn_on' else 'off'

    def control_variables(self, refresh=True):
        if refresh:
            self.states[CONTROL_STATE] = self.selected_state()
            self.states[DESIRED_TEMPERATURE] = self.selected_setpoint()
        if not all(self.condition_passes(c) for c in CONTROL['conditions']):
            return None
        variables = {}
        for action in CONTROL['actions']:
            if 'delay' in action:
                continue
            if 'variables' in action:
                for name, source in action['variables'].items():
                    variables[name] = self.env.from_string(source).render(**variables).strip()
            elif 'condition' in action:
                if not self.condition_passes(action, **variables):
                    return None
            else:
                break
        return variables

    def requested_hvac_mode(self):
        variables = self.control_variables()
        return variables['desired_hvac_mode'] if variables else None

    def selected_state(self):
        scheduled = HEATING_SENSORS['calefaccion_perfil_programado']['state']
        self.states['sensor.calefaccion_perfil_programado'] = self.env.from_string(scheduled).render().strip()
        return self.env.from_string(HEATING_SENSORS['calefaccion_estado']['state']).render().strip()

    def selected_setpoint(self):
        self.states[CONTROL_STATE] = self.selected_state()
        sensor = HEATING_SENSORS['calefaccion_temperatura_objetivo']
        if not self.evaluate(sensor['availability']):
            return 'unknown'
        return self.env.from_string(sensor['state']).render().strip()

    def test_waste_alert_needs_estimated_heating_and_an_open_door(self):
        self.assertTrue(self.evaluate(ALERT['state']))
        self.states[ACTIVE] = 'off'
        self.assertFalse(self.evaluate(ALERT['state']))
        self.states[ACTIVE] = 'on'
        self.openings[0].state = 'off'
        self.assertFalse(self.evaluate(ALERT['state']))

    def test_each_opening_must_individually_exceed_ten_minutes(self):
        for age, expected in [(0, False), (599, False), (600, False), (601, True)]:
            with self.subTest(age=age):
                self.openings = [self.opening('Ventana', age)]
                self.assertEqual(self.evaluate(ALERT['state']), expected)

    def test_successive_recent_openings_do_not_accumulate_time(self):
        self.openings = [self.opening('Ventana', 1200, 'off'), self.opening('Puerta', 300)]
        self.assertFalse(self.evaluate(ALERT['state']))
        # Passage of time alone is enough; no new sensor state is required.
        self.now += timedelta(seconds=301)
        self.assertTrue(self.evaluate(ALERT['state']))

    def test_heating_start_uses_existing_opening_age(self):
        self.openings = [self.opening('Ventana', 1800)]
        self.states[ACTIVE] = 'off'
        self.assertFalse(self.evaluate(ALERT['state']))
        self.states[ACTIVE] = 'on'
        self.assertTrue(self.evaluate(ALERT['state']))

    def test_notice_lists_all_openings_including_recent_ones(self):
        self.openings = [self.opening('Ventana salón', 900), self.opening('Puerta cocina', 180),
                         self.opening('Ventana cerrada', 1800, 'off')]
        self.assertTrue(self.evaluate(ALERT['state']))
        message = self.env.from_string(NOTICE['message']).render()
        self.assertIn('La Ventana salón lleva más de 15 minutos abierta y la calefacción está encendida.', message)
        self.assertIn('La Puerta cocina lleva más de 3 minutos abierta y la calefacción está encendida.', message)
        self.assertNotIn('Ventana cerrada', message)

    def test_unknown_unavailable_and_closed_openings_cannot_trigger(self):
        for state in ['off', 'unknown', 'unavailable']:
            self.openings = [self.opening('Ventana', 1800, state)]
            self.assertFalse(self.evaluate(ALERT['state']))
        self.openings = []
        self.assertFalse(self.evaluate(ALERT['state']))

    def test_alert_sends_immediately_repeats_and_can_be_acknowledged(self):
        self.assertTrue(NOTICE['can_acknowledge'])
        self.assertFalse(NOTICE['skip_first'])
        self.assertEqual(NOTICE['repeat'], 10)
        self.assertEqual(NOTICE['notifiers'], ['recibidor', 'suite', 'despacho', 'telegram_hokusphone'])
        self.assertIn('Enterado:/alert.turn_off#alert.energy_waste_alert',
                      NOTICE['data']['inline_keyboard'])

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
            trigger = next(t['value_template'] for t in automation['triggers'] if t.get('id') == 'recovery')
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
            trigger = next(t['value_template'] for t in automation['triggers'] if t.get('id') == 'recovery')
            results = []
            for state in ['heat', 'off', 'heat']:
                self.states[THERMOSTAT] = state
                results.append(self.evaluate(trigger))
            self.assertEqual(results, [True, True, True])

    def test_confirmation_requires_the_requested_hvac_mode(self):
        confirmation = next(a['wait_template'] for a in CONTROL['actions'] if 'wait_template' in a)
        for desired in ['heat', 'off']:
            for state in ['unknown', 'unavailable', 'off', 'heat']:
                with self.subTest(desired=desired, state=state):
                    self.states[THERMOSTAT] = state
                    self.assertEqual(self.evaluate(confirmation, desired_hvac_mode=desired, desired_setpoint='19'), state == desired)

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
                        self.states.update({PERMISSION: permission, PRESENCE: presence, EFFECTIVE_PRESENCE: 'on' if presence == 'home' else 'off', THERMOSTAT: mode})
                        desired = 'heat' if permission == 'on' else 'off'
                        target = 19 if presence == 'home' else 14
                        changed = desired != mode or (desired == 'heat' and target != self.attributes[THERMOSTAT]['temperature'])
                        self.assertEqual(self.requested_hvac_mode(), desired if changed else None)

    def test_unknown_entities_block_thermostat_commands(self):
        for entity, values in [
            (HOLIDAY, ['unknown', 'unavailable']),
            (FUNCTION_MODE, ['unknown', 'unavailable']),
            (PRESENCE, ['unknown', 'unavailable']),
            (EFFECTIVE_PRESENCE, ['unknown', 'unavailable']),
            (PERMISSION, ['unknown', 'unavailable']),
            (THERMOSTAT, ['unknown', 'unavailable', 'auto']),
        ]:
            for bad in values:
                with self.subTest(entity=entity, value=bad):
                    previous = self.states[entity]
                    self.states[entity] = bad
                    self.assertIsNone(self.requested_hvac_mode())
                    self.states[entity] = previous

    def test_away_cold_then_arrival_and_summer_arrival(self):
        self.states.update({PRESENCE: 'not_home', EFFECTIVE_PRESENCE: 'off', PERMISSION: 'off'})
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'on')
        self.assertEqual(self.requested_hvac_mode(), 'heat')
        self.assertEqual(self.selected_setpoint(), '14.0')
        self.states[THERMOSTAT] = 'off'
        self.states[PRESENCE] = 'home'
        self.states[EFFECTIVE_PRESENCE] = 'on'
        self.assertEqual(self.requested_hvac_mode(), 'heat')
        self.states[MEAN] = '21'
        self.update_permission()
        self.assertIsNone(self.requested_hvac_mode())

    def test_holiday_exit_reconciles_updated_seasonal_permission(self):
        self.states.update({HOLIDAY: 'on', MEAN: '21'})
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'off')
        self.assertEqual(self.requested_hvac_mode(), 'off')
        self.states[HOLIDAY] = 'off'
        self.assertEqual(self.requested_hvac_mode(), 'off')

    def test_restored_permission_cannot_heat_before_hot_temperature_is_applied(self):
        self.states.update({PERMISSION: 'on', MEAN: '21', THERMOSTAT: 'off'})
        self.assertIsNone(self.requested_hvac_mode())

    def test_custom_thresholds_keep_hysteresis_and_update_hot_start_guard(self):
        self.states.update({LOWER: '17', UPPER: '22', MEAN: '18', PERMISSION: 'off'})
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'off')
        self.states[MEAN] = '16.9'
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'on')
        self.states.update({MEAN: '21', THERMOSTAT: 'off'})
        self.assertEqual(self.requested_hvac_mode(), 'heat')
        self.states[MEAN] = '22.1'
        self.assertIsNone(self.requested_hvac_mode())
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'off')

    def test_invalid_thresholds_preserve_season_and_thermostat(self):
        for lower, upper in [('20', '20'), ('21', '19'), ('unknown', '20'), ('18.5', 'unavailable')]:
            for previous in ['on', 'off']:
                with self.subTest(lower=lower, upper=upper, previous=previous):
                    # Keep the derived sensor stale to exercise event ordering.
                    self.states.update({LOWER: lower, UPPER: upper, PERMISSION: previous, VALID: 'on'})
                    self.assertFalse(self.evaluate(VALIDATION['state']))
                    self.update_permission()
                    self.assertEqual(self.states[PERMISSION], previous)
                    self.assertIsNone(self.requested_hvac_mode())

    def test_initial_equal_thresholds_wait_for_manual_configuration(self):
        self.states.update({LOWER: '5', UPPER: '5'})
        self.assertFalse(self.evaluate(VALIDATION['state']))
        self.assertIsNone(self.requested_hvac_mode())
        self.states[PERMISSION] = 'off'
        self.update_permission()
        self.assertEqual(self.states[PERMISSION], 'off')

    def test_threshold_edits_are_watched_by_temperature_automations(self):
        for automation in AUTOMATIONS:
            edits = next(t for t in automation['triggers'] if t['trigger'] == 'state')
            self.assertEqual(set(edits['entity_id']), {LOWER, UPPER})

    def test_effective_presence_keeps_heating_on_during_absence_grace_period(self):
        self.states.update({PRESENCE: 'not_home', EFFECTIVE_PRESENCE: 'on', THERMOSTAT: 'heat'})
        self.assertIsNone(self.requested_hvac_mode())
        self.states[EFFECTIVE_PRESENCE] = 'off'
        self.assertEqual(self.requested_hvac_mode(), 'heat')
        self.assertEqual(self.selected_setpoint(), '14.0')
        self.states.update({PRESENCE: 'home', EFFECTIVE_PRESENCE: 'on', THERMOSTAT: 'off'})
        self.assertEqual(self.requested_hvac_mode(), 'heat')

    def test_effective_presence_template_rejects_missing_data_and_delays_only_absence(self):
        package = yaml.safe_load((ROOT / 'config/packages/calefaccion.yaml').read_text(encoding='utf-8'))
        presence = next(sensor for sensor in package['template'][0]['binary_sensor']
                        if sensor.get('unique_id') == 'calefaccion_presencia')
        self.assertEqual(presence['delay_off'], '00:05:00')
        self.assertNotIn('delay_on', presence)
        for raw, result in [('home', 'True'), ('not_home', 'False'),
                            ('unknown', 'None'), ('unavailable', 'None')]:
            with self.subTest(raw=raw):
                self.states[PRESENCE] = raw
                self.assertEqual(self.env.from_string(presence['state']).render().strip(), result)

    def test_controller_recovers_without_overriding_manual_mode_changes(self):
        recovery = next(t['value_template'] for t in CONTROL['triggers'] if t['trigger'] == 'template')
        for state, expected in [('unavailable', False), ('off', True), ('heat', True), ('off', True)]:
            self.states[THERMOSTAT] = state
            self.assertEqual(self.evaluate(recovery), expected)
        entities = CONTROL['triggers'][0]['entity_id']
        self.assertEqual(set(entities), {CONTROL_STATE, DESIRED_TEMPERATURE})
        self.assertNotIn(THERMOSTAT, entities)
        self.assertIn('to', CONTROL['triggers'][0])
        self.assertIsNone(CONTROL['triggers'][0]['to'])

    def test_automatic_overrides_have_priority_over_the_schedule(self):
        self.assertEqual(self.selected_state(), 'confort')
        self.states[EFFECTIVE_PRESENCE] = 'off'
        self.assertEqual(self.selected_state(), 'ausente')
        self.assertEqual(self.selected_setpoint(), '14.0')
        self.states[HOLIDAY] = 'on'
        self.states[PRESENCE] = 'unknown'
        self.assertEqual(self.selected_state(), 'vacaciones')
        self.states[PERMISSION] = 'off'
        self.assertEqual(self.selected_state(), 'fuera_temporada')
        self.assertEqual(self.selected_setpoint(), 'unknown')

    def test_schedule_attribute_changes_select_each_occupied_profile(self):
        for profile, target in [('eco', 16), ('normal', 18), ('confort', 19), ('caliente', 20)]:
            with self.subTest(profile=profile):
                self.attributes[SCHEDULE]['perfil'] = profile
                self.assertEqual(self.states[SCHEDULE], 'on')
                self.assertEqual(self.selected_state(), profile)
                self.assertEqual(float(self.selected_setpoint()), target)

    def test_active_profile_setpoint_edits_update_the_requested_setpoint(self):
        self.assertIsNone(self.requested_hvac_mode())
        self.states['input_number.calefaccion_temperatura_confort'] = '19.5'
        variables = self.control_variables()
        self.assertEqual(variables['desired_hvac_mode'], 'heat')
        self.assertEqual(float(variables['desired_setpoint']), 19.5)
        self.attributes[THERMOSTAT]['temperature'] = 19.5
        self.assertIsNone(self.requested_hvac_mode())

    def test_controller_confirmation_needs_the_actual_setpoint_too(self):
        confirmation = next(a['wait_template'] for a in CONTROL['actions'] if 'wait_template' in a)
        for current, expected in [(18, False), (19, True), (20, False), (None, False)]:
            with self.subTest(current=current):
                self.attributes[THERMOSTAT]['temperature'] = current
                self.assertEqual(self.evaluate(confirmation, desired_hvac_mode='heat', desired_setpoint='19'), expected)

    def test_control_state_change_never_uses_the_previous_displayed_setpoint(self):
        self.states[CONTROL_STATE] = 'eco'
        self.states[DESIRED_TEMPERATURE] = '19'
        variables = self.control_variables(refresh=False)
        self.assertEqual(variables['control_state'], 'eco')
        self.assertEqual(float(variables['desired_setpoint']), 16)

    def test_bad_selected_setpoint_blocks_heat(self):
        for value in ['unknown', 'unavailable', 'bad', '4', '31']:
            with self.subTest(value=value):
                self.states['input_number.calefaccion_temperatura_confort'] = value
                self.assertIsNone(self.requested_hvac_mode())
        self.states['input_number.calefaccion_temperatura_confort'] = '19'
        self.states[PERMISSION] = 'off'
        self.assertEqual(self.requested_hvac_mode(), 'off')

    def test_missing_schedule_is_not_a_fallback_but_an_empty_schedule_uses_eco(self):
        for state in ['unknown', 'unavailable']:
            self.states[SCHEDULE] = state
            self.assertEqual(self.selected_state(), 'sin_datos')
            self.assertIsNone(self.requested_hvac_mode())
        self.states[SCHEDULE] = 'off'
        self.assertEqual(self.selected_state(), 'eco')
        self.states[SCHEDULE] = 'on'
        self.attributes[SCHEDULE]['perfil'] = 'invalid'
        self.assertEqual(self.selected_state(), 'sin_datos')
        self.states[EFFECTIVE_PRESENCE] = 'off'
        self.assertEqual(self.selected_state(), 'ausente')

    def test_auto_return_from_absence_and_vacation_uses_the_current_scheduled_profile(self):
        self.states.update({HOLIDAY: 'on', EFFECTIVE_PRESENCE: 'off'})
        self.assertEqual(self.selected_state(), 'vacaciones')
        self.states[HOLIDAY] = 'off'
        self.assertEqual(self.selected_state(), 'ausente')
        self.attributes[SCHEDULE]['perfil'] = 'eco'
        self.states[EFFECTIVE_PRESENCE] = 'on'
        self.assertEqual(self.selected_state(), 'eco')
        self.assertEqual(self.selected_setpoint(), '16.0')

    def test_profile_and_manual_setpoints_restore_saved_values(self):
        self.assertEqual({name for name in HEATING_CONFIG['input_number']
                          if name.startswith('calefaccion_temperatura_')}, {
            'calefaccion_temperatura_' + profile
            for profile in ['ausente', 'vacaciones', 'eco', 'normal', 'confort', 'caliente', 'manual']
        })
        self.assertEqual(set(HEATING_CONFIG['input_boolean']), {'calefaccion_temporada_activo'})
        for config in HEATING_CONFIG['input_number'].values():
            self.assertNotIn('initial', config)
            self.assertEqual(config['min'], 5)

    def virtual_action(self, action, **variables):
        for step in VIRTUAL[action]:
            if 'condition' in step:
                if not self.condition_passes(step, **variables):
                    return
                continue
            service = step['action']
            entity = step['target']['entity_id']
            field = 'option' if service == 'input_select.select_option' else 'value'
            value = self.env.from_string(step['data'][field]).render(**variables).strip()
            self.states[entity] = value

    def test_virtual_modes_are_standard_and_start_off_without_resetting_saved_settings(self):
        import ast
        supported = ast.literal_eval(self.env.from_string(VIRTUAL['hvac_modes']).render())
        self.assertEqual(supported, ['off', 'auto', 'heat'])
        config = HEATING_CONFIG['input_select']['calefaccion_funcionamiento']
        self.assertEqual(config['options'][0], 'off')
        self.assertNotIn('initial', config)
        self.assertEqual(VIRTUAL['default_entity_id'], 'climate.calefaccion')

    def test_virtual_hvac_actions_only_change_the_requested_function(self):
        for function in ['off', 'auto', 'heat']:
            self.virtual_action('set_hvac_mode', hvac_mode=function)
            self.assertEqual(self.states[FUNCTION_MODE], function)
            self.assertEqual(self.env.from_string(VIRTUAL['hvac_mode']).render().strip(), function)
            label = self.env.from_string(VIRTUAL['attributes']['modo_funcionamiento']).render().strip()
            self.assertEqual(label, {'off': 'apagado', 'auto': 'automático', 'heat': 'manual'}[function])
        for action in ['set_hvac_mode', 'set_temperature']:
            for step in VIRTUAL[action]:
                if 'action' in step:
                    self.assertNotIn(step['action'].split('.')[0], ['climate'])

    def test_explicit_off_wins_over_every_automatic_rule_and_missing_data(self):
        self.states.update({FUNCTION_MODE: 'off', HOLIDAY: 'on', PRESENCE: 'unknown', LOWER: '5', UPPER: '5'})
        self.assertEqual(self.selected_state(), 'apagado')
        self.assertEqual(self.requested_hvac_mode(), 'off')
        self.states[PERMISSION] = 'off'
        self.update_permission()
        self.assertEqual(self.states[FUNCTION_MODE], 'off')

    def test_manual_ignores_schedule_but_respects_season_vacation_and_absence(self):
        self.states.update({FUNCTION_MODE: 'heat', SCHEDULE: 'unavailable', MANUAL: '18.5'})
        self.assertEqual(self.selected_state(), 'manual')
        self.assertEqual(self.selected_setpoint(), '18.5')
        self.states[EFFECTIVE_PRESENCE] = 'off'
        self.assertEqual(self.selected_state(), 'ausente')
        self.assertEqual(self.selected_setpoint(), '14.0')
        self.states[HOLIDAY] = 'on'
        self.assertEqual(self.selected_state(), 'vacaciones')
        self.states[PERMISSION] = 'off'
        self.assertEqual(self.selected_state(), 'fuera_temporada')

    def test_return_from_overrides_restores_manual_target_or_current_schedule(self):
        self.states.update({FUNCTION_MODE: 'heat', MANUAL: '20.5', HOLIDAY: 'on', EFFECTIVE_PRESENCE: 'off'})
        self.assertEqual(self.selected_state(), 'vacaciones')
        self.states[HOLIDAY] = 'off'
        self.assertEqual(self.selected_state(), 'ausente')
        self.states[EFFECTIVE_PRESENCE] = 'on'
        self.assertEqual(self.selected_state(), 'manual')
        self.assertEqual(self.selected_setpoint(), '20.5')
        self.states[FUNCTION_MODE] = 'auto'
        self.attributes[SCHEDULE]['perfil'] = 'eco'
        self.assertEqual(self.selected_state(), 'eco')
        self.assertEqual(self.selected_setpoint(), '16.0')

    def test_virtual_temperature_edit_selects_manual_and_keeps_explicit_auto_or_off(self):
        self.virtual_action('set_temperature', temperature=19.5, hvac_mode=None)
        self.assertEqual(self.states[FUNCTION_MODE], 'heat')
        self.assertEqual(float(self.states[MANUAL]), 19.5)
        self.assertEqual(self.selected_state(), 'manual')
        for function in ['auto', 'off']:
            self.virtual_action('set_temperature', temperature=18, hvac_mode=function)
            self.assertEqual(self.states[FUNCTION_MODE], function)
            self.assertEqual(float(self.states[MANUAL]), 18)

    def test_virtual_temperature_edit_preserves_override_and_remembers_manual_value(self):
        self.states[HOLIDAY] = 'on'
        self.virtual_action('set_temperature', temperature=20, hvac_mode=None)
        self.assertEqual(self.selected_state(), 'vacaciones')
        self.assertEqual(self.selected_setpoint(), '14.0')
        self.states[HOLIDAY] = 'off'
        self.assertEqual(self.selected_state(), 'manual')
        self.assertEqual(self.selected_setpoint(), '20.0')

    def test_virtual_temperature_display_uses_effective_target_and_real_tado_measurement(self):
        self.attributes[THERMOSTAT]['current_temperature'] = 19.4
        self.states[CONTROL_STATE] = self.selected_state()
        self.states[DESIRED_TEMPERATURE] = self.selected_setpoint()
        self.assertEqual(float(self.env.from_string(VIRTUAL['current_temperature']).render()), 19.4)
        self.assertEqual(float(self.env.from_string(VIRTUAL['target_temperature']).render()), 19)
        self.states[DESIRED_TEMPERATURE] = 'unavailable'
        self.assertEqual(float(self.env.from_string(VIRTUAL['target_temperature']).render()), 18)

    def test_active_profile_excludes_manual_shutdown_and_missing_data(self):
        source = HEATING_SENSORS['calefaccion_perfil_activo']['state']
        for status, expected in [('eco', 'eco'), ('normal', 'normal'), ('confort', 'confort'),
                                 ('caliente', 'caliente'), ('ausente', 'ausente'),
                                 ('vacaciones', 'vacaciones'), ('manual', 'ninguno'),
                                 ('apagado', 'ninguno'), ('fuera_temporada', 'ninguno'),
                                 ('sin_datos', 'sin_datos')]:
            with self.subTest(status=status):
                self.states[CONTROL_STATE] = status
                self.assertEqual(self.env.from_string(source).render().strip(), expected)

    def test_sensor_unique_ids_match_their_entity_ids(self):
        for identity, entity in [('calefaccion_estado', 'sensor.calefaccion_estado'),
                                 ('calefaccion_perfil_programado', 'sensor.calefaccion_perfil_programado'),
                                 ('calefaccion_perfil_activo', 'sensor.calefaccion_perfil_activo')]:
            self.assertEqual(HEATING_SENSORS[identity]['default_entity_id'], entity)

    def test_weekly_schedule_covers_every_minute_with_the_requested_profiles(self):
        def minute(value):
            hour, minutes, _ = map(int, value.split(':'))
            return hour * 60 + minutes

        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for day_index, day in enumerate(days):
            blocks = HEATING_CONFIG['schedule']['calefaccion'][day]
            self.assertEqual(minute(blocks[0]['from']), 0)
            self.assertEqual(minute(blocks[-1]['to']), 1440)
            for previous, following in zip(blocks, blocks[1:]):
                self.assertEqual(previous['to'], following['from'])
            for current in range(1440):
                matches = [block['data']['perfil'] for block in blocks
                           if minute(block['from']) <= current < minute(block['to'])]
                if day_index < 5:
                    expected = ('confort' if 360 <= current < 405 or 840 <= current < 1380
                                else 'normal' if 720 <= current < 840 else 'eco')
                else:
                    expected = ('normal' if 660 <= current < 840
                                else 'confort' if 840 <= current < 1380 else 'eco')
                self.assertEqual(matches, [expected], (day, current))


if __name__ == '__main__':
    unittest.main()
