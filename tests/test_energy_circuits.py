"""Exercise the actual circuit templates with simulated device outages."""

import json
import math
from pathlib import Path
import unittest

from jinja2 import FileSystemLoader
from jinja2.sandbox import ImmutableSandboxedEnvironment
import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'config/custom_templates/energia_circuitos.jinja').read_text(encoding='utf-8')
PACKAGE = yaml.safe_load((ROOT / 'config/packages/energia_supervision_circuitos.yaml').read_text(encoding='utf-8'))


def is_number(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


class CircuitAlerts(unittest.TestCase):
    def setUp(self):
        self.states = {}
        env = ImmutableSandboxedEnvironment(loader=FileSystemLoader(ROOT / 'config/custom_templates'))
        env.filters.update(to_json=json.dumps, from_json=json.loads)
        env.globals.update(
            states=lambda entity: self.states.get(entity, 'unknown'),
            is_state=lambda entity, value: self.states.get(entity, 'unknown') == value,
            is_number=is_number,
        )
        self.macros = env.from_string(SOURCE).module
        self.env = env
        for circuit in self.macros.circuitos.values():
            for entity in circuit['equipos']:
                self.states[entity] = '0' if circuit.get('numerico') else 'off'

    def set_circuit(self, key, state):
        for entity in self.macros.circuitos[key]['equipos']:
            self.states[entity] = state

    def restore_circuit(self, key):
        self.set_circuit(key, '0' if self.macros.circuitos[key].get('numerico') else 'off')

    def diagnose(self):
        return json.loads(self.macros.diagnostico())

    def active(self, key):
        return self.macros.alerta(key).strip() == 'True'

    def message(self, key):
        return ' '.join(self.macros.mensaje(key).split())

    def test_off_relays_are_available_not_power_outages(self):
        self.assertEqual(self.diagnose()['locales'], [])
        self.assertFalse(self.active('diferencial'))

    def test_each_individual_circuit_is_detected(self):
        for key in self.macros.circuitos:
            with self.subTest(key=key):
                self.set_circuit(key, 'unavailable')
                self.assertEqual(self.diagnose()['locales'], [key])
                self.assertFalse(self.active('diferencial'))
                self.assertTrue(self.active(key))
                self.restore_circuit(key)

    def test_one_kitchen_device_does_not_identify_whole_circuit(self):
        self.states['switch.cocina_nevera'] = 'unavailable'
        self.assertFalse(self.active('cocina'))

    def test_pool_is_one_circuit_and_live_peer_contradicts_outage(self):
        self.set_circuit('piscina', 'unavailable')
        self.states['switch.piscina_medidor_consumo'] = 'on'
        self.assertFalse(self.active('piscina'))
        self.assertFalse(self.active('diferencial'))
        self.states['switch.piscina_medidor_consumo'] = 'unknown'
        self.assertTrue(self.active('piscina'))
        self.assertFalse(self.active('diferencial'))

    def test_lower_differential_does_not_require_cameras(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unavailable')
        for camera_state in ['idle', 'unavailable', 'unknown']:
            with self.subTest(camera_state=camera_state):
                for camera in ['camera.caseta', 'camera.piscina', 'camera.barbacoa']:
                    self.states[camera] = camera_state
                self.assertTrue(self.active('diferencial'))
                self.assertEqual(self.diagnose()['locales'], [])
                self.assertFalse(self.active('piscina'))
                # Camera availability changes the observations, not the diagnosis.
                self.assertEqual('Cámara' in self.message('diferencial'), camera_state == 'unavailable')

    def test_two_distinct_lower_circuits_suffice_with_other_refs_unknown(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unknown')
        self.set_circuit('lavadora', 'unavailable')
        self.set_circuit('secadora', 'unavailable')
        self.assertTrue(self.active('diferencial'))

    def test_one_lost_lower_circuit_with_unknown_peers_is_not_a_differential(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unknown')
        self.set_circuit('lavadora', 'unavailable')
        self.assertFalse(self.active('diferencial'))
        self.assertEqual(self.diagnose()['locales'], [])
        # A second independent disconnected circuit crosses the threshold.
        self.set_circuit('secadora', 'unavailable')
        self.assertTrue(self.active('diferencial'))

    def test_live_lower_circuit_prevents_differential_claim(self):
        self.set_circuit('lavadora', 'unavailable')
        self.set_circuit('secadora', 'unavailable')
        self.assertFalse(self.active('diferencial'))
        self.assertEqual(self.diagnose()['locales'], ['lavadora', 'secadora'])

    def test_total_outage_or_common_network_failure_does_not_blame_breakers(self):
        for key in self.macros.circuitos:
            self.set_circuit(key, 'unavailable')
        self.assertFalse(self.active('diferencial'))
        self.assertEqual(self.diagnose()['locales'], [])

    def test_no_upper_reference_means_no_differential_diagnosis(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unavailable')
        self.assertTrue(self.active('diferencial'))
        self.set_circuit('cocina', 'unknown')
        self.assertFalse(self.active('diferencial'))
        self.assertEqual(self.diagnose()['locales'], [])

    def test_startup_unknowns_are_not_outages(self):
        self.states.clear()
        self.assertFalse(self.active('diferencial'))
        self.assertEqual(self.diagnose()['locales'], [])

    def test_circuit_alert_ends_when_evidence_becomes_unknown(self):
        self.set_circuit('lavadora', 'unavailable')
        self.assertTrue(self.active('lavadora'))
        self.set_circuit('lavadora', 'unknown')
        self.assertFalse(self.active('lavadora'))
        # Loss of evidence is not a recovery; no alert has a done_message.
        self.assertTrue(all('done_message' not in alert for alert in PACKAGE['alert'].values()))

    def test_messages_report_actual_devices_only(self):
        self.set_circuit('piscina', 'unavailable')
        self.states['camera.caseta'] = 'unavailable'
        self.states['camera.barbacoa'] = 'idle'
        msg = self.message('piscina')
        self.assertTrue(msg.startswith('⚠️'))
        self.assertIn('Sin comunicación: Depuradora, Iluminación de piscina, Medidor de piscina.', msg)
        self.assertIn('Siguen comunicando: Nevera, Congelador', msg)
        self.assertIn('Cámara de caseta', msg)
        self.assertNotIn('Cámara de barbacoa', msg)
        self.assertNotIn('barrera', msg)

    def test_partial_recovery_changes_diagnosis(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unavailable')
        self.assertTrue(self.active('diferencial'))
        self.set_circuit('lavadora', 'off')
        self.assertFalse(self.active('diferencial'))
        self.assertTrue(self.active('piscina'))

    def test_alert_delivery_uses_modern_family_notify_action(self):
        adapter = PACKAGE['notify'][0]
        self.assertEqual(adapter['services'], [dict(
            action='send_message', data=dict(entity_id='notify.telegram_family_group'))])
        for alert in PACKAGE['alert'].values():
            self.assertIn(adapter['name'], alert['notifiers'])
            # Generic notify entities do not accept Telegram-specific payloads.
            self.assertNotIn('data', alert)

    def test_yaml_wires_each_outage_to_its_sensor_and_message(self):
        for key, sensor_id in {
            'piscina': 'piscina_magnetotermico_alerta',
            'cocina': 'cocina_enchufes_estado',
            'lavadora': 'energia_lavadora_circuito_alerta',
            'secadora': 'energia_secadora_circuito_alerta',
            'lavavajillas': 'energia_lavavajillas_circuito_alerta',
            'cargador_ev': 'energia_cargador_ev_circuito_alerta',
            'aire_planta_baja': 'energia_aire_planta_baja_circuito_alerta',
            'aire_primera_planta': 'energia_aire_primera_planta_circuito_alerta',
        }.items():
            with self.subTest(key=key):
                self.set_circuit(key, 'unavailable')
                active = [s['unique_id'] for s in PACKAGE['template'][0]['binary_sensor']
                          if self.env.from_string(s['state']).render().strip() == 'True']
                self.assertEqual(active, [sensor_id])
                alert = next(a for a in PACKAGE['alert'].values()
                             if a['entity_id'] == 'binary_sensor.' + sensor_id)
                msg = self.env.from_string(alert['message']).render().strip()
                self.assertEqual(msg, self.message(key))
                self.restore_circuit(key)

    def test_shelly_zero_and_numeric_power_are_live_references(self):
        for power in ['0', '0.0', '1500.25', '-1.5']:
            with self.subTest(power=power):
                self.set_circuit('aire_planta_baja', power)
                d = self.diagnose()
                self.assertIn('aire_planta_baja', d['vivos'])
                self.assertNotIn('aire_planta_baja', d['locales'])

    def test_shelly_invalid_values_are_neither_live_nor_outage(self):
        for value in ['unknown', 'off', 'on', 'NaN', 'inf', '']:
            with self.subTest(value=value):
                self.set_circuit('aire_primera_planta', value)
                d = self.diagnose()
                self.assertNotIn('aire_primera_planta', d['vivos'])
                self.assertNotIn('aire_primera_planta', d['locales'])

    def test_live_shelly_prevents_false_lower_differential(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unavailable')
        self.set_circuit('aire_planta_baja', '0')
        self.assertFalse(self.active('diferencial'))
        self.assertTrue(self.active('aire_primera_planta'))
        self.assertIn('Siguen comunicando: Nevera, Congelador, Shelly EM del aire de planta baja.',
                      self.message('aire_primera_planta'))

    def test_differential_message_includes_both_disconnected_shellys(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unavailable')
        self.assertTrue(self.active('diferencial'))
        msg = self.message('diferencial')
        self.assertIn('Shelly EM del aire de planta baja', msg)
        self.assertIn('Shelly EM del aire de primera planta', msg)

    def test_gate_is_conditional_impact_not_a_detection_reference(self):
        for key, circuit in self.macros.circuitos.items():
            if circuit['grupo'] == 'inferior':
                self.set_circuit(key, 'unavailable')
        for gate_state in ['on', 'off', 'unknown', 'unavailable']:
            with self.subTest(gate_state=gate_state):
                self.states['switch.entrada_barrera'] = gate_state
                self.assertTrue(self.active('diferencial'))
                msg = self.message('diferencial')
                self.assertIn('Si se confirma la caída del diferencial inferior, la barrera no funcionará.', msg)
                observed = msg.split('Sin comunicación: ', 1)[1].split('Siguen comunicando:', 1)[0]
                self.assertNotIn('barrera', observed)


if __name__ == '__main__':
    unittest.main()
