"""Native configuration, journal and profile persistence in actual HA Core."""
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import add_item, empty_topology


async def test_native_options_edit_and_save(hass: HomeAssistant, enable_custom_integrations):
    topology, floor = add_item(empty_topology(), "floors", "Test floor")
    topology, room = add_item(topology, "rooms", "Original", floor_id=floor, heating_target_c=22)
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": topology})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    flow_id = result["flow_id"]
    assert result["type"] is FlowResultType.MENU
    assert "edit" in result["menu_options"]
    result = await manager.async_configure(flow_id, {"next_step_id": "edit"})
    assert result["step_id"] == "edit"
    result = await manager.async_configure(flow_id, {"collection": "rooms"})
    assert result["step_id"] == "edit_select"
    result = await manager.async_configure(flow_id, {"item_id": room})
    assert result["step_id"] == "edit_item"
    result = await manager.async_configure(flow_id, {"name": "Renamed room", "heating_target_c": 23})
    assert result["type"] is FlowResultType.MENU, result
    # Confirming an edit applies it before closing the menu.
    assert entry.options["topology"]["rooms"][0]["name"] == "Renamed room"
    result = await manager.async_configure(flow_id, {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    stored = entry.options["topology"]["rooms"][0]
    assert stored["id"] == room
    assert stored["floor_id"] == floor
    assert stored["name"] == "Renamed room"
    assert stored["heating_target_c"] == 23
    assert entry.state is ConfigEntryState.LOADED


async def test_journal_profile_survive_reload(hass: HomeAssistant, hass_ws_client, enable_custom_integrations):
    topology, floor = add_item(empty_topology(), "floors", "Floor")
    topology, zone = add_item(topology, "zones", "Zone")
    topology, room = add_item(topology, "rooms", "Room", floor_id=floor)
    topology, manifold = add_item(topology, "manifolds", "Manifold", floor_id=floor, zone_id=zone)
    topology, circuit = add_item(topology, "circuits", "Circuit", manifold_id=manifold, room_id=room, position=1)
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": topology})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    sequence = 0

    async def call(command, **fields):
        nonlocal sequence
        sequence += 1
        await client.send_json({"id": sequence, "type": f"{DOMAIN}/{command}",
                                "entry_id": entry.entry_id, **fields})
        response = await client.receive_json()
        assert response["success"], response
        return response["result"]

    initial = await call("journal_append", manifold_id=manifold, readings={circuit: 1.2},
                         phase="observation")
    profile = await call("profile_create", zone_id=zone, name="Reference",
                         mode="heating", snapshot_ids=[initial["id"]])
    later = await call("journal_append", manifold_id=manifold, readings={circuit: 0.9},
                       phase="observation")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    result = await call("profile_review", profile_id=profile["id"], snapshot_id=later["id"])
    assert result["automatic_restore"] is False
    assert result["rows"][0]["circuit_id"] == circuit
    assert result["rows"][0]["reference_lmin"] == 1.2
    assert result["rows"][0]["observed_lmin"] == 0.9
    assert abs(result["rows"][0]["difference_lmin"] + 0.3) < 1e-9


async def test_non_admin_cannot_read_or_modify(hass: HomeAssistant, hass_ws_client,
                                               hass_admin_user, enable_custom_integrations):
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": empty_topology()})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    # Same permission downgrade used by Home Assistant's websocket tests.
    hass_admin_user.groups = []
    assert not hass_admin_user.is_admin
    commands = [
        {"type": f"{DOMAIN}/overview"},
        {"type": f"{DOMAIN}/configuration", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/configuration_action", "entry_id": entry.entry_id,
         "revision":"invalid", "action":"add_floor", "payload":{"name":"Forbidden"}},
        {"type": f"{DOMAIN}/export_data", "entry_id": entry.entry_id, "format": "json"},
        {"type": f"{DOMAIN}/journal_append", "entry_id": entry.entry_id,
         "manifold_id": "unknown", "readings": {"unknown": 1}, "phase": "observation"},
    ]
    for sequence, command in enumerate(commands, 1):
        await client.send_json({"id": sequence, **command})
        result = await client.receive_json()
        assert not result["success"], result
        assert result["error"]["code"] == "unauthorized", result
