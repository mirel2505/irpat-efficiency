import unittest
from custom_components.irpat_efficiency.inertia import cooling_drift


class InertiaTests(unittest.TestCase):
    def setUp(self):
        self.end = 14400
        self.indoor = {str(s): 22 - s / self.end for s in range(0, self.end + 300, 300)}
        self.outdoor = {k: 2 for k in self.indoor}

    def check(self, **kwargs):
        return cooling_drift(self.indoor, self.outdoor, 0, self.end,
                             **{"heat_off_confirmed": True, "comparable": True, **kwargs})

    def test_observed(self):
        r = self.check()
        self.assertEqual(r["status"], "observed")
        self.assertEqual(r["drop_c"], 1)
        self.assertEqual(r["rate_c_per_h"], .25)
        self.assertAlmostEqual(r["degree_hours"], 78)
        self.assertAlmostEqual(r["normalized_per_h"], 1 / 78)

    def test_review(self):
        self.assertEqual(self.check(heat_off_confirmed=False)["status"], "review_required")
        self.assertEqual(self.check(comparable=False)["status"], "review_required")

    def test_missing(self):
        del self.indoor["300"]
        self.assertEqual(self.check()["status"], "insufficient_data")
        self.assertIsNone(self.check()["rate_c_per_h"])

    def test_missing_endpoint(self):
        del self.outdoor[str(self.end)]
        self.assertEqual(self.check()["status"], "insufficient_data")

    def test_nonfinite(self):
        self.indoor["300"] = float("nan")
        self.assertEqual(self.check()["status"], "insufficient_data")

    def test_warming(self):
        self.indoor[str(self.end)] = 23
        r = self.check()
        self.assertEqual(r["rate_c_per_h"], -.25)
        self.assertIsNone(r["normalized_per_h"])

    def test_outdoor_warmer(self):
        self.outdoor["300"] = 25
        self.assertIsNone(self.check()["normalized_per_h"])

    def test_short_or_unaligned(self):
        for end in (3600, 7201):
            r = cooling_drift(self.indoor, self.outdoor, 0, end,
                              heat_off_confirmed=True, comparable=True)
            self.assertEqual(r["status"], "insufficient_data")
