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
from homeassistant.core import HomeAssistant, SupportsResponse, callback as hass_callback
from homeassistant.exceptions import HomeAssistantError
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
        prepared_paths = []
        delivered_at = []
        failed_uploads = []
        drop_internal_history = False

        async def drop_history(call):
            nonlocal drop_internal_history
            if drop_internal_history:
                drop_internal_history = False
                state = hass.states.get('sensor.alarma_contexto')
                hass.states.async_set(state.entity_id, state.state,
                                      {**state.attributes, 'internal_contexts': []}, context=state.context)

        async def prepare_file(call):
            prepared_at.append(time.monotonic())
            path = call.data['file']
            prepared_paths.append(path)
            if 'failed' in path:
                return {'returncode': 1, 'stdout': '{}'}
            return {'returncode': 0, 'stdout': ''}

        async def notify(call):
            if call.data.get('file', '').endswith('send_failed.jpg'):
                failed_uploads.append(call.data['file'])
                raise HomeAssistantError('Simulated Telegram upload failure')
            if 'file' in call.data:
                delivered_at.append(time.monotonic())
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
            # Fault injection: lose the persisted history after the controller's
            # acknowledgement, immediately before it calls the panel.
            hass.services.async_register('test', 'drop_internal_history', drop_history)
            config['script']['seguridad_controlar']['sequence'].insert(
                2, {'action': 'test.drop_internal_history'})
            old_scripts = yaml.load_yaml(str(ROOT / 'config/scripts.yaml'))
            for name in ['alarm_disarm_telegram', 'alarm_disarm_telegram_temporary', 'goto_sleep']:
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
            open_window = detector('ventana_ya_abierta', [night], 'window')
            hass.states.async_set(open_window, 'on', {'friendly_name': 'Ventana ya abierta', 'device_class': 'window'})
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

            # Exercise the complete voice script -> event -> controller -> panel path.
            # Capture service calls to detect panel feedback reentering the controller.
            service_events = []

            @hass_callback
            def capture_service(event):
                service_events.append(event)

            unsubscribe = hass.bus.async_listen('call_service', capture_service)
            messages.clear()
            await hass.services.async_call('script', 'goto_sleep', {}, blocking=True)
            await hass.async_block_till_done()
            unsubscribe()
            controller_calls = [e for e in service_events if e.data['domain'] == 'script'
                                and e.data['service'] == 'seguridad_controlar']
            panel_calls = [e for e in service_events if e.data['domain'] == 'alarm_control_panel'
                           and e.data['service'] == 'alarm_arm_night']
            assert len(controller_calls) == 1, [e.as_dict() for e in controller_calls]
            assert controller_calls[0].data['service_data']['command'] == 'arm_night'
            assert len(panel_calls) == 1, [e.as_dict() for e in panel_calls]
            internal = hass.states.get('sensor.alarma_contexto').attributes['internal_contexts']
            assert panel_calls[0].context.id in internal, internal
            c = context()
            assert c['mode'] == 'armed_night', c
            assert hass.states.get('alarm_control_panel.home').state == 'armed_night'
            assert sum('Alarma armada en modo noche.' in m.get('message', '') for m in messages) == 1, messages
            assert not any('Movimiento existente' in m.get('message', '') for m in messages), messages
            # Arming reports open windows, but not motion already present.
            assert any('Ventana ya abierta' in m.get('message', '') for m in messages), messages
            assert not any(m.get('message', '').startswith('🚨') for m in messages), messages
            # Positive control: the SAME motion sensor must generate the text
            # above on a fresh off -> on edge. A broken notification path fails here.
            messages.clear()
            motion_attrs = dict(hass.states.get(active_motion).attributes)
            hass.states.async_set(active_motion, 'off', motion_attrs)
            hass.states.async_set(active_motion, 'on', motion_attrs)
            await hass.async_block_till_done()
            assert [m.get('message') for m in messages] == ['🚨 Movimiento detectado: Movimiento existente'], messages
            print('PASS: good-night script calls controller once; internal panel call is filtered; one Telegram arming message')
            await command('disarm')
            messages.clear()
            service_events.clear()
            drop_internal_history = True
            unsubscribe = hass.bus.async_listen('call_service', capture_service)
            await hass.services.async_call('script', 'goto_sleep', {}, blocking=True)
            await hass.async_block_till_done()
            unsubscribe()
            controller_calls = [e for e in service_events if e.data['domain'] == 'script'
                                and e.data['service'] == 'seguridad_controlar']
            assert sum('Alarma armada en modo noche.' in m.get('message', '') for m in messages) == 1, messages
            assert len(controller_calls) == 1, [e.as_dict() for e in controller_calls]
            assert not drop_internal_history, 'Fault injection did not run'
            assert hass.states.get('sensor.alarma_contexto').attributes['internal_contexts'] == []
            assert hass.states.get('alarm_control_panel.home').state == 'armed_night'
            print('PASS: missing internal history does not turn panel feedback into a second arming')
            messages.clear()
            hass.states.async_set(door, 'on', {'friendly_name': 'Puerta', 'device_class': 'door'})
            await hass.async_block_till_done()
            hass.states.async_set(second, 'on', {'friendly_name': 'Ventana', 'device_class': 'window'})
            await hass.async_block_till_done()
            alerts = [m for m in messages if m.get('message') in ['🚨 Apertura detectada: Puerta', '🚨 Apertura detectada: Ventana']]
            assert sorted(m.get('message', '') for m in messages) == ['🚨 Apertura detectada: Puerta', '🚨 Apertura detectada: Ventana'], messages
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

            # Rearming from the panel resets exclusions even in the same mode.
            messages.clear()
            await hass.services.async_call('alarm_control_panel', 'alarm_arm_night',
                                           {'entity_id': 'alarm_control_panel.home'}, blocking=True)
            await hass.async_block_till_done()
            assert context()['excluded'] == [], context()
            assert sum('Alarma armada en modo noche.' in m.get('message', '') for m in messages) == 1, messages
            # Inspect messages BEFORE clearing them: rearming open sensors must
            # not generate new detections. Reopening the excluded door must work.
            assert not any(m.get('message', '').startswith('🚨') for m in messages), messages
            messages.clear()
            door_attrs = {'friendly_name': 'Puerta', 'device_class': 'door'}
            hass.states.async_set(door, 'off', door_attrs)
            hass.states.async_set(door, 'on', door_attrs)
            await hass.async_block_till_done()
            assert [m.get('message') for m in messages] == ['🚨 Apertura detectada: Puerta'], messages

            # Pause can be cancelled even if panel already reads disarmed.
            c = await command('pause', minutes=30)
            assert c['paused_mode'] == 'armed_night' and c['paused_until'] > 0, c
            assert not c['manual_hold'], c
            assert hass.states.get('alarm_control_panel.home').state == 'disarmed'
            await hass.services.async_call('alarm_control_panel', 'alarm_disarm', {'entity_id': 'alarm_control_panel.home'}, blocking=True)
            await hass.async_block_till_done()
            assert context()['paused_until'] == 0 and context()['manual_hold'], context()
            c = await command('resume')
            assert c['mode'] == 'disarmed'

            # A real occupancy off -> on transition must not disarm night mode.
            hass.states.async_set('person.test', 'not_home')
            hass.states.async_set('group.familia', 'not_home', {'entity_id': ['person.test']})
            await hass.async_block_till_done()
            await command('arm_night')
            assert hass.states.get('binary_sensor.alarma_ocupacion').state == 'off'
            hass.states.async_set('person.test', 'home')
            hass.states.async_set('group.familia', 'home', {'entity_id': ['person.test']})
            await hass.async_block_till_done()
            assert hass.states.get('binary_sensor.alarma_ocupacion').state == 'on'
            assert context()['mode'] == 'armed_night', context()
            # Guest mode and the calendar independently prevent away mode.
            messages.clear()
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
            assert not any('manualmente' in m.get('message', '') for m in messages), messages
            assert sum('modo ausente' in m.get('message', '') for m in messages) == 1, messages
            assert sum(m.get('message', '') == '🔓 Alarma desarmada.' for m in messages) == 1, messages

            # Add a new detector after setup, using labels only.
            third = detector('nuevo_detector', [night])
            await command('arm_night')
            messages.clear()
            hass.states.async_set(third, 'on', {'friendly_name': 'Nuevo', 'device_class': 'motion'})
            await hass.async_block_till_done()
            assert [m.get('message') for m in messages] == ['🚨 Movimiento detectado: Nuevo'], messages

            resolved = await hass.services.async_call('script', 'seguridad_resolver_camara',
                {'file_path': '/media/camera/C1_00626E615161/2026/test.mkv'}, blocking=True, return_response=True)
            assert resolved['token'] == 'recibidor', resolved

            # Existing duration buttons reach the new persistent pause controller.
            for duration in [30, 60, 120, 180]:
                before = int(dt_util.utcnow().timestamp())
                hass.bus.async_fire('telegram_callback', {'data': f'/{duration}_mins', 'id': 'duration',
                    'message': {'message_id': 1}, 'chat_id': -123})
                await hass.async_block_till_done()
                after = int(dt_util.utcnow().timestamp())
                assert before + duration * 60 <= context()['paused_until'] <= after + duration * 60, context()
                assert context()['paused_mode'] == 'armed_night', context()
                assert context()['mode'] == 'disarmed', context()
                assert hass.states.get('alarm_control_panel.home').state == 'disarmed'
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
            watcher = 'event.test_folder_watcher'
            entity_sources(hass)[watcher] = {'domain': 'folder_watcher'}
            hass.states.async_set(watcher, '0', {'event_type': 'closed', 'path': ''})
            watcher_revision = 0

            def file_event(path, *, native=False, event_type='closed'):
                nonlocal watcher_revision
                if native:
                    watcher_revision += 1
                    hass.states.async_set(watcher, str(watcher_revision),
                                          {'event_type': event_type, 'path': path})
                else:
                    hass.bus.async_fire('folder_watcher', {'event_type': event_type, 'path': path})

            async def wait_for_reservations(count):
                # Wait for routing/eligibility to finish, not the 15-second upload delay.
                async with asyncio.timeout(5):
                    while len(hass.states.get('sensor.alarma_archivos').attributes.get('entries', {})) < count:
                        await asyncio.sleep(0.01)

            file_event('/media/camera/FoscamCamera_00626ED836A9/interior.mkv')
            for index, path in enumerate([
                '/media/camera/C1_00626E615161/good.mkv',
                '/media/camera/C1_00626E615161/failed.mkv',
                '/media/camera/C1_00626E615161/good.mkv',
                '/media/camera/C1_00626E615161/photo.jpg',
                '/media/camera/puerta_principal/netatmo.mp4',
                '/media/aqara_video/lumi3.99aa9fe51953f04f/aqara.mp4',
                '/media/camera/C1_00626E615161/send_failed.jpg',
            ]):
                file_event(path, native=index % 2 == 0)
            # Conversion output and unrelated events must not become detections.
            file_event('/media/camera/C1_00626E615161/good.mp4')
            file_event('/media/camera/unknown/ignored.mkv', native=True)
            file_event('/media/camera/C1_00626E615161/not_closed.mkv', event_type='created')
            await wait_for_reservations(7)
            # Positive control for the SAME interior camera: adding the alarm
            # label must route its next recording to Telegram. The earlier one
            # must retain its silent classification despite this label change.
            registry.async_update_entity(interior.entity_id, labels={night})
            file_event('/media/camera/FoscamCamera_00626ED836A9/salon_alert.mkv', native=True)
            await wait_for_reservations(8)
            # Eligibility was captured before disarming; new recordings are ignored.
            await command('disarm')
            file_event('/media/camera/C1_00626E615161/after_disarm.mkv')
            try:
                async with asyncio.timeout(20):
                    while not any('No se pudo preparar' in m.get('message', '') for m in messages):
                        await asyncio.sleep(0.05)
            except TimeoutError as err:
                raise AssertionError(f'Expected media preparation failure; messages={messages}, prepared={prepared_at}') from err
            await hass.async_block_till_done()
            assert {Path(p).name for p in prepared_paths} == {'interior.mkv', 'good.mkv', 'failed.mkv', 'salon_alert.mkv'}, prepared_paths
            assert len(prepared_at) == 4, prepared_at
            assert all(t - started >= 14.9 for t in prepared_at), prepared_at
            assert delivered_at and all(t - started >= 14.9 for t in delivered_at), delivered_at
            videos = [m for m in messages if m.get('file', '').endswith('.mp4')]
            assert len([m for m in messages if m.get('file', '').endswith('.jpg')]) == 1, messages
            assert len(videos) == 4 and {m['caption'] for m in videos} == {'🚨 Movimiento detectado: Cámara recibidor', '🚨 Movimiento detectado: entrada', '🚨 Movimiento detectado: caseta', '🚨 Movimiento detectado: Cámara salón'}, messages
            assert {Path(m['file']).name for m in videos} == {'good.mp4', 'netatmo.mp4', 'aqara.mp4', 'salon_alert.mp4'}, messages
            assert len(failed_uploads) == 1, failed_uploads
            assert sorted(m['message'] for m in messages if 'message' in m) == sorted([
                '🔓 Alarma desarmada manualmente.',
                '🚨 Movimiento detectado: Cámara recibidor. No se pudo preparar el archivo adjunto.',
                '🚨 Movimiento detectado: Cámara recibidor. No se pudo enviar el archivo adjunto.',
            ]), messages
            assert hass.states.get('alarm_control_panel.home').state == 'disarmed'

            await command('arm_night')
            await command('exclude', detector=door)
            expected = await command('pause', minutes=60)
            assert expected['excluded'] == [door], expected
            expected_files = dict(hass.states.get('sensor.alarma_archivos').attributes['entries'])
            assert expected_files, 'Persistence must be tested with a nonempty file history'
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
            assert restored.states.get('input_datetime.alarma_fin_pausa').attributes['timestamp'] == expected['paused_until']
            print('PASS: context, exclusions and pause deadline survive restart')
        finally:
            await restored.async_stop()


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(run(), timeout=60))
