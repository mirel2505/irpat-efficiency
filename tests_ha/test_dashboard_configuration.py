"""Real Core graphical configuration WebSocket workflow."""
from homeassistant.helpers import area_registry as ar, floor_registry as fr, entity_registry as er
from homeassistant.setup import async_setup_component
try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import empty_topology


async def test_graphical_configuration(hass, hass_ws_client, enable_custom_integrations):
    floor = fr.async_get(hass).async_create("Ground")
    area = ar.async_get(hass).async_create("Bedroom", floor_id=floor.floor_id)
    registry = er.async_get(hass)
    sensor = registry.async_get_or_create("sensor", "test", "temperature", original_device_class="temperature")
    registry.async_update_entity(sensor.entity_id, area_id=area.id)
    hass.states.async_set(sensor.entity_id, "21.5", {"device_class": "temperature", "unit_of_measurement": "°C"})
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": empty_topology()})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    seq = 0
    async def call(command, **fields):
        nonlocal seq
        seq += 1
        await client.send_json({"id": seq, "type": f"{DOMAIN}/{command}", "entry_id": entry.entry_id, **fields})
        return await client.receive_json()
    response = await call("configuration")
    assert response["success"], response
    state = response["result"]
    async def action(name, **payload):
        nonlocal state
        result = await call("configuration_action", revision=state["revision"], action=name, payload=payload)
        assert result["success"], result
        state = result["result"]
        return state["topology"]
    initial_revision = state["revision"]
    t = await action("import")
    room = t["rooms"][0]["id"]
    assert t["bindings"][0]["entity_id"] == sensor.entity_id
    assert state["room_temperatures"][room]["heating"]["temperature_c"] == 21.5
    t = await action("add_manifold", name="Distributor", floor_id=t["floors"][0]["id"], count=2, zone_name="Heating")
    first = t["circuits"][0]["id"]
    t = await action("map_circuit", id=first, room_id=room)
    assert t["circuits"][-1]["room_id"] == room
    assert t["circuits"][-1]["id"] != first
    t = await action("add_source", name="Heat pump", source_type="heat_pump", zone_ids=[t["zones"][0]["id"]])
    assert t == entry.options["topology"]
    result = await call("configuration_action", revision=initial_revision, action="add_floor", payload={"name":"Stale"})
    assert not result["success"] and result["error"]["code"] == "configuration_changed"
    result = await call("configuration_action", revision=state["revision"], action="remove", payload={"collection":"rooms","id":room,"confirmed":True})
    assert not result["success"] and result["error"]["code"] == "object_in_use"
    await client.send_json({"id":seq+1,"type":f"{DOMAIN}/overview"})
    result = await client.receive_json()
    assert result["success"], result
    assert result["result"][0]["topology"] == t
