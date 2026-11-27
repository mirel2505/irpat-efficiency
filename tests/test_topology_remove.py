import unittest
from copy import deepcopy
from custom_components.irpat_efficiency.topology import add_item, empty_topology, TopologyError
from custom_components.irpat_efficiency.topology_remove import remove_item
from custom_components.irpat_efficiency.telemetry import set_binding
from custom_components.irpat_efficiency.journal import make_snapshot
from custom_components.irpat_efficiency.profiles import create_profile
from custom_components.irpat_efficiency.profile_store import compare_profile


class RemoveTests(unittest.TestCase):
    def setUp(self):
        t, self.floor = add_item(empty_topology(), 'floors', 'Floor')
        t, self.zone = add_item(t, 'zones', 'Zone')
        t, self.room = add_item(t, 'rooms', 'Room', floor_id=self.floor)
        t, self.mid = add_item(t, 'manifolds', 'Manifold', floor_id=self.floor, zone_id=self.zone)
        t, self.cid = add_item(t, 'circuits', 'Circuit', manifold_id=self.mid, room_id=self.room, position=1)
        t, self.bid = add_item(t, 'bindings', 'Sensor', room_id=self.room, entity_id='sensor.room')
        t, self.sid = add_item(t, 'sources', 'Source', source_type='heat_pump', zone_ids=[self.zone])
        t = set_binding(t, 'sources', self.sid, 'electrical_energy', 'sensor.energy')
        t = set_binding(t, 'rooms', self.room, 'humidity', 'sensor.humidity')
        self.t = t

    def remove(self, collection, identifier):
        return remove_item(self.t, collection, identifier, confirmed=True)

    def test_confirmation_is_explicit(self):
        for value in (False, 1, 'yes'):
            with self.assertRaisesRegex(TopologyError, 'remove_confirmation_required'):
                remove_item(self.t, 'circuits', self.cid, confirmed=value)

    def test_no_cascade_of_references(self):
        old = deepcopy(self.t)
        for group, identifier in [('floors', self.floor), ('zones', self.zone), ('rooms', self.room), ('manifolds', self.mid)]:
            with self.assertRaisesRegex(TopologyError, 'object_in_use'):
                self.remove(group, identifier)
        self.assertEqual(self.t, old)

    def test_source_only_removes_own_telemetry(self):
        updated = self.remove('sources', self.sid)
        self.assertEqual(updated['sources'], [])
        self.assertEqual(updated['telemetry'], [self.t['telemetry'][1]])
        self.assertEqual(updated['zones'], self.t['zones'])
        self.assertEqual(len(self.t['sources']), 1)

    def test_binding_can_be_replaced_with_new_identity(self):
        updated = self.remove('bindings', self.bid)
        updated, new = add_item(updated, 'bindings', 'New', room_id=self.room, entity_id='sensor.room')
        self.assertNotEqual(new, self.bid)
        self.assertEqual(updated['rooms'], self.t['rooms'])

    def test_historical_profile_not_reused_for_replaced_circuit(self):
        snap = make_snapshot(self.t, self.mid, {self.cid: 1.2})
        profile = create_profile('Reference', self.t, self.zone, [snap], 'heating')
        updated = self.remove('circuits', self.cid)
        updated, new = add_item(updated, 'circuits', 'Replacement', manifold_id=self.mid, room_id=self.room, position=1)
        self.assertNotEqual(new, self.cid)
        with self.assertRaisesRegex(ValueError, 'topology_changed'):
            compare_profile(profile, updated, snap)
        self.assertEqual(profile['flows_lmin'], {self.cid: 1.2})
        self.assertEqual(snap['flows_lmin'], {self.cid: 1.2})

    def test_removing_leaf_objects_then_parents(self):
        updated = self.t
        for group, identifier in [('bindings', self.bid), ('circuits', self.cid), ('rooms', self.room),
                                  ('manifolds', self.mid), ('sources', self.sid), ('zones', self.zone), ('floors', self.floor)]:
            updated = remove_item(updated, group, identifier, confirmed=True)
        self.assertFalse(updated['telemetry'])
        self.assertTrue(all(not updated[group] for group in ('bindings','circuits','rooms','manifolds','sources','zones','floors')))

    def test_invalid_id_or_collection(self):
        with self.assertRaisesRegex(TopologyError, 'invalid_reference'):
            self.remove('rooms', 'unknown')
        with self.assertRaisesRegex(TopologyError, 'invalid_schema'):
            self.remove('telemetry', self.sid)
