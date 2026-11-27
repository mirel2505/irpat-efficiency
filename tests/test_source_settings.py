import unittest
from custom_components.irpat_efficiency.source_settings import set_source_settings, estimate_cost


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.topology = {'sources': [{'id': 's', 'name': 'Source'}]}

    def source(self, **kwargs):
        return set_source_settings(self.topology, 's', **kwargs)['sources'][0]

    def test_default_is_unknown(self):
        s = self.source()
        self.assertIsNone(s['density_kg_m3'])
        self.assertIsNone(s['cp_j_kgk'])
        self.assertFalse(s['power_boundary_confirmed'])
        self.assertFalse(s['energy_boundary_confirmed'])

    def test_glycol_explicit(self):
        s = self.source(fluid_type='propylene_glycol', density_kg_m3=1040, cp_j_kgk=3650)
        self.assertEqual(s['cp_j_kgk'], 3650)
        self.assertNotIn('fluid_type', self.topology['sources'][0])

    def test_no_water_defaults(self):
        self.assertIsNone(self.source(fluid_type='water')['density_kg_m3'])

    def test_invalid_properties(self):
        for fields in ({'density_kg_m3': 1000}, {'density_kg_m3': 1000, 'cp_j_kgk': 4180},
                       {'fluid_type': 'water', 'density_kg_m3': True, 'cp_j_kgk': 4180},
                       {'fluid_type': 'water', 'density_kg_m3': 1000, 'cp_j_kgk': float('nan')}):
            with self.assertRaises(ValueError):
                self.source(**fields)

    def test_boundary_separate(self):
        s = self.source(power_boundary_confirmed=True)
        self.assertTrue(s['power_boundary_confirmed'])
        self.assertFalse(s['energy_boundary_confirmed'])
        with self.assertRaises(ValueError):
            self.source(power_boundary_confirmed=1)

    def test_cost(self):
        s = self.source(tariff=1.16, currency='ron')
        self.assertAlmostEqual(estimate_cost(12, s)['amount'], 13.92)
        self.assertEqual(estimate_cost(12, s)['currency'], 'RON')
        self.assertEqual(estimate_cost(0, s)['amount'], 0)
        self.assertIsNone(estimate_cost(None, s))
        self.assertIsNone(estimate_cost(12, self.source()))

    def test_invalid_tariff(self):
        for fields in ({'tariff': 1}, {'tariff': -1, 'currency': 'RON'},
                       {'tariff': 1, 'currency': '12A'}):
            with self.assertRaises(ValueError):
                self.source(**fields)

    def test_unknown_source(self):
        with self.assertRaises(ValueError):
            set_source_settings(self.topology, 'missing')
