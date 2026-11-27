import unittest
from datetime import timezone
from copy import deepcopy
from custom_components.irpat_efficiency.topology import empty_topology, add_item
from custom_components.irpat_efficiency.source_settings import set_source_settings
from custom_components.irpat_efficiency.fuel_economics import (
    configure_fuel, configure_electric_scenario, configure_strategy, fuel_cost, economic_overview, factor
)
from custom_components.irpat_efficiency.energy_store import EnergyStore


class FuelTests(unittest.TestCase):
    def setUp(self):
        t, self.z = add_item(empty_topology(), "zones", "Zone")
        t, self.hp = add_item(t, "sources", "HP", source_type="heat_pump", zone_ids=[self.z])
        t, self.gas = add_item(t, "sources", "Gas", source_type="gas", zone_ids=[self.z])
        self.t = set_source_settings(t, self.hp, tariff=1.2, currency="EUR")
        self.t = set_source_settings(self.t, self.gas, tariff=1.2, currency="EUR")

    def configure(self, **kw):
        args = dict(kind="natural_gas", basis="HHV", billing_unit="kWh", tariff=.3, fuel_currency="EUR",
                    meter_entity="sensor.gas", meter_unit="m3", meter_kwh_per_unit=10.5,
                    efficiency_percent=90, auxiliary_kwh_per_heat_kwh=.01)
        args.update(kw)
        return configure_fuel(self.t, self.gas, **args)

    def test_gas_meter_and_billing_units(self):
        t = self.configure()
        f = t["sources"][1]["fuel"]
        self.assertEqual(f["meter_kwh_per_unit"], 10.5)
        self.assertEqual(f["billing_kwh_per_unit"], 1)
        self.assertAlmostEqual(fuel_cost(21, f)["amount"], 6.3)
        self.assertNotIn("fuel", self.t["sources"][1])

    def test_lpg_liters_and_kg(self):
        f = self.configure(kind="lpg", basis="LHV", billing_unit="L", tariff=4.5,
                           billing_kwh_per_unit=6.5, meter_unit="kg", meter_kwh_per_unit=13)["sources"][1]["fuel"]
        self.assertAlmostEqual(fuel_cost(26, f)["quantity"], 4)
        self.assertAlmostEqual(fuel_cost(26, f)["amount"], 18)

    def test_cylinder_and_sack(self):
        for unit in ("cylinder", "bag", "t", "Gcal"):
            f = self.configure(billing_unit=unit, billing_kwh_per_unit=100)["sources"][1]["fuel"]
            self.assertAlmostEqual(fuel_cost(200, f)["quantity"], 2)

    def test_factor_validation(self):
        for unit, value in [("m3", None), ("kWh", 10), ("kg", 0), ("L", float("nan"))]:
            with self.assertRaises(ValueError):
                factor(unit, value)
        self.assertEqual(factor("MWh"), 1000)
        with self.assertRaisesRegex(ValueError, "invalid_fuel_factor"):
            self.configure(billing_unit="m3", billing_kwh_per_unit=11)

    def test_basis_and_efficiency(self):
        with self.assertRaisesRegex(ValueError, "invalid_fuel_efficiency"):
            self.configure(efficiency_percent=105)
        self.configure(basis="LHV", efficiency_percent=105)
        with self.assertRaisesRegex(ValueError, "invalid_fuel_basis"):
            self.configure(basis="delivered_heat")

    def test_break_even_includes_auxiliary(self):
        t = configure_electric_scenario(self.configure(), self.hp, 4)
        result = economic_overview(t)
        gas = result["modeled"][self.gas]
        self.assertAlmostEqual(gas["amount"], .3/.9 + .01*1.2)
        self.assertAlmostEqual(result["modeled"][self.hp]["amount"], .3)
        self.assertAlmostEqual(result["comparisons"][0]["break_even_cop"], 1.2/gas["amount"])
        self.assertTrue(result["comparisons"][0]["advisory_only"])

    def test_unknown_aux_or_other_currency_blocks_comparison(self):
        for kw in [dict(auxiliary_kwh_per_heat_kwh=None), dict(fuel_currency="RON")]:
            result = economic_overview(self.configure(**kw))
            self.assertFalse(result["modeled"][self.gas]["complete"])
            self.assertEqual(result["comparisons"], [])
        self.assertTrue(economic_overview(self.configure(auxiliary_kwh_per_heat_kwh=0))["comparisons"])

    def test_strategy_no_mode_inference(self):
        t = configure_strategy(self.t, self.z, "alternate", -5)
        self.assertEqual(t["zones"][0]["declared_switch_c"], -5)
        self.assertEqual(t["sources"], self.t["sources"])
        with self.assertRaises(ValueError):
            configure_strategy(t, self.z, "bad")


class Disk:
    data = None
    async def async_load(self):
        return deepcopy(self.data)
    async def async_save(self, data):
        self.data = deepcopy(data)


class FuelLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_conversion_epoch_and_shared_guard(self):
        store = EnergyStore(Disk())
        def sample(t, v, factor=10, blocked=False):
            return {"gas": {"entity_id": "sensor.gas", "value": v*factor, "timestamp": t,
                           "status": "reported", "signature_extra": ["gas","HHV","m3",factor],
                           "blocked": blocked}}
        async def add(t, v, factor=10, blocked=False):
            await store.async_sample(sample(t,v,factor,blocked),t,timezone.utc)
        def row(t,factor=10,blocked=False):
            return store.overview(sample(t,0,factor,blocked),t,timezone.utc)["gas"]["daily"]
        await add(0, 10)
        await add(300, 11)
        self.assertEqual(row(300)["electric_kwh"], 10)
        await add(600, 12, 11)
        self.assertIsNone(row(600,11)["electric_kwh"])
        await add(900,13,11)
        self.assertEqual(row(900,11)["electric_kwh"],11)
        await add(1200,14,11,True)
        self.assertEqual(row(1200,11,True)["status"],"shared_meter")
        self.assertIsNone(row(1200,11,True)["electric_kwh"])
