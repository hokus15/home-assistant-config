"""Run in a Home Assistant container with simulated readings and services."""

import asyncio
from pathlib import Path
import tempfile

import yaml
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import template
from homeassistant.setup import async_setup_component

ROOT = Path(__file__).resolve().parents[1]
LOWER = 'input_number.calefaccion_temporada_temperatura_activar'
UPPER = 'input_number.calefaccion_temporada_temperatura_desactivar'
FLAG = 'input_boolean.calefaccion_umbrales_inicializado'
SEASON = 'input_boolean.calefaccion_temporada_activo'
VALID = 'binary_sensor.calefaccion_umbrales_validos'
MEAN = 'sensor.home_temperature_stats'


async def run():
    package = yaml.safe_load((ROOT / 'config/packages/confort.yaml').read_text(encoding='utf-8'))
    validation = next(s for s in package['template'][0]['binary_sensor']
                      if s.get('unique_id') == 'calefaccion_umbrales_validos')
    automations = []
    for filename in ['calefaccion_inicializar_umbrales',
                     'calefaccion_recibidor_encender_por_temperatura_media',
                     'calefaccion_recibidor_apagar_por_temperatura_media']:
        automations.extend(yaml.safe_load((ROOT / f'config/automations/{filename}.yaml').read_text(encoding='utf-8')))
    config = {
        'input_boolean': {key: package['input_boolean'][key]
                          for key in [FLAG.split('.')[1], SEASON.split('.')[1]]},
        'input_number': package['input_number'],
        'template': [{'binary_sensor': [validation]}],
        'automation': automations,
    }
    with tempfile.TemporaryDirectory() as directory:
        async def setup():
            hass = HomeAssistant(directory)
            loader.async_setup(hass)
            hass.config_entries = ConfigEntries(hass, {})
            assert await async_load_base_functionality(hass)

            async def fake_service(call):
                pass

            hass.services.async_register('notify', 'send_message', fake_service)
            hass.services.async_register('logbook', 'log', fake_service)
            hass.states.async_set(MEAN, '19')
            for domain in ['input_boolean', 'input_number', 'template', 'automation']:
                assert await async_setup_component(hass, domain, config), domain
            await hass.async_start()
            await hass.async_block_till_done()
            return hass

        hass = await setup()
        try:
            assert float(hass.states.get(LOWER).state) == 18.5, 'First-install lower default'
            assert float(hass.states.get(UPPER).state) == 20, 'First-install upper default'
            assert hass.states.is_state(VALID, 'on'), 'Defaults must be valid'

            async def set_number(entity, value):
                await hass.services.async_call('input_number', 'set_value',
                                               {'entity_id': entity, 'value': value}, blocking=True)
                await hass.async_block_till_done()

            # A threshold edit must evaluate an unchanged mean immediately.
            await set_number(LOWER, 19.5)
            assert hass.states.is_state(SEASON, 'on'), 'Threshold edit must enable season'
            await set_number(UPPER, 19.4)
            assert hass.states.is_state(VALID, 'off'), 'Inverted thresholds must be invalid'
            assert hass.states.is_state(SEASON, 'on'), 'Invalid range must preserve season'
            await set_number(UPPER, 22)
            assert hass.states.is_state(VALID, 'on'), 'Corrected range must recover'
            hass.states.async_set(MEAN, '22.1')
            await hass.async_block_till_done()
            assert hass.states.is_state(SEASON, 'off'), 'Crossing edited upper threshold must disable season'
            hass.states.async_set(MEAN, '19.5')
            await hass.async_block_till_done()
            assert hass.states.is_state(SEASON, 'off'), 'Equality must preserve season'
            hass.states.async_set(MEAN, '19.4')
            await hass.async_block_till_done()
            assert hass.states.is_state(SEASON, 'on'), 'Crossing edited lower threshold must enable season'
            dashboard = yaml.safe_load((ROOT / 'config/dashboards/climatizacion.yaml').read_text(encoding='utf-8'))
            view = next(v for v in dashboard['views'] if v['path'] == 'calefaccion')
            for card in view['cards']:
                if card['type'] == 'markdown':
                    template.Template(card['content'], hass).async_render(parse_result=False)
        finally:
            await hass.async_stop()

        # Reuse storage with a new HA instance to exercise helper restoration.
        hass = await setup()
        try:
            assert float(hass.states.get(LOWER).state) == 19.5, 'Lower threshold must persist'
            assert float(hass.states.get(UPPER).state) == 22, 'Upper threshold must persist'
            assert hass.states.is_state(FLAG, 'on'), 'Initialization flag must persist'
        finally:
            await hass.async_stop()
        print('Heating runtime: defaults, edits, invalid range, crossings, dashboard and restoration OK')


if __name__ == '__main__':
    asyncio.run(run())
