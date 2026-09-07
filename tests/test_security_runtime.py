"""Run in the HA container: python /repo/tests/test_security_runtime.py.

Uses real Home Assistant scripts, templates, registries, panel and automations.
All device and Telegram services are local fakes; no external messages are sent.
"""

import asyncio
from pathlib import Path
import shutil
import tempfile
import time

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_registry as er, label_registry as lr, template
from homeassistant.helpers.entity import entity_sources
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util, yaml

ROOT = Path(__file__).resolve().parents[1]


async def run():
    with tempfile.TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.time_zone = 'Europe/Madrid'
        dt_util.set_default_time_zone(dt_util.get_time_zone('Europe/Madrid'))
        shutil.copytree(ROOT / 'config/custom_templates', Path(directory) / 'custom_templates')
        messages = []
        prepared_at = []

        async def prepare_file(call):
            prepared_at.append(time.monotonic())
            path = call.data['file']
            if 'failed' in path:
                return {'returncode': 1, 'stdout': '{}'}
            return {'returncode': 0, 'stdout': ''}

        async def notify(call):
            messages.append(dict(call.data))
            return {'chats': [{'chat_id': -123, 'message_id': len(messages)}]}

        async def control_device(call):
            ids = call.data['entity_id']
            for entity in [ids] if isinstance(ids, str) else ids:
                hass.states.async_set(entity, 'on' if call.service == 'turn_on' else 'off')

        try:
            loader.async_setup(hass)
            hass.config_entries = ConfigEntries(hass, {})
            assert await async_load_base_functionality(hass)
            assert await async_setup_component(hass, 'homeassistant', {})
            for name in ['send_message', 'send_photo', 'send_video', 'answer_callback_query', 'edit_replymarkup']:
                hass.services.async_register('telegram_bot', name, notify, supports_response=SupportsResponse.OPTIONAL)
            for name in ['turn_on', 'turn_off']:
                hass.services.async_register('switch', name, control_device)
            hass.services.async_register('shell_command', 'mp4_convert', prepare_file,
                                         supports_response=SupportsResponse.OPTIONAL)

            package = yaml.load_yaml(str(ROOT / 'config/packages/seguridad_alarma.yaml'))
            panel = yaml.load_yaml(str(ROOT / 'config/packages/alarm.yaml'))
            config = {**package, 'alarm_control_panel': panel['alarm_control_panel']}
            old_scripts = yaml.load_yaml(str(ROOT / 'config/scripts.yaml'))
            for name in ['alarm_disarm_telegram', 'alarm_disarm_telegram_temporary']:
                config['script'][name] = old_scripts[name]
            for domain in ['input_boolean', 'input_datetime', 'template', 'alarm_control_panel', 'script']:
                assert await async_setup_component(hass, domain, config), domain
            automations = []
            for path in sorted((ROOT / 'config/automations').glob('seguridad_alarma_*.yaml')):
                automations.extend(yaml.load_yaml(str(path)))
            config['automation'] = automations
            assert await async_setup_component(hass, 'automation', config)

            labels = lr.async_get(hass)
            total = labels.async_create('alarma_modo_ausente').label_id
            night = labels.async_create('alarma_modo_noche').label_id
            night_recording = labels.async_create('alarma_grabacion_noche').label_id
            registry = er.async_get(hass)

            def detector(name, mode_labels, device_class='door'):
                entity = registry.async_get_or_create('binary_sensor', 'test', name, suggested_object_id=name)
                registry.async_update_entity(entity.entity_id, labels=set(mode_labels))
                hass.states.async_set(entity.entity_id, 'off', {'friendly_name': name, 'device_class': device_class})
                return entity.entity_id

            for camera in yaml.load_yaml(str(ROOT / 'config/seguridad/camaras.yaml')).values():
                control = camera.get('detection_control')
                if control and control.startswith('switch.'):
                    hass.states.async_set(control, 'off')
            door = detector('prueba_puerta', [total, night])
            second = detector('prueba_ventana', [total, night])
            active_motion = detector('movimiento_existente', [night], 'motion')
            hass.states.async_set(active_motion, 'on', {'friendly_name': 'Movimiento existente', 'device_class': 'motion'})
            hass.states.async_set('person.test', 'home')
            hass.states.async_set('group.familia', 'home', {'entity_id': ['person.test']})
            hass.states.async_set('calendar.asistente_hogar', 'off')
            hass.states.async_set('switch.guest_mode', 'off')
            await hass.async_start()
            await hass.async_block_till_done()
            assert hass.states.get('input_boolean.alarma_inicializada').state == 'on'

            async def command(name, **kwargs):
                await hass.services.async_call('script', 'seguridad_controlar', {'command': name, **kwargs}, blocking=True)
                await hass.async_block_till_done()
                return hass.states.get('sensor.alarma_contexto').attributes['data']

            def context():
                return hass.states.get('sensor.alarma_contexto').attributes['data']

            c = await command('arm_night')
            assert c['mode'] == 'armed_night', c
            assert hass.states.get('alarm_control_panel.home').state == 'armed_night'
            assert any('noche' in m.get('message', '') for m in messages), messages
            assert not any('Movimiento existente' in m.get('message', '') for m in messages), messages
            messages.clear()
            hass.states.async_set(door, 'on', {'friendly_name': 'Puerta', 'device_class': 'door'})
            await hass.async_block_till_done()
            hass.states.async_set(second, 'on', {'friendly_name': 'Ventana', 'device_class': 'window'})
            await hass.async_block_till_done()
            alerts = [m for m in messages if m.get('message') in ['🚨 Apertura detectada: Puerta', '🚨 Apertura detectada: Ventana']]
            assert len(alerts) == 2, messages
            assert hass.states.get('alarm_control_panel.home').state == 'triggered'

            # Exclusion callback is derived from the actual generated button.
            callback = alerts[0]['inline_keyboard'][0][0][1]
            assert len(callback.encode()) <= 64
            hass.bus.async_fire('telegram_callback', {'data': callback, 'id': 'test'})
            await hass.async_block_till_done()
            assert door in context()['excluded'], context()
            assert any('próximo armado' in m.get('message', '') for m in messages)
            messages.clear()
            hass.states.async_set(door, 'off')
            hass.states.async_set(door, 'on')
            await hass.async_block_till_done()
            assert not messages, messages

            c = await command('arm_night')
            assert c['excluded'] == [], c
            messages.clear()
            # Open sensors at arming do not trigger again until closed/reopened.
            await hass.async_block_till_done()
            assert not messages, messages

            # Pause can be cancelled even if panel already reads disarmed.
            c = await command('pause', minutes=30)
            assert c['paused_mode'] == 'armed_night' and c['paused_until'] > 0, c
            await hass.services.async_call('alarm_control_panel', 'alarm_disarm', {'entity_id': 'alarm_control_panel.home'}, blocking=True)
            await hass.async_block_till_done()
            assert context()['paused_until'] == 0 and context()['manual_hold'], context()
            c = await command('resume')
            assert c['mode'] == 'disarmed'

            # Arrival does not disarm night; all occupancy sources prevent away.
            await command('arm_night')
            hass.states.async_set('switch.guest_mode', 'on')
            hass.states.async_set('person.test', 'not_home')
            hass.states.async_set('group.familia', 'not_home', {'entity_id': ['person.test']})
            await hass.async_block_till_done()
            assert context()['mode'] == 'armed_night', context()
            hass.states.async_set('calendar.asistente_hogar', 'on')
            hass.states.async_set('switch.guest_mode', 'off')
            await hass.async_block_till_done()
            assert context()['mode'] == 'armed_night', context()
            hass.states.async_set('calendar.asistente_hogar', 'off')
            await hass.async_block_till_done()
            assert context()['mode'] == 'armed_away', context()
            hass.states.async_set('person.test', 'home')
            hass.states.async_set('group.familia', 'home', {'entity_id': ['person.test']})
            await hass.async_block_till_done()
            assert context()['mode'] == 'disarmed', context()

            # Add a new detector after setup, using labels only.
            third = detector('nuevo_detector', [night])
            await command('arm_night')
            messages.clear()
            hass.states.async_set(third, 'on', {'friendly_name': 'Nuevo', 'device_class': 'motion'})
            await hass.async_block_till_done()
            assert any(m.get('message') == '🚨 Movimiento detectado: Nuevo' for m in messages), messages

            resolved = await hass.services.async_call('script', 'seguridad_resolver_camara',
                {'file_path': '/media/camera/C1_00626E615161/2026/test.mkv'}, blocking=True, return_response=True)
            assert resolved['token'] == 'recibidor', resolved

            # Existing duration buttons reach the new persistent pause controller.
            for duration in [30, 60, 120, 180]:
                hass.bus.async_fire('telegram_callback', {'data': f'/{duration}_mins', 'id': 'duration',
                    'message': {'message_id': 1}, 'chat_id': -123})
                await hass.async_block_till_done()
                assert abs(context()['paused_until'] - (dt_util.utcnow().timestamp() + duration * 60)) < 2, context()
                assert context()['paused_mode'] == 'armed_night', context()
            await command('arm_night')

            camera = registry.async_get_or_create('camera', 'test', 'recibidor', suggested_object_id='recibidor')
            registry.async_update_entity(camera.entity_id, labels={night})
            hass.states.async_set(camera.entity_id, 'idle', {'friendly_name': 'Cámara recibidor'})
            interior = registry.async_get_or_create('camera', 'test', 'salon', suggested_object_id='salon')
            registry.async_update_entity(interior.entity_id, labels={night_recording})
            hass.states.async_set(interior.entity_id, 'idle', {'friendly_name': 'Cámara salón'})
            for name in ['entrada', 'caseta']:
                native = registry.async_get_or_create('camera', 'test', name, suggested_object_id=name)
                registry.async_update_entity(native.entity_id, labels={night})
                hass.states.async_set(native.entity_id, 'idle', {'friendly_name': name})
            await hass.async_block_till_done()
            assert template.Template("{{ 'camera.recibidor' in label_entities('alarma_modo_noche') }}", hass).async_render() is True
            assert template.Template("{{ 'camera.salon' in label_entities('alarma_grabacion_noche') }}", hass).async_render() is True
            assert context()['mode'] == 'armed_night' and hass.states.get('alarm_control_panel.home').state == 'armed_night', context()
            assert hass.states.get('switch.recibidor_camara_deteccion_movimiento_activa').state == 'on'
            assert hass.states.get('switch.salon_camara_deteccion_movimiento_activa').state == 'on'
            messages.clear()
            started = time.monotonic()
            await hass.services.async_call('script', 'turn_on', {
                'entity_id': 'script.seguridad_convertir_grabacion',
                'variables': {'file_path': '/media/camera/FoscamCamera_00626ED836A9/interior.mkv'},
            }, blocking=True)
            for path in [
                '/media/camera/C1_00626E615161/good.mkv',
                '/media/camera/C1_00626E615161/failed.mkv',
                '/media/camera/C1_00626E615161/good.mkv',
                '/media/camera/C1_00626E615161/photo.jpg',
                '/media/camera/puerta_principal/netatmo.mp4',
                '/media/aqara_video/lumi3.99aa9fe51953f04f/aqara.mp4',
            ]:
                await hass.services.async_call('script', 'turn_on', {
                    'entity_id': 'script.seguridad_notificar_deteccion',
                    'variables': {
                        'detector': 'camera.recibidor' if 'C1_' in path else
                                    'camera.entrada' if 'puerta_principal' in path else 'camera.caseta',
                        'alarm_mode': 'armed_night',
                        'detected_at': '06/09/2026 02:17:00',
                        'file_path': path,
                    },
                }, blocking=True)
            # Change mode while uploads are waiting: original night context stays.
            await asyncio.sleep(0.1)
            await command('disarm')
            try:
                async with asyncio.timeout(20):
                    while not any('No se pudo preparar' in m.get('message', '') for m in messages):
                        await asyncio.sleep(0.05)
            except TimeoutError as err:
                raise AssertionError(f'Expected media preparation failure; messages={messages}, prepared={prepared_at}') from err
            await hass.async_block_till_done()
            assert len(prepared_at) == 3, prepared_at
            assert all(t - started >= 14.9 for t in prepared_at), prepared_at
            videos = [m for m in messages if m.get('file', '').endswith('.mp4')]
            assert len([m for m in messages if m.get('file', '').endswith('.jpg')]) == 1, messages
            assert len(videos) == 3 and {m['caption'] for m in videos} == {'🚨 Movimiento detectado: Cámara recibidor', '🚨 Movimiento detectado: entrada', '🚨 Movimiento detectado: caseta'}, messages
            assert {Path(m['file']).name for m in videos} == {'good.mp4', 'netatmo.mp4', 'aqara.mp4'}
            assert not any('Cámara salón' in (m.get('caption') or m.get('message') or '') for m in messages), messages
            assert not any('No se pudo enviar' in m.get('message', '') for m in messages), messages
            assert hass.states.get('alarm_control_panel.home').state == 'disarmed'

            await command('arm_night')
            expected = await command('pause', minutes=60)
            expected_files = dict(hass.states.get('sensor.alarma_archivos').attributes['entries'])
            print('PASS: real HA scripts, dynamic sensors, Telegram buttons, exclusions, pauses, panel, presence, FTP delay and media failures')
        finally:
            await hass.async_stop()

        # Restore the persisted sensor and deadline in a fresh HA process object.
        restored = HomeAssistant(directory)
        try:
            loader.async_setup(restored)
            restored.config_entries = ConfigEntries(restored, {})
            assert await async_load_base_functionality(restored)
            package = yaml.load_yaml(str(ROOT / 'config/packages/seguridad_alarma.yaml'))
            for domain in ['template', 'input_datetime', 'input_boolean']:
                assert await async_setup_component(restored, domain, package)
            await restored.async_start()
            await restored.async_block_till_done()
            assert restored.states.get('sensor.alarma_contexto').attributes['data'] == expected
            assert restored.states.get('sensor.alarma_archivos').attributes['entries'] == expected_files
            assert restored.states.get('input_datetime.alarma_fin_pausa').attributes['timestamp'] > 0
            print('PASS: context, exclusions and pause deadline survive restart')
        finally:
            await restored.async_stop()


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(run(), timeout=60))
