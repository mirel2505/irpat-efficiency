"""Regression for source selector failure and interrupted configuration sessions."""
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


async def test_source_settings_and_draft_survive_cancel(hass, enable_custom_integrations):
    topology, zone = add_item(empty_topology(), "zones", "Zone")
    topology, source = add_item(topology, "sources", "PDC", source_type="heat_pump", zone_ids=[zone])
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": topology})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    fid = result["flow_id"]
    # Use custom floor form with an empty HA floor registry.
    result = await manager.async_configure(fid, {"next_step_id": "floor"})
    assert result["step_id"] == "floor_custom"
    result = await manager.async_configure(fid, {"name": "Ground"})
    assert result["type"] is FlowResultType.MENU
    assert "discard_draft" in result["menu_options"]
    assert entry.options["topology"]["floors"] == []
    result = await manager.async_configure(fid, {"next_step_id": "source_settings"})
    result = await manager.async_configure(fid, {"source_id": source})
    assert result["step_id"] == "source_properties"
    result = await manager.async_configure(fid, {
        "fluid_type": "propylene_glycol", "density_kg_m3": 1030, "cp_j_kgk": 3600,
        "tariff": 1.16, "currency": "RON", "power_boundary_confirmed": False,
        "energy_boundary_confirmed": False})
    assert result["type"] is FlowResultType.MENU, result
    # Mimic pressing X without applying the configuration.
    manager.async_abort(fid)
    assert entry.options["topology"] == topology
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    fid = result["flow_id"]
    assert "discard_draft" in result["menu_options"]
    assert "room" in result["menu_options"]
    result = await manager.async_configure(fid, {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    saved = entry.options["topology"]
    assert saved["floors"][0]["name"] == "Ground"
    assert saved["sources"][0]["tariff"] == 1.16
    assert saved["sources"][0]["fluid_type"] == "propylene_glycol"
    assert saved["sources"][0]["id"] == source
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    assert "discard_draft" not in result["menu_options"]
    manager.async_abort(result["flow_id"])


async def test_discard_draft_retains_saved_configuration(hass, enable_custom_integrations):
    topology, _ = add_item(empty_topology(), "floors", "Saved floor")
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": topology})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    fid = result["flow_id"]
    result = await manager.async_configure(fid, {"next_step_id": "floor"})
    result = await manager.async_configure(fid, {"name": "Draft floor"})
    assert "discard_draft" in result["menu_options"]
    result = await manager.async_configure(fid, {"next_step_id": "discard_draft"})
    result = await manager.async_configure(fid, {"confirmed": True})
    assert result["type"] is FlowResultType.MENU
    assert "discard_draft" not in result["menu_options"]
    manager.async_abort(fid)
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    assert "discard_draft" not in result["menu_options"]
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["topology"] == topology
