"""Manual hydraulic journal contract tests."""
import unittest

from custom_components.irpat_efficiency.journal import make_snapshot, compare_snapshots


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.topology = {"manifolds": [{"id": "m"}, {"id": "other"}], "circuits": [
            {"id": "a", "manifold_id": "m"}, {"id": "b", "manifold_id": "m"},
            {"id": "c", "manifold_id": "other"}]}

    def test_manual_and_missing(self):
        snap = make_snapshot(self.topology, "m", {"a": 0}, source_total_m3h=1.5)
        self.assertEqual(snap["flows_lmin"]["a"], 0)
        self.assertIsNone(snap["manifold_total_lmin"])
        self.assertEqual(snap["source_total_m3h"], 1.5)

    def test_complete_sum(self):
        snap = make_snapshot(self.topology, "m", {"a": 1, "b": 2})
        self.assertEqual(snap["manifold_total_lmin"], 3)
        self.assertEqual(snap["total_provenance"], "sum_all_circuits")

    def test_invalid(self):
        for readings in ({"c": 1}, {"a": -1}, {"a": float("nan")}, {"a": None}, {}):
            with self.assertRaises(ValueError):
                make_snapshot(self.topology, "m", readings)
        with self.assertRaises(ValueError):
            make_snapshot(self.topology, "m", {"a": 1}, phase="after")

    def test_before_after(self):
        before = make_snapshot(self.topology, "m", {"a": 1.2}, phase="before", manifold_total_lmin=26)
        after = make_snapshot(self.topology, "m", {"a": 0.85}, phase="after", previous=before,
                              manifold_total_lmin=1100/60)
        self.assertEqual(after["previous_id"], before["id"])
        self.assertIsNone(compare_snapshots(before, after))
        result = compare_snapshots(before, after, comparable=True)
        self.assertAlmostEqual(result["a"]["normalized_after_lmin"], 1.20545454545)

    def test_inconsistent_totals(self):
        before = make_snapshot(self.topology, "m", {"a": 1, "b": 2}, manifold_total_lmin=2)
        after = make_snapshot(self.topology, "m", {"a": 1, "b": 1}, manifold_total_lmin=2)
        self.assertIsNone(compare_snapshots(before, after, comparable=True))

    def test_different_provenance(self):
        before = make_snapshot(self.topology, "m", {"a": 1, "b": 2})
        after = make_snapshot(self.topology, "m", {"a": 1}, manifold_total_lmin=3)
        self.assertIsNone(compare_snapshots(before, after, comparable=True))
