import unittest
from copy import deepcopy

from custom_components.irpat_efficiency.topology import add_item, empty_topology, TopologyError
from custom_components.irpat_efficiency.topology_edit import edit_item
from custom_components.irpat_efficiency.journal import make_snapshot
from custom_components.irpat_efficiency.profiles import create_profile
from custom_components.irpat_efficiency.profile_store import compare_profile
from custom_components.irpat_efficiency.telemetry import set_binding
from custom_components.irpat_efficiency.report_inputs import prepare_capture


class TopologyEditTests(unittest.TestCase):
    def setUp(self):
        t, self.floor = add_item(empty_topology(), 'floors', 'Ground')
        t, self.zone = add_item(t, 'zones', 'Zone', operating_mode='weather', circuit_control='manual')
        t, self.room = add_item(t, 'rooms', 'Room', floor_id=self.floor, area_m2=20, heating_target_c=22)
        t, self.other = add_item(t, 'rooms', 'Other', floor_id=self.floor)
        t, self.manifold = add_item(t, 'manifolds', 'Manifold', floor_id=self.floor, zone_id=self.zone)
        t, self.circuit = add_item(t, 'circuits', 'Loop 1', manifold_id=self.manifold, room_id=self.room, position=1)
        t, self.circuit2 = add_item(t, 'circuits', 'Loop 2', manifold_id=self.manifold, room_id=self.other, position=2)
        t, self.binding = add_item(t, 'bindings', 'Temperature', room_id=self.room, entity_id='sensor.room')
        t, self.binding2 = add_item(t, 'bindings', 'Other temperature', room_id=self.other, entity_id='sensor.other')
        t, self.source = add_item(t, 'sources', 'Heat pump', source_type='heat_pump', zone_ids=[self.zone])
        t = set_binding(t, 'sources', self.source, 'electrical_energy', 'sensor.energy')
        t['sources'][0]['energy_boundary_confirmed'] = True
        t['outdoor_entity_id'] = 'sensor.outdoor'
        self.t = t

    def test_rename_all_collections_preserves_ids_and_references(self):
        for collection in ('floors', 'zones', 'sources', 'rooms', 'manifolds', 'circuits', 'bindings'):
            original = deepcopy(self.t)
            edited = edit_item(self.t, collection, self.t[collection][0]['id'], 'Renamed')
            expected = deepcopy(self.t)
            expected[collection][0]['name'] = 'Renamed'
            self.assertEqual(edited, expected)
            self.assertEqual(self.t, original)

    def test_room_targets_and_clear_optional(self):
        edited = edit_item(self.t, 'rooms', self.room, 'Room', area_m2=None, heating_target_c=23.5, cooling_target_c=25)
        self.assertEqual(edited['rooms'][0]['id'], self.room)
        self.assertEqual(edited['rooms'][0]['floor_id'], self.floor)
        self.assertIsNone(edited['rooms'][0]['area_m2'])
        self.assertEqual(edited['rooms'][0]['heating_target_c'], 23.5)
        self.assertEqual(edited['rooms'][0]['cooling_target_c'], 25)
        self.assertEqual(self.t['rooms'][0]['area_m2'], 20)

    def test_invalid_target_rolls_back(self):
        original = deepcopy(self.t)
        with self.assertRaisesRegex(TopologyError, 'invalid_number'):
            edit_item(self.t, 'rooms', self.room, 'Room', heating_target_c=100)
        self.assertEqual(self.t, original)

    def test_position_cannot_overlap_and_id_preserved(self):
        with self.assertRaisesRegex(TopologyError, 'duplicate_position'):
            edit_item(self.t, 'circuits', self.circuit, 'Loop', position=2)
        edited = edit_item(self.t, 'circuits', self.circuit, 'Loop', position=3, length_m=95)
        self.assertEqual(edited['circuits'][0]['id'], self.circuit)
        self.assertEqual(edited['circuits'][0]['position'], 3)
        self.assertEqual(edited['circuits'][0]['room_id'], self.room)

    def test_replace_sensor_revalidates_and_updates_attribute(self):
        for entity in ('sensor.other', 'sensor.outdoor'):
            with self.assertRaisesRegex(TopologyError, 'duplicate_entity'):
                edit_item(self.t, 'bindings', self.binding, 'Sensor', entity_id=entity)
        edited = edit_item(self.t, 'bindings', self.binding, 'Sensor', entity_id='climate.room')
        self.assertEqual(edited['bindings'][0]['id'], self.binding)
        self.assertEqual(edited['bindings'][0]['attribute'], 'current_temperature')

    def test_source_rename_preserves_telemetry_and_confirmation(self):
        edited = edit_item(self.t, 'sources', self.source, 'New label')
        self.assertEqual(edited['telemetry'], self.t['telemetry'])
        self.assertTrue(edited['sources'][0]['energy_boundary_confirmed'])
        self.assertEqual(edited['sources'][0]['zone_ids'], [self.zone])

    def test_structural_reassignment_rejected(self):
        for collection, identifier, changes in [('circuits', self.circuit, {'room_id':self.other}),
                                                ('sources',self.source,{'source_type':'gas'}),
                                                ('bindings',self.binding,{'room_id':self.other})]:
            with self.assertRaisesRegex(TopologyError, 'unsupported_edit'):
                edit_item(self.t, collection, identifier, 'Changed', **changes)

    def test_zone_updates_control(self):
        edited = edit_item(self.t, 'zones', self.zone, 'Zone', operating_mode='onoff', circuit_control='automatic')
        self.assertEqual(edited['zones'][0]['operating_mode'], 'onoff')
        self.assertEqual(edited['zones'][0]['circuit_control'], 'automatic')

    def test_existing_profiles_and_journal_references_survive_rename(self):
        snap = make_snapshot(self.t, self.manifold, {self.circuit:1.1,self.circuit2:0.9})
        profile = create_profile('Reference', self.t, self.zone, [snap], 'heating')
        edited = edit_item(self.t, 'circuits', self.circuit, 'Renamed loop')
        comparison = compare_profile(profile, edited, snap)
        self.assertEqual(comparison[self.circuit]['reference_lmin'], 1.1)
        self.assertEqual(profile['references'][self.manifold]['snapshot_id'], snap['id'])

    def test_sensor_change_changes_report_measurement_identity(self):
        series = {rid: {str(s):v for s in range(0,86401,300)}
                  for rid,v in ((self.room,22),(self.other,21),('__outdoor__',2))}
        a = prepare_capture(self.t, series, 0, 86400, now=86400, configuration_since=0)
        edited = edit_item(self.t, 'bindings', self.binding, 'Sensor', entity_id='sensor.new')
        b = prepare_capture(edited, series, 0, 86400, now=86400, configuration_since=0)
        self.assertNotEqual(a['measurement_signature'], b['measurement_signature'])
