import unittest
from custom_components.irpat_efficiency.thermal_balance import analyze_zone


class ThermalBalanceTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{"id": "a", "target_c": 22}, {"id": "b", "target_c": 23}]
        self.end = 86400

    def run_case(self, a, b, **kwargs):
        series = {"a": {str(s): a for s in range(0, self.end, 300)},
                  "b": {str(s): b for s in range(0, self.end, 300)}}
        return analyze_zone(self.rooms, series, 0, self.end, **{"eligible": True, **kwargs})

    def test_common(self):
        r = self.run_case(23, 24)
        self.assertEqual(r["pattern"], "common")
        self.assertEqual(r["common_error_c"], 1)
        self.assertEqual(r["rooms"]["a"]["residual_c"], 0)

    def test_distribution(self):
        r = self.run_case(21, 24)
        self.assertEqual(r["pattern"], "distribution")
        self.assertEqual(r["common_error_c"], 0)

    def test_area_weighting(self):
        self.rooms[0]["area_m2"] = 30
        self.rooms[1]["area_m2"] = 10
        r = self.run_case(23, 22)
        self.assertEqual(r["weighting"], "area")
        self.assertEqual(r["common_error_c"], 0.5)
        self.assertEqual(r["pattern"], "mixed")

    def test_missing(self):
        r = self.run_case(22, None)
        self.assertEqual(r["status"], "insufficient_data")
        self.assertIsNone(r["common_error_c"])

    def test_settling_and_modes(self):
        self.assertEqual(self.run_case(22, 23, last_adjustment=1)["status"], "settling")
        self.assertEqual(self.run_case(22, 23, eligible=False)["status"], "monitor_only")

    def test_near_targets(self):
        r = self.run_case(22.3, 23.3)
        self.assertEqual(r["pattern"], "near_targets")
        self.assertEqual(r["rooms"]["a"]["within_fraction"], 1)

    def test_disjoint_coverage(self):
        series = {"a": {str(s): 22 for s in range(0, 43200, 300)},
                  "b": {str(s): 23 for s in range(43200, 86400, 300)}}
        r = analyze_zone(self.rooms, series, 0, 86400, eligible=True)
        self.assertEqual(r["coverage"], 0)
        self.assertEqual(r["status"], "insufficient_data")
