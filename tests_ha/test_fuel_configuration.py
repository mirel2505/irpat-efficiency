"""Verify native economics options and meter validation on actual HA Core."""
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import add_item, empty_topology
from custom_components.irpat_efficiency.source_settings import set_source_settings
from custom_components.irpat_efficiency.fuel_economics import economic_overview


async def test_fuel_configuration_and_meter(hass, enable_custom_integrations, hass_ws_client):
    t, zone = add_item(empty_topology(), "zones", "Zone")
    t, hp = add_item(t, "sources", "Heat pump", source_type="heat_pump", zone_ids=[zone])
    t, gas = add_item(t, "sources", "Boiler", source_type="gas", zone_ids=[zone])
    t = set_source_settings(t, hp, tariff=1.2, currency="RON")
    t = set_source_settings(t, gas, tariff=1.2, currency="RON")
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": t})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    result = await manager.async_configure(result["flow_id"], {"next_step_id": "all_actions"})
    fid = result["flow_id"]
    assert "economic_source" in result["menu_options"] and "hybrid_zone" in result["menu_options"]
    result = await manager.async_configure(fid, {"next_step_id": "economic_source"})
    result = await manager.async_configure(fid, {"source_id": gas})
    assert result["step_id"] == "fuel_properties"
    hass.states.async_set("sensor.test_gas", "10", {"unit_of_measurement": "m³", "state_class": "total_increasing"})
    result = await manager.async_configure(fid, {
        "kind":"natural_gas", "basis":"HHV", "billing_unit":"kWh", "tariff":.3,
        "fuel_currency":"RON", "meter_entity":"sensor.test_gas", "meter_unit":"m3",
        "meter_kwh_per_unit":10.5, "efficiency_percent":90, "auxiliary_kwh_per_heat_kwh":.01})
    assert result["type"] is FlowResultType.MENU, result
    result = await manager.async_configure(fid, {"next_step_id":"economic_source"})
    result = await manager.async_configure(fid, {"source_id":hp})
    assert result["step_id"] == "electric_scenario"
    result = await manager.async_configure(fid, {"cop":4})
    assert result["type"] is FlowResultType.MENU, result
    result = await manager.async_configure(fid, {"next_step_id":"hybrid_zone"})
    result = await manager.async_configure(fid, {"zone_id":zone})
    assert result["step_id"] == "hybrid_policy"
    result = await manager.async_configure(fid, {"strategy":"alternate","threshold_c":-5})
    assert result["type"] is FlowResultType.MENU, result
    result = await manager.async_configure(fid, {"next_step_id":"save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    t = entry.options["topology"]
    assert t["zones"][0]["declared_switch_c"] == -5
    monitor = hass.data[DOMAIN]["energy_monitors"][entry.entry_id].fuel
    sample = monitor.samples(t, dt_util.utcnow().timestamp())[gas]
    assert sample["status"] == "reported" and sample["value"] == 105
    hass.states.async_set("sensor.test_gas", "10", {"unit_of_measurement": "kg", "state_class": "total_increasing"})
    assert monitor.samples(t, dt_util.utcnow().timestamp())[gas]["status"] != "reported"
    assert economic_overview(t)["comparisons"]
    client = await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/overview"})
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"][0]["economics"]["comparisons"]
    assert gas in response["result"][0]["fuel_history"]
