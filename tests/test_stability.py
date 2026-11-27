import unittest
from custom_components.irpat_efficiency.stability import stability, DAY


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{"id": "a", "target_c": 22}, {"id": "b", "target_c": 23}]
        self.end = 5 * DAY
        self.series = {r["id"]: {str(s): r["target_c"] for s in range(0, self.end, 300)} for r in self.rooms}

    def check(self, **kwargs):
        return stability(self.rooms, self.series, self.end, **{
            "eligible": True, "configuration_since": 0, **kwargs})

    def test_five_days(self):
        self.assertEqual(self.check()["status"], "stable_observed")
        self.assertEqual(self.check()["consecutive_days"], 5)

    def test_configurable_days(self):
        self.assertEqual(self.check(days=3)["consecutive_days"], 3)
        self.assertEqual(self.check(days=7)["status"], "collecting")
        with self.assertRaises(ValueError):
            self.check(days=2)

    def test_intervention(self):
        result = self.check(last_adjustment=3 * DAY)
        self.assertEqual(result["consecutive_days"], 2)
        self.assertEqual(result["status"], "collecting")
        self.assertEqual(self.check(last_adjustment=self.end - 300)["status"], "settling")

    def test_configuration_change(self):
        self.assertEqual(self.check(configuration_since=DAY)["consecutive_days"], 4)
        self.assertEqual(self.check(configuration_since=None)["status"], "collecting")

    def test_bad_day_breaks_streak(self):
        for s in range(2 * DAY, 3 * DAY, 300):
            self.series["b"][str(s)] = 24
        result = self.check()
        self.assertEqual(result["consecutive_days"], 2)
        self.assertEqual(result["status"], "criteria_not_met")

    def test_mean_masks_variation(self):
        for s in range(4 * DAY, self.end, 300):
            self.series["a"][str(s)] = 21 if s % 600 == 0 else 23
        self.assertEqual(self.check()["consecutive_days"], 0)

    def test_missing_samples(self):
        for s in range(4 * DAY, self.end, 600):
            del self.series["a"][str(s)]
        result = self.check()
        self.assertEqual(result["daily"][0]["coverage"], 0.5)
        self.assertEqual(result["status"], "criteria_not_met")

    def test_ineligible(self):
        self.assertEqual(self.check(eligible=False)["status"], "monitor_only")

    def test_target_missing(self):
        self.rooms[0]["target_c"] = None
        self.assertEqual(self.check()["status"], "collecting")
