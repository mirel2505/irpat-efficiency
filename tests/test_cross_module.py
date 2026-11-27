"""Cross-module contracts, using real topology and algorithm code."""
import unittest

from custom_components.irpat_efficiency.topology import add_item, empty_topology, TopologyError
from custom_components.irpat_efficiency.zone_analysis import zone_diagnostics
from custom_components.irpat_efficiency.report_inputs import prepare_capture
from custom_components.irpat_efficiency.building_report import snapshot
from custom_components.irpat_efficiency.telemetry import set_binding
from custom_components.irpat_efficiency.defrost import enabled_sources


class CrossModuleTests(unittest.TestCase):
    def setUp(self):
        t, floor = add_item(empty_topology(), 'floors', 'Ground')
        t, self.zone = add_item(t, 'zones', 'Zone', operating_mode='weather', circuit_control='manual')
        t, self.manifold = add_item(t, 'manifolds', 'Manifold', floor_id=floor, zone_id=self.zone)
        t, self.a = add_item(t, 'rooms', 'A', floor_id=floor, heating_target_c=22, area_m2=20)
        t, self.b = add_item(t, 'rooms', 'B', floor_id=floor, heating_target_c=22, area_m2=10)
        for position, rid in enumerate((self.a, self.a, self.b), 1):
            t, _ = add_item(t, 'circuits', str(position), manifold_id=self.manifold, room_id=rid, position=position)
        t, _ = add_item(t, 'bindings', 'A sensor', room_id=self.a, entity_id='sensor.a')
        t['outdoor_entity_id'] = 'sensor.outside'
        self.t = t
        self.series = {rid: {str(s): v for s in range(0, 86401, 300)}
                       for rid, v in ((self.a, 22), (self.b, 22), ('__outdoor__', 2))}

    def test_duplicate_sensor_rejected_before_report(self):
        with self.assertRaisesRegex(TopologyError, 'duplicate_entity'):
            add_item(self.t, 'bindings', 'B sensor', room_id=self.b, entity_id='sensor.a')

    def test_outdoor_sensor_not_indoor(self):
        with self.assertRaisesRegex(TopologyError, 'duplicate_entity'):
            add_item(self.t, 'bindings', 'B sensor', room_id=self.b, entity_id='sensor.outside')

    def test_legacy_duplicate_sensor_cannot_confirm_balance(self):
        self.t['bindings'].append({'room_id': self.b, 'entity_id': 'sensor.a'})
        result = zone_diagnostics(self.t, self.series, 86400, [], 0, 'heating')[self.zone]
        self.assertEqual(result['status'], 'duplicate_temperature_sensor')
        self.assertEqual(result['stability']['status'], 'monitor_only')
        with self.assertRaisesRegex(ValueError, 'missing_temperature_configuration'):
            prepare_capture(self.t, self.series, 0, 86400, now=86400, configuration_since=0)

    def test_independent_room_pipeline(self):
        t, _ = add_item(self.t, 'bindings', 'B sensor', room_id=self.b, entity_id='sensor.b')
        result = zone_diagnostics(t, self.series, 86400, [], 0, 'heating')[self.zone]
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(len(result['rooms']), 2)
        p = prepare_capture(t, self.series, 0, 86400, now=86400, configuration_since=0)
        r = snapshot(p['indoor'], p['outdoor'], 0, 86400, room_ids=p['room_ids'],
                     boundary_id='house', thermal_kwh=48, reviewed=True)
        self.assertEqual(r['apparent_w_per_k'], 100)

    def test_non_defrost_source_does_not_disable_room_analysis(self):
        t, gas = add_item(self.t, 'sources', 'Boiler', source_type='gas', zone_ids=[self.zone])
        t, hp = add_item(t, 'sources', 'Heat pump', source_type='heat_pump', zone_ids=[self.zone])
        t = set_binding(t, 'sources', hp, 'defrost', 'binary_sensor.defrost')
        self.assertEqual(enabled_sources(t), {hp})
        self.assertNotIn(gas, enabled_sources(t))
        self.assertEqual(zone_diagnostics(t, self.series, 86400, [], 0, 'heating')[self.zone]['status'], 'observed')
