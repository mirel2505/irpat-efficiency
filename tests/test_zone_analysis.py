"""Synthetic topology diagnostics tests."""
import unittest
from custom_components.irpat_efficiency.zone_analysis import zone_diagnostics


class ZoneTests(unittest.TestCase):
    def setUp(self):
        self.t = {"zones": [{"id":"z","name":"Zone","operating_mode":"weather","circuit_control":"manual"}],
                  "manifolds":[{"id":"m","zone_id":"z"}],
                  "circuits":[{"manifold_id":"m","room_id":"r"},{"manifold_id":"m","room_id":"r"}],
                  "rooms":[{"id":"r","heating_target_c":22,"cooling_target_c":25}]}
        self.series = {"r": {str(s): 23 for s in range(0, 86400, 300)}}

    def result(self, since=0, journal=(), mode="heating"):
        return zone_diagnostics(self.t, self.series, 86400, journal, since, mode)["z"]

    def test_duplicate_loops(self):
        r = self.result()
        self.assertEqual(len(r["rooms"]), 1)
        self.assertEqual(r["common_error_c"], 1)

    def test_cooling(self):
        self.assertEqual(self.result(mode="cooling")["common_error_c"], -2)

    def test_configuration_change(self):
        self.assertEqual(self.result(since=1)["status"], "configuration_collecting")

    def test_adjustment(self):
        entry = {"manifold_id":"m","phase":"after","timestamp":"1970-01-01T12:00:00+00:00"}
        self.assertEqual(self.result(journal=[entry])["status"], "settling")

    def test_shared_room(self):
        self.t["zones"].append({"id":"z2","name":"Other","operating_mode":"fixed","circuit_control":"manual"})
        self.t["manifolds"].append({"id":"m2","zone_id":"z2"})
        self.t["circuits"].append({"manifold_id":"m2","room_id":"r"})
        self.assertEqual(self.result()["status"], "shared_rooms")

    def test_thermostat(self):
        self.t["zones"][0]["operating_mode"]="onoff"
        self.assertEqual(self.result()["status"], "monitor_only")
