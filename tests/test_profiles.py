import unittest
from custom_components.irpat_efficiency.profiles import create_profile


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.t = {"zones": [{"id": "z", "name": "Zone"}],
                  "manifolds": [{"id": "m", "zone_id": "z"}],
                  "circuits": [{"id": "a", "manifold_id": "m", "room_id": "r"},
                               {"id": "b", "manifold_id": "m", "room_id": "r"}],
                  "rooms": [{"id": "r", "heating_target_c": 22}]}
        self.s = {"id": "s", "manifold_id": "m", "timestamp": "2026-01-01T00:00:00+00:00", "flows_lmin": {"a": 1.2, "b": 0}}

    def create(self, snapshots=None):
        return create_profile("Reference", self.t, "z", [self.s] if snapshots is None else snapshots, "heating")

    def test_reference(self):
        result = self.create()
        self.assertEqual(result["targets_c"], {"r": 22})
        self.assertEqual(result["flows_lmin"], {"a": 1.2, "b": 0})
        self.assertEqual(result["references"]["m"]["snapshot_id"], "s")
        self.assertFalse(result["automatic_restore"])
        self.assertEqual(result["status"], "manual_reference")

    def test_missing_circuit(self):
        del self.s["flows_lmin"]["b"]
        with self.assertRaisesRegex(ValueError, "incomplete_circuits"):
            self.create()

    def test_missing_manifold(self):
        self.t["manifolds"].append({"id": "other", "zone_id": "z"})
        with self.assertRaisesRegex(ValueError, "incomplete_manifolds"):
            self.create()

    def test_invalid_flow(self):
        self.s["flows_lmin"]["b"] = float("nan")
        with self.assertRaisesRegex(ValueError, "incomplete_circuits"):
            self.create()

    def test_independent_profile(self):
        result = self.create()
        self.s["flows_lmin"]["a"] = 3
        self.t["zones"][0]["name"] = "Renamed"
        self.assertEqual(result["flows_lmin"]["a"], 1.2)
        self.assertEqual(result["zone"]["name"], "Zone")
