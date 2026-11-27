import unittest
from copy import deepcopy
from custom_components.irpat_efficiency.topology import empty_topology, add_item, TopologyError
from custom_components.irpat_efficiency.registry_import import (
    import_floor, import_room, import_all, sensor_candidates, confirm_sensors,
)


class RegistryImportTests(unittest.TestCase):
    def setUp(self):
        self.floors = {"f": "Ground", "u": "Upper"}
        self.areas = {"a": {"name": "Bedroom", "floor_id": "f"},
                      "b": {"name": "Living", "floor_id": "f"},
                      "c": {"name": "Garage", "floor_id": None}}
        self.t, self.floor = add_item(empty_topology(), "floors", "Ground")
        self.t, self.room = add_item(self.t, "rooms", "Bedroom", floor_id=self.floor,
                                     area_m2=17.75, heating_target_c=22)

    def test_reuse_existing_identity_and_metadata(self):
        before = deepcopy(self.t)
        result, rid = import_room(self.t, self.floors, self.areas, "a")
        self.assertEqual(rid, self.room)
        self.assertEqual(result["floors"][0]["id"], self.floor)
        self.assertEqual(result["rooms"][0]["area_m2"], 17.75)
        self.assertEqual(result["rooms"][0]["heating_target_c"], 22)
        self.assertEqual(self.t, before)
        self.assertEqual(result["rooms"][0]["ha_area_id"], "a")
        self.assertEqual(result["floors"][0]["ha_floor_id"], "f")

    def test_bulk_repeat_is_idempotent(self):
        result = import_all(self.t, self.floors, self.areas)
        self.assertEqual(len(result["floors"]), 2)
        self.assertEqual(len(result["rooms"]), 2)
        self.assertEqual(result, import_all(result, self.floors, self.areas))

    def test_unassigned_requires_explicit_floor(self):
        with self.assertRaisesRegex(TopologyError, "registry_floor_required"):
            import_room(self.t, self.floors, self.areas, "c")
        result, rid = import_room(self.t, self.floors, self.areas, "c", self.floor)
        self.assertEqual(result["rooms"][-1]["floor_id"], self.floor)
        self.assertNotEqual(rid, self.room)

    def test_native_rename_and_move_do_not_change_local_identity(self):
        result, rid = import_room(self.t, self.floors, self.areas, "a")
        self.areas["a"] = {"name": "Renamed", "floor_id": "u"}
        again, new_id = import_room(result, self.floors, self.areas, "a")
        self.assertEqual(rid, new_id)
        self.assertEqual(again, result)

    def test_ambiguous_manual_match_rejected_atomically(self):
        t, _ = add_item(self.t, "floors", "ground")
        before = deepcopy(t)
        with self.assertRaisesRegex(TopologyError, "registry_conflict"):
            import_all(t, self.floors, self.areas)
        self.assertEqual(t, before)

    def test_preserve_bindings_and_circuits(self):
        t, _ = add_item(self.t, "bindings", "Sensor", room_id=self.room, entity_id="sensor.room")
        t, zone = add_item(t, "zones", "Zone")
        t, manifold = add_item(t, "manifolds", "Manifold", floor_id=self.floor, zone_id=zone)
        t, _ = add_item(t, "circuits", "Loop", manifold_id=manifold, room_id=self.room, position=1)
        result = import_all(t, self.floors, self.areas)
        for group in ("bindings", "circuits", "manifolds", "zones"):
            self.assertEqual(result[group], t[group])

    def test_sensor_candidates_and_explicit_binding(self):
        t, rid = import_room(self.t, self.floors, self.areas, "a")
        t["outdoor_entity_id"] = "sensor.outside"
        entities = [{"entity_id": eid, "name": eid, "area_id": aid, "device_class": kind, "disabled": disabled}
                    for eid, aid, kind, disabled in [
                        ("sensor.room", "a", "temperature", False),
                        ("climate.room", "a", None, False),
                        ("sensor.humidity", "a", "humidity", False),
                        ("sensor.disabled", "a", "temperature", True),
                        ("sensor.outside", "a", "temperature", False),
                        ("sensor.other", "b", "temperature", False),
                        ("sensor.power", "a", "power", False)]]
        found = sensor_candidates(t, rid, entities)
        self.assertEqual(set(found["temperature"]), {"sensor.room", "climate.room"})
        self.assertEqual(set(found["humidity"]), {"sensor.humidity"})
        self.assertEqual(t["bindings"], [])
        updated = confirm_sensors(t, rid, entities, ["climate.room"], "sensor.humidity")
        self.assertEqual(updated["bindings"][0]["attribute"], "current_temperature")
        self.assertEqual(updated["telemetry"][0]["entity_id"], "sensor.humidity")
        self.assertFalse(sensor_candidates(updated, rid, entities)["humidity"])
        self.assertNotIn("climate.room", sensor_candidates(updated, rid, entities)["temperature"])
        with self.assertRaisesRegex(TopologyError, "invalid_entity"):
            confirm_sensors(t, rid, entities, ["sensor.other"])

    def test_manual_sensor_not_replaced_or_reused(self):
        t, rid = import_room(self.t, self.floors, self.areas, "a")
        t, _ = add_item(t, "bindings", "Sensor", room_id=rid, entity_id="sensor.room")
        entities = [{"entity_id": "sensor.room", "name": "Room", "area_id": "a", "device_class": "temperature"}]
        self.assertFalse(sensor_candidates(t, rid, entities)["temperature"])
        with self.assertRaisesRegex(TopologyError, "invalid_entity"):
            confirm_sensors(t, rid, entities, ["sensor.room"])
