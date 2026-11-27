import unittest
from custom_components.irpat_efficiency.topology import add_item, empty_topology
from custom_components.irpat_efficiency.topology_edit import edit_item
from custom_components.irpat_efficiency.journal import make_snapshot
from custom_components.irpat_efficiency.profiles import create_profile
from custom_components.irpat_efficiency.profile_review import review_profile


class ReviewTests(unittest.TestCase):
    def setUp(self):
        t, floor = add_item(empty_topology(), 'floors', 'Floor')
        t, zone = add_item(t, 'zones', 'Zone')
        t, self.mid = add_item(t, 'manifolds', 'Manifold', floor_id=floor, zone_id=zone)
        t, self.b = add_item(t, 'circuits', 'B', manifold_id=self.mid, position=2)
        t, self.a = add_item(t, 'circuits', 'A', manifold_id=self.mid, position=1)
        self.t = t
        ref = make_snapshot(t, self.mid, {self.a: 1.2, self.b: 0.9})
        self.profile = create_profile('Reference', t, zone, [ref], 'heating')
        self.obs = make_snapshot(t, self.mid, {self.a: 0, self.b: 1.1})

    def test_difference_order_and_zero(self):
        result = review_profile(self.t, self.profile, self.obs)
        a, b = result['rows']
        self.assertEqual(a['circuit_id'], self.a)
        self.assertEqual(a['observed_lmin'], 0)
        self.assertAlmostEqual(a['difference_lmin'], -1.2)
        self.assertAlmostEqual(b['difference_lmin'], 0.2)
        self.assertFalse(result['automatic_restore'])
        self.assertFalse(result['comparable_confirmed'])

    def test_missing_observation_not_zero(self):
        obs = make_snapshot(self.t, self.mid, {self.a: 1.2})
        self.assertIsNone(review_profile(self.t, self.profile, obs)['rows'][1]['difference_lmin'])

    def test_rename_uses_current_label(self):
        t = edit_item(self.t, 'circuits', self.a, 'Renamed')
        self.assertEqual(review_profile(t, self.profile, self.obs)['rows'][0]['name'], 'Renamed')

    def test_reject_extra_historical_circuit(self):
        self.obs['flows_lmin']['retired'] = 1
        with self.assertRaisesRegex(ValueError, 'topology_changed'):
            review_profile(self.t, self.profile, self.obs)

    def test_invalid_historical_flow(self):
        self.obs['flows_lmin'][self.a] = -1
        with self.assertRaisesRegex(ValueError, 'invalid_flow'):
            review_profile(self.t, self.profile, self.obs)

    def test_wrong_zone(self):
        self.profile['zone_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'topology_changed'):
            review_profile(self.t, self.profile, self.obs)
