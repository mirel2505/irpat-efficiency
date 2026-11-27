"""Exercise native registry import in real Home Assistant Core."""
from homeassistant.helpers import area_registry as ar, floor_registry as fr
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import empty_topology, add_item
from custom_components.irpat_efficiency.ha_registry_reader import read_structure, read_entities


async def test_native_registry_import(hass, enable_custom_integrations):
    floors = fr.async_get(hass)
    areas = ar.async_get(hass)
    floor = floors.async_create("Ground")
    area = areas.async_create("Bedroom", floor_id=floor.floor_id)
    topology, local_floor = add_item(empty_topology(), "floors", "Ground")
    topology, local_room = add_item(topology, "rooms", "Bedroom", floor_id=local_floor, heating_target_c=22)
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": topology})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    flow_id = result["flow_id"]
    assert "import_structure" in result["menu_options"]
    result = await manager.async_configure(flow_id, {"next_step_id": "import_structure"})
    assert result["step_id"] == "import_structure"
    result = await manager.async_configure(flow_id, {"confirmed": True})
    assert result["type"] is FlowResultType.MENU, result
    assert "discover_sensors" in result["menu_options"]
    assert "ha_area_id" not in entry.options["topology"]["rooms"][0]
    result = await manager.async_configure(flow_id, {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    t = entry.options["topology"]
    assert len(t["floors"]) == len(t["rooms"]) == 1
    assert t["floors"][0]["id"] == local_floor
    assert t["floors"][0]["ha_floor_id"] == floor.floor_id
    assert t["rooms"][0]["id"] == local_room
    assert t["rooms"][0]["ha_area_id"] == area.id
    assert t["rooms"][0]["heating_target_c"] == 22
    assert read_structure(hass) == ({floor.floor_id: "Ground"},
        {area.id: {"name": "Bedroom", "floor_id": floor.floor_id}})


async def test_native_room_selection_and_sensor_confirmation(hass, enable_custom_integrations):
    floor = fr.async_get(hass).async_create("Ground")
    area = ar.async_get(hass).async_create("Bedroom", floor_id=floor.floor_id)
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": empty_topology()})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    sensor = registry.async_get_or_create("sensor", "test", "temperature", suggested_object_id="bedroom_temperature",
                                         original_device_class="temperature")
    registry.async_update_entity(sensor.entity_id, area_id=area.id)
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    fid = result["flow_id"]
    result = await manager.async_configure(fid, {"next_step_id": "room"})
    assert "room_existing" in result["menu_options"]
    result = await manager.async_configure(fid, {"next_step_id": "room_existing"})
    assert result["step_id"] == "room_existing"
    result = await manager.async_configure(fid, {"ha_area_id": area.id, "area_m2": 17.75,
                                                  "heating_target_c": 22})
    assert result["step_id"] == "confirm_sensors", result
    result = await manager.async_configure(fid, {"temperatures": [sensor.entity_id]})
    assert result["type"] is FlowResultType.MENU, result
    result = await manager.async_configure(fid, {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    t = entry.options["topology"]
    assert len(t["rooms"]) == len(t["floors"]) == len(t["bindings"]) == 1
    assert t["rooms"][0]["area_m2"] == 17.75
    assert t["rooms"][0]["heating_target_c"] == 22
    assert t["bindings"][0]["entity_id"] == sensor.entity_id
    assert t["bindings"][0]["room_id"] == t["rooms"][0]["id"]
    assert registry.async_get(sensor.entity_id).area_id == area.id


async def test_guided_room_and_batch_removal(hass, enable_custom_integrations):
    floor = fr.async_get(hass).async_create("Ground")
    area = ar.async_get(hass).async_create("Bedroom", floor_id=floor.floor_id)
    t, local_floor = add_item(empty_topology(), "floors", "Ground")
    t, zone = add_item(t, "zones", "Heating")
    t, spare = add_item(t, "zones", "Unused")
    t, manifold = add_item(t, "manifolds", "Distributor", floor_id=local_floor, zone_id=zone)
    t, source = add_item(t, "sources", "HP", source_type="heat_pump", zone_ids=[zone, spare])
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": t})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    sensor = registry.async_get_or_create("sensor", "test", "temp", suggested_object_id="bedroom_temp",
                                         original_device_class="temperature")
    registry.async_update_entity(sensor.entity_id, area_id=area.id)
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    fid = result["flow_id"]
    assert result["menu_options"] == ["building_menu", "hydraulics_menu", "rooms_menu", "sources_menu",
                                      "manage_menu", "all_actions", "save"]
    result = await manager.async_configure(fid, {"next_step_id": "rooms_menu"})
    assert result["step_id"] == "rooms_menu"
    result = await manager.async_configure(fid, {"next_step_id": "room"})
    result = await manager.async_configure(fid, {"next_step_id": "room_existing"})
    result = await manager.async_configure(fid, {"ha_area_id": area.id, "area_m2": 17.75,
                                                 "heating_target_c": 22})
    assert result["step_id"] == "room_complete", result
    result = await manager.async_configure(fid, {"temperatures": [sensor.entity_id],
                                                "manifold_id": manifold, "count": 2, "positions": "2,4"})
    assert result["step_id"] == "rooms_menu", result
    assert result["description_placeholders"]["missing_sensors"] == "0"
    assert result["description_placeholders"]["missing_circuits"] == "0"
    result = await manager.async_configure(fid, {"next_step_id": "overview_menu"})
    result = await manager.async_configure(fid, {"next_step_id": "manage_menu"})
    result = await manager.async_configure(fid, {"next_step_id": "remove"})
    result = await manager.async_configure(fid, {"collection": "zones"})
    result = await manager.async_configure(fid, {"item_ids": [spare]})
    assert result["step_id"] == "remove_confirm", result
    assert result["description_placeholders"]["sources"] == "HP"
    result = await manager.async_configure(fid, {"confirmed": True, "detach_zone_sources": True})
    assert result["step_id"] == "manage_menu", result
    result = await manager.async_configure(fid, {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    stored = entry.options["topology"]
    assert len(stored["zones"]) == 1
    assert stored["sources"][0]["id"] == source
    assert stored["sources"][0]["zone_ids"] == [zone]
    assert len(stored["rooms"]) == 1
    assert len(stored["bindings"]) == 1
    assert [c["position"] for c in stored["circuits"]] == [2, 4]
