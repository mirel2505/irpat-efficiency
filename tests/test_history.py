"""Synthetic tests for bounded sampling, missing data and local-day comparison."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import unittest

from custom_components.irpat_efficiency.history import (
    bucket, record_samples, window_stats, previous_local_day, compare_room,
)


class HistoryTests(unittest.TestCase):
    def test_missing_slots(self):
        data = {}
        record_samples(data, 300, {"a": 22, "b": None})
        record_samples(data, 900, {"a": 23})
        self.assertNotIn("b", data)
        result = window_stats(data["a"], 300, 1200)
        self.assertEqual(result["mean_c"], 22.5)
        self.assertEqual(result["count"], 2)
        self.assertAlmostEqual(result["coverage"], 2/3)

    def test_duplicate_slot(self):
        data = {}
        record_samples(data, 300, {"a": 22})
        record_samples(data, 350, {"a": 23})
        self.assertEqual(data["a"], {"300": 23})

    def test_retention(self):
        data = {}
        record_samples(data, 300, {"a": 22})
        record_samples(data, 9*86400, {"b": 21})
        self.assertNotIn("a", data)

    def test_empty(self):
        self.assertIsNone(window_stats({}, 300, 900)["mean_c"])
        self.assertEqual(window_stats({}, 300, 900)["coverage"], 0)

    def test_local_same_hour_dst(self):
        tz = ZoneInfo("Europe/Bucharest")
        now = datetime(2026, 3, 29, 10, tzinfo=tz).timestamp()
        prior = previous_local_day(now, tz)
        self.assertEqual(datetime.fromtimestamp(prior, tz).hour, 10)
        self.assertEqual(now-prior, 23*3600)

    def test_previous_sample(self):
        now = datetime(2026, 11, 27, 10, tzinfo=timezone.utc).timestamp()
        series = {str(bucket(now-86400)): 21.5}
        self.assertEqual(compare_room(series, now, timezone.utc)["yesterday_same_slot_c"],21.5)
        self.assertIsNone(compare_room({}, now, timezone.utc)["yesterday_same_slot_c"])
