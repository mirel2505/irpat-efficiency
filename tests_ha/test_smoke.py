"""Run against real Home Assistant Core, not stubbed integration modules."""
import json
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import add_item, empty_topology


async def test_setup_overview_reload(hass: HomeAssistant, hass_ws_client, enable_custom_integrations):
    topology, floor = add_item(empty_topology(), 'floors', 'Test floor')
    topology, room = add_item(topology, 'rooms', 'Test room', floor_id=floor, heating_target_c=22)
    topology, _ = add_item(topology, 'bindings', 'Test sensor', room_id=room, entity_id='sensor.test_temperature')
    hass.states.async_set('sensor.test_temperature', '21.5', {'unit_of_measurement': '°C'})
    entry = MockConfigEntry(domain=DOMAIN, title='Test installation', data={}, options={'topology': topology})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    client = await hass_ws_client(hass)
    await client.send_json({'id': 1, 'type': f'{DOMAIN}/overview'})
    response = await client.receive_json()
    assert response['success'], response
    overview = response['result'][0]
    assert overview['entry_id'] == entry.entry_id
    assert overview['room_temperatures'][room]['heating']['temperature_c'] == 21.5
    assert overview['defrost'] == {}
    assert overview['energy_history'] == {}
    await client.send_json({'id': 10, 'type': f'{DOMAIN}/export_data',
                            'entry_id': entry.entry_id, 'format': 'json'})
    exported = await client.receive_json()
    assert exported['success'], exported
    archive = json.loads(exported['result']['content'])
    assert archive['format'] == 'irpat_efficiency.export'
    assert archive['entry_id'] == entry.entry_id
    assert archive['topology'] == topology
    assert archive['restore_supported'] is False
    await client.send_json({'id': 11, 'type': f'{DOMAIN}/export_data',
                            'entry_id': entry.entry_id, 'format': 'csv', 'section': 'temperatures'})
    exported = await client.receive_json()
    assert exported['success'], exported
    assert exported['result']['mime'] == 'text/csv'
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    await client.send_json({'id': 2, 'type': f'{DOMAIN}/overview'})
    response = await client.receive_json()
    assert response['success'], response
    assert len(response['result']) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    await client.send_json({'id': 3, 'type': f'{DOMAIN}/overview'})
    response = await client.receive_json()
    assert response['success'], response
    assert response['result'] == []
    await client.send_json({'id': 12, 'type': f'{DOMAIN}/export_data',
                            'entry_id': entry.entry_id, 'format': 'json'})
    exported = await client.receive_json()
    assert not exported['success']
    assert exported['error']['code'] == 'not_found'
