"""Regression coverage for grouped configuration and explicit room circuit setup."""
import unittest
from copy import deepcopy

from custom_components.irpat_efficiency.topology import add_item, empty_topology, TopologyError
from custom_components.irpat_efficiency.topology_remove import remove_selection, removal_preview
from custom_components.irpat_efficiency.room_setup import complete_room, parse_positions


class GuidedConfigurationTests(unittest.TestCase):
    def setUp(self):
        t, self.floor = add_item(empty_topology(), "floors", "Ground")
        t, self.zone = add_item(t, "zones", "Heating")
        t, self.extra = add_item(t, "zones", "Unused")
        t, self.source = add_item(t, "sources", "HP", source_type="heat_pump",
                                  zone_ids=[self.zone, self.extra])
        t, self.manifold = add_item(t, "manifolds", "Distributor", floor_id=self.floor, zone_id=self.zone)
        t, self.room = add_item(t, "rooms", "Bedroom", floor_id=self.floor)
        self.t = t

    def test_room_circuits_explicit_positions_and_sensor(self):
        result = complete_room(self.t, self.room, [], manual_temperature="sensor.bedroom",
                               manifold_id=self.manifold, count=2, positions="2, 4")
        self.assertEqual([c["position"] for c in result["circuits"]], [2, 4])
        self.assertTrue(all(c["room_id"] == self.room for c in result["circuits"]))
        self.assertEqual(result["bindings"][0]["entity_id"], "sensor.bedroom")
        self.assertEqual(self.t["circuits"], [])
        self.assertEqual(self.t["bindings"], [])

    def test_invalid_position_or_duplicate_is_atomic(self):
        original = deepcopy(self.t)
        for count, positions in [(2, "1"), (2, "1,1"), (1, "0"), (1.5, "1"), (1, None), (0, "1")]:
            with self.subTest(count=count, positions=positions):
                with self.assertRaises(TopologyError):
                    complete_room(self.t, self.room, [], manual_temperature="sensor.bedroom",
                                  manifold_id=self.manifold, count=count, positions=positions)
        self.assertEqual(self.t, original)
        t = complete_room(self.t, self.room, [], manifold_id=self.manifold, count=1, positions="2")
        original = deepcopy(t)
        with self.assertRaises(TopologyError):
            complete_room(t, self.room, [], manifold_id=self.manifold, count=2, positions="1,2")
        self.assertEqual(t, original)

    def test_zero_circuits_keeps_existing(self):
        t = complete_room(self.t, self.room, [], manifold_id=self.manifold, count=1, positions="2")
        self.assertEqual(complete_room(t, self.room, []), t)
        self.assertEqual(parse_positions(0, None), [])

    def test_zone_preview_and_explicit_detachment(self):
        self.assertEqual(removal_preview(self.t, "zones", [self.extra]),
                         {"selected": ["Unused"], "blockers": [], "sources": ["HP"]})
        for kw in ({}, {"confirmed": True}, {"detach_zone_sources": True}):
            with self.assertRaises(TopologyError):
                remove_selection(self.t, "zones", [self.extra], **kw)
        result = remove_selection(self.t, "zones", [self.extra], confirmed=True, detach_zone_sources=True)
        self.assertEqual(result["sources"][0]["id"], self.source)
        self.assertEqual(result["sources"][0]["zone_ids"], [self.zone])
        self.assertEqual(result["zones"][0]["id"], self.zone)
        self.assertEqual(self.t["sources"][0]["zone_ids"], [self.zone, self.extra])

    def test_batch_blocks_if_any_dependent_manifold(self):
        before = deepcopy(self.t)
        self.assertEqual(removal_preview(self.t, "zones", [self.zone, self.extra])["blockers"], ["Distributor"])
        with self.assertRaises(TopologyError):
            remove_selection(self.t, "zones", [self.zone, self.extra], confirmed=True, detach_zone_sources=True)
        self.assertEqual(self.t, before)

    def test_batch_unreferenced_rooms(self):
        t, room = add_item(self.t, "rooms", "Other", floor_id=self.floor)
        result = remove_selection(t, "rooms", [self.room, room], confirmed=True)
        self.assertEqual(result["rooms"], [])
        self.assertEqual(len(t["rooms"]), 2)
