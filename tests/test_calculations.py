"""Synthetic unit tests for the initial calculation primitives."""
import unittest

from custom_components.irpat_efficiency.calculations import (
    balancing_capability, normalize_flow, thermal_power_w, period_cop, dew_point_c,
)


class CalculationsTest(unittest.TestCase):
    def test_eligibility(self):
        self.assertEqual(balancing_capability("weather", "manual"), "weather_compensation")
        self.assertEqual(balancing_capability("fixed", "open"), "fixed_supply")
        for mode, control in [("weather", "automatic"), ("onoff", "manual"),
                              ("unknown", "open"), ("weather", "unknown")]:
            self.assertEqual(balancing_capability(mode, control), "monitor_only")

    def test_normalization(self):
        self.assertAlmostEqual(normalize_flow(0.85, 1100/60, 1560/60), 1.2054545)
        self.assertEqual(normalize_flow(0, 10, 20), 0)
        for inputs in [(None, 10, 20), (1, 0, 20), (11, 10, 20), (1, 10, -2)]:
            self.assertIsNone(normalize_flow(*inputs))

    def test_power(self):
        self.assertAlmostEqual(thermal_power_w(1, 35, 30, 1000, 4180), 5805.5555556)
        self.assertLess(thermal_power_w(1, 15, 20, 1000, 4180), 0)
        self.assertIsNone(thermal_power_w(1, 35, 30, None, 4180))
        self.assertIsNone(thermal_power_w(-1, 35, 30, 1000, 4180))

    def test_cop(self):
        self.assertAlmostEqual(period_cop(57.6, 12), 4.8)
        self.assertIsNone(period_cop(57.6, 0))
        self.assertIsNone(period_cop(None, 12))
        self.assertIsNone(period_cop(float("nan"), 12))

    def test_dewpoint(self):
        self.assertAlmostEqual(dew_point_c(25, 60), 16.69, places=1)
        self.assertAlmostEqual(dew_point_c(25, 100), 25)
        self.assertIsNone(dew_point_c(25, 0))
        self.assertIsNone(dew_point_c(None, 60))


if __name__ == "__main__":
    unittest.main()
