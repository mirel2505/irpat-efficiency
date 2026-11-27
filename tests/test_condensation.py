import unittest

from custom_components.irpat_efficiency.condensation import assess_room, summarize_zone


class CondensationTests(unittest.TestCase):
    def sample(self, value, stamp=1000):
        return {"value": value, "timestamp": stamp}

    def check(self, **kwargs):
        return assess_room(self.sample(25), self.sample(60), now=1000, **kwargs)

    def test_dew_point_and_surface(self):
        r = self.check(surface=self.sample(20))
        self.assertAlmostEqual(r["dew_point_c"], 16.69, places=1)
        self.assertEqual(r["status"], "surface_above_margin")
        self.assertTrue(r["hardware_protection_required"])

    def test_condensation_risk(self):
        r = self.check(surface=self.sample(16))
        self.assertEqual(r["surface"]["status"], "at_or_below_dew_point")
        self.assertEqual(r["status"], "review_risk")

    def test_low_margin(self):
        self.assertEqual(self.check(surface=self.sample(18))["surface"]["status"], "low_margin")

    def test_supply_proxy_only(self):
        self.assertEqual(self.check(supply=self.sample(20))["status"], "proxy_only")

    def test_proxy_risk_not_ignored(self):
        r = self.check(surface=self.sample(22), supply=self.sample(16))
        self.assertEqual(r["status"], "review_risk")
        self.assertEqual(r["surface"]["status"], "above_margin")

    def test_missing_humidity(self):
        r = assess_room(self.sample(25), None, now=1000, surface=self.sample(20))
        self.assertIsNone(r["dew_point_c"])
        self.assertEqual(r["status"], "unknown")

    def test_invalid_humidity(self):
        for value in (0, 101, float("nan"), True):
            r = assess_room(self.sample(25), self.sample(value), now=1000)
            self.assertEqual(r["status"], "unknown")

    def test_stale_future_or_unsynchronized(self):
        for stamp in (0, 1001, 600):
            self.assertEqual(self.check(surface=self.sample(20, stamp))["status"], "unknown")

    def test_zone_partial(self):
        r = summarize_zone({"a": self.check(surface=self.sample(20))}, ["a", "b"])
        self.assertEqual(r["status"], "incomplete_surface_coverage")

    def test_zone_risk_and_complete(self):
        a = self.check(surface=self.sample(20))
        b = self.check(surface=self.sample(16))
        self.assertEqual(summarize_zone({"a": a, "b": b}, ["a", "b"])["status"], "review_risk")
        self.assertEqual(summarize_zone({"a": a}, ["a"])["status"], "observed_surfaces_above_margin")

    def test_bad_threshold(self):
        with self.assertRaises(ValueError):
            self.check(margin_c=0)
