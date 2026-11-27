"""Tests for independent, user-defined installations."""
import unittest

from custom_components.irpat_efficiency.topology import (
    TopologyError, add_item, empty_topology, rename_item,
)


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.data = empty_topology()
        self.data, self.floor = add_item(self.data, "floors", "Level A")
        self.data, self.zone = add_item(self.data, "zones", "Zone A")
        self.data, self.room = add_item(self.data, "rooms", "Room A", floor_id=self.floor)
        self.data, self.manifold = add_item(self.data, "manifolds", "Manifold A",
                                           floor_id=self.floor, zone_id=self.zone)

    def test_empty(self):
        self.assertEqual(empty_topology()["rooms"], [])

    def test_multiple_manifolds_and_floors(self):
        data, floor2 = add_item(self.data, "floors", "Level B")
        data, m2 = add_item(data, "manifolds", "Manifold B", floor_id=floor2, zone_id=self.zone)
        data, _ = add_item(data, "circuits", "A", manifold_id=self.manifold, room_id=self.room, position=1)
        data, _ = add_item(data, "circuits", "B", manifold_id=m2, room_id=self.room, position=1)
        self.assertEqual(len(data["circuits"]), 2)
        self.assertEqual(len(data["rooms"]), 1)
        self.assertEqual(self.data["circuits"], [])

    def test_duplicate_position(self):
        data, _ = add_item(self.data, "circuits", "A", manifold_id=self.manifold, position=1)
        with self.assertRaisesRegex(TopologyError, "duplicate_position"):
            add_item(data, "circuits", "B", manifold_id=self.manifold, position=1)

    def test_invalid_reference(self):
        with self.assertRaisesRegex(TopologyError, "invalid_reference"):
            add_item(self.data, "rooms", "Room B", floor_id="missing")

    def test_rename_keeps_id(self):
        data = rename_item(self.data, "rooms", self.room, "Renamed")
        self.assertEqual(data["rooms"][0]["id"], self.room)
        self.assertEqual(self.data["rooms"][0]["name"], "Room A")

    def test_temperature_binding(self):
        data, _ = add_item(self.data, "bindings", "My sensor", room_id=self.room, entity_id="climate.test")
        self.assertEqual(data["bindings"][0]["attribute"], "current_temperature")
        self.assertEqual(data["bindings"][0]["name"], "My sensor")
        with self.assertRaisesRegex(TopologyError, "duplicate_entity"):
            add_item(data, "bindings", "Again", room_id=self.room, entity_id="climate.test")

    def test_missing_data(self):
        self.assertIsNone(self.data["rooms"][0]["heating_target_c"])
        self.assertIsNone(self.data["rooms"][0]["area_m2"])
        with self.assertRaisesRegex(TopologyError, "invalid_number"):
            add_item(self.data, "rooms", "Bad", floor_id=self.floor, area_m2=-1)

    def test_source_can_be_unintegrated(self):
        data, _ = add_item(self.data, "sources", "Heat source", zone_ids=[self.zone])
        self.assertEqual(data["sources"][0]["source_type"], "unintegrated")
