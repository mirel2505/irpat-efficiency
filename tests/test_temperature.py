"""Synthetic tests for temperature readings and availability."""
import unittest

from custom_components.irpat_efficiency.temperature import temperature_c, summarize_room


class TemperatureTests(unittest.TestCase):
    def test_units(self):
        self.assertAlmostEqual(temperature_c("71.6", "°F"), 22)
        self.assertAlmostEqual(temperature_c(295.15, "K"), 22)
        self.assertEqual(temperature_c("22", "°C"), 22)

    def test_invalid(self):
        for value, unit in [(None, "°C"), ("unavailable", "°C"), ("NaN", "°C"),
                            (float("inf"), "°C"), (True, "°C"), (22, None), (999, "°C")]:
            self.assertIsNone(temperature_c(value, unit))

    def test_room_mean_and_missing(self):
        readings = [{"entity_id": "sensor.a", "temperature_c": 22},
                    {"entity_id": "sensor.b", "temperature_c": None},
                    {"entity_id": "sensor.c", "temperature_c": 23}]
        result = summarize_room(readings, 22)
        self.assertEqual(result["temperature_c"], 22.5)
        self.assertEqual(result["status"], "warm")
        self.assertEqual(result["valid_count"], 2)
        self.assertEqual(result["configured_count"], 3)

    def test_missing_target_and_missing_value(self):
        self.assertIsNone(summarize_room([], 22)["temperature_c"])
        self.assertEqual(summarize_room([], 22)["status"], "unknown")
        self.assertEqual(summarize_room([{"entity_id":"sensor.a","temperature_c":22}])["status"], "unknown")

    def test_tolerance_and_duplicate(self):
        result = summarize_room([{"entity_id":"sensor.a","temperature_c":22.3},
                                 {"entity_id":"sensor.a","temperature_c":22.3}], 22)
        self.assertEqual(result["status"], "within")
        self.assertEqual(result["valid_count"], 1)

    def test_cold(self):
        self.assertEqual(summarize_room([{"entity_id":"sensor.a","temperature_c":21}],22)["status"], "cold")
