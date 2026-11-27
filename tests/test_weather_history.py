import unittest
from custom_components.irpat_efficiency.weather_history import daily_observations, DAY


class WeatherHistoryTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{'id': 'a', 'target_c': 22}, {'id': 'b', 'target_c': 23}]
        self.series = {i: {str(s): t for s in range(0, DAY, 300)} for i,t in [('a',23),('b',23)]}
        self.outside = {str(s): 5 for s in range(0, DAY, 300)}

    def get(self, since=0):
        return daily_observations(self.rooms, self.series, self.outside, DAY, since=since)

    def test_aligned(self):
        r = self.get()[0]
        self.assertEqual(r['coverage'], 1)
        self.assertEqual(r['outdoor_c'], 5)
        self.assertEqual(r['common_error_c'], .5)
        self.assertEqual(r['max_residual_c'], .5)
        self.assertFalse(r['comparable'])

    def test_missing_outdoor(self):
        self.outside.clear()
        r = self.get()[0]
        self.assertEqual(r['coverage'], 0)
        self.assertIsNone(r['common_error_c'])

    def test_partial_overlap(self):
        del self.outside['0']
        del self.series['a']['300']
        self.assertAlmostEqual(self.get()[0]['coverage'], 286/288)

    def test_weighted(self):
        self.rooms[0]['area_m2'] = 30
        self.rooms[1]['area_m2'] = 10
        self.assertEqual(self.get()[0]['common_error_c'], .75)

    def test_configuration_change(self):
        self.assertEqual(self.get(since=1), [])
        self.assertEqual(self.get(since=None), [])

    def test_missing_target(self):
        self.rooms[0]['target_c'] = None
        self.assertEqual(self.get(), [])
