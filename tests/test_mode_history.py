import unittest
from custom_components.irpat_efficiency.mode_history import observation, interval_mode, transition


class ModeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'entity_id': 'sensor.mode', 'mapping': {'1': 'heating', '2': 'dhw', '3': 'defrost'}}

    def obs(self, now, raw='1', changed=0, reported=None, binding=None):
        return observation(binding or self.binding, raw, changed, now if reported is None else reported, now)

    def test_continuity(self):
        self.assertEqual(interval_mode(self.obs(0), self.obs(300), 0, 300), 'heating')

    def test_return_to_same_state(self):
        self.assertIsNone(interval_mode(self.obs(0), self.obs(300, changed=250), 0, 300))

    def test_mixed_modes(self):
        self.assertIsNone(interval_mode(self.obs(0), self.obs(300, '2', 100), 0, 300))

    def test_dhw_defrost_not_heating(self):
        for raw, mode in [('2', 'dhw'), ('3', 'defrost')]:
            self.assertEqual(interval_mode(self.obs(0, raw), self.obs(300, raw), 0, 300), mode)

    def test_changed_mapping(self):
        binding = {'entity_id': 'sensor.other', 'mapping': {'1': 'heating'}}
        self.assertIsNone(interval_mode(self.obs(0), self.obs(300, binding=binding), 0, 300))

    def test_stale_unmapped_unavailable(self):
        self.assertIsNone(self.obs(400, reported=0))
        self.assertIsNone(self.obs(0, 'unknown'))
        self.assertIsNone(self.obs(0, '9'))
        self.assertIsNone(self.obs(0, changed=1))

    def test_missing_or_gap(self):
        self.assertIsNone(interval_mode(None, self.obs(300), 0, 300))
        self.assertIsNone(interval_mode(self.obs(0), self.obs(600), 0, 600))

    def test_outside_observation_window(self):
        self.assertIsNone(interval_mode(self.obs(10), self.obs(300), 0, 300))
        self.assertIsNone(interval_mode(self.obs(0), self.obs(300, reported=290), 0, 300))

    def test_transition(self):
        a, b = self.obs(0), self.obs(300, '2', 100)
        self.assertIsNone(transition(a, self.obs(300), 300))
        self.assertEqual(transition(a, b, 300)['mode'], 'dhw')
        self.assertIsNone(transition(b, None, 400)['mode'])
        self.assertEqual(transition(None, a, 0)['mode'], 'heating')
        self.assertIsNone(transition(None, None, 0))

    def test_hidden_transition(self):
        a, b = self.obs(0), self.obs(300, changed=250)
        self.assertEqual(transition(a, b, 300)['reported_change_at'], 250)
        self.assertTrue(transition(a, b, 300)['reported_only'])
