"""Fresh beta reset using real HA options, reload and persistent storage."""
from copy import deepcopy

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.storage import Store
from homeassistant.helpers import area_registry as ar, floor_registry as fr
from homeassistant.setup import async_setup_component

try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import empty_topology, add_item
from custom_components.irpat_efficiency.storage_identity import storage_key, generation


async def test_beta_reset_fresh_session(hass, enable_custom_integrations, hass_ws_client):
    floor = fr.async_get(hass).async_create("Native floor")
    area = ar.async_get(hass).async_create("Native area", floor_id=floor.floor_id)
    t, local_floor = add_item(empty_topology(), "floors", "Old floor")
    t, room = add_item(t, "rooms", "Old room", floor_id=local_floor)
    t, zone = add_item(t, "zones", "Old zone")
    t, source = add_item(t, "sources", "Old source", source_type="heat_pump", zone_ids=[zone])
    t, manifold = add_item(t, "manifolds", "Old distributor", floor_id=local_floor, zone_id=zone)
    t, _ = add_item(t, "circuits", "Old circuit", manifold_id=manifold, room_id=room, position=1)
    t, _ = add_item(t, "bindings", "Room sensor", room_id=room, entity_id="sensor.beta_temperature")
    t["outdoor_entity_id"] = "sensor.beta_outdoor"
    hass.states.async_set("sensor.beta_temperature", "21", {"unit_of_measurement": "°C"})
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={"operating_mode":"weather_compensated"},
                            options={"topology": t})
    entry.add_to_hass(hass)
    old_records = {
        "reports": {"observations": [], "reports": []},
        "journal": {"entries": [{"id": "old-journal"}]},
        "profiles": {"profiles": [{"id": "old-profile"}]},
        "history": {"rooms": {room: {"0": 21}}, "configuration_hash": "old", "configuration_since": 0},
        "defrost": {"events": [{"source_id":source, "end": 123}]},
        "energy": {"sources": {}},
        "fuel": {"sources": {}},
        "modes": {"events": [{"source_id":source, "observed_at":123}]},
    }
    old_keys = {kind:storage_key(entry, kind) for kind in old_records}
    for kind, data in old_records.items():
        await Store(hass, 1, old_keys[kind]).async_save(deepcopy(data))
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    fid = result["flow_id"]
    result = await manager.async_configure(fid, {"next_step_id":"manage_menu"})
    assert "beta_reset" in result["menu_options"]
    result = await manager.async_configure(fid, {"next_step_id":"beta_reset"})
    result = await manager.async_configure(fid, {"confirmation":"wrong", "confirmed":True})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "beta_reset_confirmation"
    assert entry.options["topology"] == t
    result = await manager.async_configure(fid, {"confirmation":"RESET", "confirmed":False})
    assert result["type"] is FlowResultType.FORM
    assert generation(entry) is None
    result = await manager.async_configure(fid, {"confirmation":"RESET", "confirmed":True, "cancel":True})
    assert result["step_id"] == "manage_menu"
    assert entry.options["topology"] == t
    # Create a confirmed, automatically saved change before reset.
    result = await manager.async_configure(fid, {"next_step_id":"overview_menu"})
    result = await manager.async_configure(fid, {"next_step_id":"building_menu"})
    result = await manager.async_configure(fid, {"next_step_id":"floor"})
    result = await manager.async_configure(fid, {"next_step_id":"floor_custom"})
    result = await manager.async_configure(fid, {"name":"Autosaved floor"})
    assert result["description_placeholders"]["pending"] == "0"
    assert any(f["name"] == "Autosaved floor" for f in entry.options["topology"]["floors"])
    result = await manager.async_configure(fid, {"next_step_id":"overview_menu"})
    result = await manager.async_configure(fid, {"next_step_id":"manage_menu"})
    result = await manager.async_configure(fid, {"next_step_id":"beta_reset"})
    result = await manager.async_configure(fid, {"confirmation":"RESET", "confirmed":True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["topology"] == empty_topology()
    assert generation(entry)
    assert entry.state is ConfigEntryState.LOADED
    # No prior generation is loaded after reset, even after an explicit reload.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    runtime = hass.data[DOMAIN]
    eid = entry.entry_id
    assert runtime["histories"][eid].data == {}
    assert runtime["journals"][eid].entries == []
    assert runtime["profiles"][eid].profiles == []
    assert runtime["report_stores"][eid].data == {"observations": [], "reports": []}
    assert runtime["defrost_monitors"][eid].journal.committed == []
    assert runtime["mode_monitors"][eid].journal.committed == []
    assert runtime["energy_monitors"][eid].history.data == {}
    assert runtime["energy_monitors"][eid].fuel.history.data == {}
    for kind, key in old_keys.items():
        assert storage_key(entry, kind) != key
    assert (await Store(hass, 1, old_keys["journal"]).async_load()) == old_records["journal"]
    assert ar.async_get(hass).async_get_area(area.id) is not None
    assert fr.async_get(hass).async_get_floor(floor.floor_id) is not None
    assert hass.states.get("sensor.beta_temperature").state == "21"
    result = await manager.async_init(entry.entry_id)
    assert result["description_placeholders"]["pending"] == "0"
    assert result["description_placeholders"]["rooms"] == "0"
    manager.async_abort(result["flow_id"])
    client = await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/overview"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"][0]["topology"] == empty_topology()
    assert response["result"][0]["journal"] == []
